"""The community feed: writing posts, indexing their cashtags, and attaching real trades.

Two rules shape everything here.

**Cashtags are extracted, never authored.** The client sends a body; the server finds `$AAPL` in it
and writes `post_symbols` rows. A client can't tag a post with a ticker it doesn't mention, and the
index can't drift from the text, because both come from one parse of one string.

**Attached trades are resolved, never trusted.** The client sends handles ("t42"), and the server
looks each one up, checks it belongs to the author, and copies the real numbers across. Sizes and
prices in a published post are therefore always fills that actually happened — see the module
docstring of `schemas/community.py` for why this is the one place sizes become public at all.

Reading is offered three ways — see `list_posts`. "popular" ranks by likes decayed by age,
"following" narrows to the people you follow, and "latest" is the raw chronological feed.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.follow import Follow
from app.models.option_trade import OptionTrade
from app.models.portfolio import Portfolio
from app.models.post import Post, PostLike, PostSymbol, PostTrade
from app.models.trade import Trade
from app.models.user import User
from app.schemas.community import (
    AttachableTrade,
    FeedMode,
    PostCreate,
    PostOut,
    PostTradeOut,
)
from app.services.competitions import as_utc
from app.services.social import option_label


class CommunityError(Exception):
    """Raised on an invalid post (empty body, an attachment that isn't the author's)."""


# A cashtag: "$" then a ticker, optionally with a class suffix ("$BRK.B", "$RDS-A"). Letters only
# after the "$", so prices ("$210") and amounts ("$1.5k") are never mistaken for symbols.
#
# The frontend re-detects cashtags with the same pattern to linkify a body it renders from text
# (see `utils/cashtags.ts`); the two must stay in step, or a ticker could be filterable but not
# clickable, or the reverse.
CASHTAG_RE = re.compile(r"\$([A-Za-z]{1,6}(?:[.\-][A-Za-z]{1,4})?)\b")

# Distinct tickers indexed per post. A cap keeps one body from writing an unbounded number of index
# rows; a post naming more than ten companies isn't really "about" any of them.
MAX_SYMBOLS_PER_POST = 10


def extract_symbols(body: str) -> list[str]:
    """Distinct uppercased tickers mentioned in `body`, in the order they first appear."""
    out: list[str] = []
    seen: set[str] = set()
    for match in CASHTAG_RE.finditer(body):
        symbol = match.group(1).upper()
        if symbol in seen:
            continue
        seen.add(symbol)
        out.append(symbol)
        if len(out) >= MAX_SYMBOLS_PER_POST:
            break
    return out


def attachable_trades(db: Session, user: User, limit: int = 20) -> list[AttachableTrade]:
    """The author's own recent fills, newest first — what the composer offers to attach.

    Sourced from every portfolio they own, competition entries included: those are their trades to
    publish or not. `portfolio_name` rides along so the choice is informed (attaching a fill from a
    live contest is a real decision), and is dropped once the post is written.

    Expiry settlements are excluded, matching the activity feed: an option expiring worthless is
    something that happened to you, not a trade you placed.
    """
    portfolios = {
        p.id: p for p in db.scalars(select(Portfolio).where(Portfolio.user_id == user.id))
    }
    if not portfolios:
        return []
    portfolio_ids = list(portfolios)
    out: list[AttachableTrade] = []

    # Each ledger is capped at `limit` before merging: the newest `limit` overall can't include
    # anything older than the newest `limit` of either side.
    for t in db.scalars(
        select(Trade)
        .where(Trade.portfolio_id.in_(portfolio_ids))
        .order_by(Trade.executed_at.desc())
        .limit(limit)
    ):
        out.append(
            AttachableTrade(
                ref=f"t{t.id}",
                kind="stock",
                symbol=t.symbol,
                label=t.symbol,
                side=t.side,
                quantity=t.quantity,
                price=t.price,
                executed_at=as_utc(t.executed_at),
                portfolio_name=portfolios[t.portfolio_id].name,
            )
        )

    for ot in db.scalars(
        select(OptionTrade)
        .where(OptionTrade.portfolio_id.in_(portfolio_ids), OptionTrade.action != "settle")
        .order_by(OptionTrade.executed_at.desc())
        .limit(limit)
    ):
        out.append(
            AttachableTrade(
                ref=f"o{ot.id}",
                kind="option",
                symbol=ot.underlying,
                label=option_label(ot),
                side=ot.action,
                quantity=ot.quantity,
                price=ot.price,
                executed_at=as_utc(ot.executed_at),
                portfolio_name=portfolios[ot.portfolio_id].name,
            )
        )

    out.sort(key=lambda t: t.executed_at, reverse=True)
    return out[:limit]


def _resolve_trade_ref(db: Session, user: User, ref: str) -> PostTrade:
    """Turn one "t<id>"/"o<id>" handle into a snapshot of the author's real fill.

    A handle that doesn't exist and one that belongs to someone else fail with the *same* message
    on purpose — otherwise the distinction would let a caller map out which trade ids are real.
    """
    prefix, rest = ref[:1], ref[1:]
    if prefix not in ("t", "o") or not rest.isdigit():
        raise CommunityError(f"'{ref}' isn't a trade you can attach.")
    trade_id = int(rest)

    if prefix == "t":
        trade = db.get(Trade, trade_id)
        if trade is None or trade.portfolio.user_id != user.id:
            raise CommunityError("You can only attach your own trades.")
        return PostTrade(
            kind="stock",
            symbol=trade.symbol,
            label=trade.symbol,
            side=trade.side,
            quantity=trade.quantity,
            price=trade.price,
            executed_at=as_utc(trade.executed_at),
        )

    option_trade = db.get(OptionTrade, trade_id)
    if option_trade is None or option_trade.portfolio.user_id != user.id:
        raise CommunityError("You can only attach your own trades.")
    if option_trade.action == "settle":
        raise CommunityError("An expiry settlement isn't a trade you placed.")
    return PostTrade(
        kind="option",
        symbol=option_trade.underlying,
        label=option_label(option_trade),
        side=option_trade.action,
        quantity=option_trade.quantity,
        price=option_trade.price,
        executed_at=as_utc(option_trade.executed_at),
    )


def create_post(db: Session, user: User, payload: PostCreate) -> Post:
    """Write a post, its cashtag index, and snapshots of any trades attached to it."""
    body = payload.body.strip()
    if not body:
        raise CommunityError("A post needs something in it.")

    # Deduplicate handles first (attaching the same fill twice would publish it twice), then
    # resolve every one *before* creating the post, so a bad handle aborts without a partial write.
    refs: list[str] = []
    seen: set[str] = set()
    for ref in payload.trade_refs:
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)
    attachments = [_resolve_trade_ref(db, user, ref) for ref in refs]

    post = Post(user_id=user.id, body=body)
    post.symbols = [PostSymbol(symbol=s) for s in extract_symbols(body)]
    post.trades = attachments
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


# --- Likes -------------------------------------------------------------------------------------
def like_counts(db: Session, post_ids: list[int]) -> dict[int, int]:
    """How many people have liked each of `post_ids`. One query, absent ids simply missing."""
    if not post_ids:
        return {}
    rows = db.execute(
        select(PostLike.post_id, func.count(PostLike.id))
        .where(PostLike.post_id.in_(post_ids))
        .group_by(PostLike.post_id)
    ).all()
    return {post_id: count for post_id, count in rows}


def liked_by(db: Session, post_ids: list[int], viewer: User) -> set[int]:
    """Which of `post_ids` the viewer has personally liked. One query."""
    if not post_ids:
        return set()
    return set(
        db.scalars(
            select(PostLike.post_id).where(
                PostLike.post_id.in_(post_ids), PostLike.user_id == viewer.id
            )
        )
    )


def set_like(db: Session, user: User, post_id: int, liked: bool) -> tuple[int, bool] | None:
    """Like or unlike a post. Returns its (count, liked_by_me) after the change, or None if gone.

    Idempotent in both directions: liking something you already like leaves the one row alone, and
    unliking something you never liked does nothing. The unique constraint enforces that at the
    schema level, but checking first means an impatient double-click reads as a no-op rather than
    surfacing as an IntegrityError.

    You may like your own post. It's a public counter, not a score anyone is ranked on, and the
    alternative — a rule the UI has to explain — buys nothing.
    """
    if db.get(Post, post_id) is None:
        return None

    existing = db.scalar(
        select(PostLike).where(PostLike.post_id == post_id, PostLike.user_id == user.id)
    )
    if liked and existing is None:
        db.add(PostLike(post_id=post_id, user_id=user.id))
        db.commit()
    elif not liked and existing is not None:
        db.delete(existing)
        db.commit()

    count = db.scalar(select(func.count(PostLike.id)).where(PostLike.post_id == post_id)) or 0
    return count, liked


# --- Reading the feed --------------------------------------------------------------------------
# Popular scores each candidate as `(likes + 1) / (age_hours + 2) ** GRAVITY` — the classic
# Hacker News shape. Two properties earn it that spot:
#
# * **It decays.** Ten likes yesterday lose to ten likes this morning, so the tab stays a feed
#   rather than settling into a hall of fame nobody's seen change in a week.
# * **It degrades to "newest first".** The `+ 1` means an unliked post still scores, so a young
#   feed where nothing has been liked yet reads chronologically instead of arriving empty.
POPULAR_GRAVITY = 1.5

# Popular ranks the newest N posts rather than the whole table. Scoring happens in Python — SQLite
# and Postgres disagree on date arithmetic, and the formula above is worth keeping readable and
# directly testable — so the candidate set has to be bounded. Anything past this cut-off has decayed
# far below what a like could lift back into the first pages.
POPULAR_CANDIDATES = 500


def _popularity(post: Post, like_count: int, now: datetime) -> float:
    age_hours = max((now - as_utc(post.created_at)).total_seconds() / 3600.0, 0.0)
    return (like_count + 1) / (age_hours + 2.0) ** POPULAR_GRAVITY


def list_posts(
    db: Session,
    viewer: User,
    *,
    feed: FeedMode = "popular",
    symbol: str | None = None,
    limit: int = 30,
    before_id: int | None = None,
    offset: int = 0,
) -> list[Post]:
    """A page of the feed in the order `feed` asks for, optionally only posts mentioning `symbol`.

    The two chronological modes page by id rather than offset: ids are monotonic and unique, so
    "everything below the last one I saw" can't skip or repeat a post when someone publishes
    mid-scroll. Ordering by id also means the cursor and the sort key are the same column, which
    two posts written in the same second would break if this sorted on `created_at`.

    "popular" can't use that cursor, because its sort key is a computed score rather than a column,
    so it pages by `offset` instead. A like landing mid-scroll can shift a post between pages —
    that's the price of ranking on something that moves.
    """
    stmt = select(Post)
    if symbol:
        stmt = stmt.join(PostSymbol).where(PostSymbol.symbol == symbol.strip().upper())
    if feed == "following":
        # Your own posts belong here too: a "following" feed that hides what you just wrote reads
        # as a bug, and you can't follow yourself to fix it.
        followees = select(Follow.followee_id).where(Follow.follower_id == viewer.id)
        stmt = stmt.where(or_(Post.user_id.in_(followees), Post.user_id == viewer.id))

    if feed == "popular":
        candidates = list(db.scalars(stmt.order_by(Post.id.desc()).limit(POPULAR_CANDIDATES)))
        counts = like_counts(db, [p.id for p in candidates])
        now = datetime.now(timezone.utc)
        # Id descending as the tiebreak, so equally-scored posts still read newest-first.
        candidates.sort(key=lambda p: (_popularity(p, counts.get(p.id, 0), now), p.id), reverse=True)
        return candidates[offset : offset + limit]

    if before_id is not None:
        stmt = stmt.where(Post.id < before_id)
    return list(db.scalars(stmt.order_by(Post.id.desc()).limit(limit)))


def delete_post(db: Session, user: User, post_id: int) -> bool:
    """Delete one of your own posts. False if it isn't yours or doesn't exist."""
    post = db.get(Post, post_id)
    if post is None or post.user_id != user.id:
        return False
    db.delete(post)  # cascades its symbols and trade snapshots
    db.commit()
    return True


def build_post(
    post: Post,
    viewer: User,
    like_count: int | None = None,
    liked_by_me: bool | None = None,
) -> PostOut:
    """Project a stored post for the reader.

    Like state is passed in when a whole page is being projected (`build_posts` resolves it for the
    page in two queries). Left out — projecting a single post that was just written or liked — it
    falls back to the loaded relationship, which is already in the session.
    """
    if like_count is None:
        like_count = len(post.likes)
    if liked_by_me is None:
        liked_by_me = any(like.user_id == viewer.id for like in post.likes)
    return PostOut(
        id=post.id,
        username=post.user.username,
        display_name=post.user.display_name,
        body=post.body,
        symbols=[s.symbol for s in post.symbols],
        trades=[
            PostTradeOut(
                kind=t.kind,
                symbol=t.symbol,
                label=t.label,
                side=t.side,
                quantity=t.quantity,
                price=t.price,
                executed_at=as_utc(t.executed_at),
            )
            for t in post.trades
        ],
        created_at=as_utc(post.created_at),
        is_mine=post.user_id == viewer.id,
        like_count=like_count,
        liked_by_me=liked_by_me,
    )


def build_posts(db: Session, posts: list[Post], viewer: User) -> list[PostOut]:
    """Project a page of posts, resolving every post's like state in two queries rather than 2N."""
    post_ids = [p.id for p in posts]
    counts = like_counts(db, post_ids)
    mine = liked_by(db, post_ids, viewer)
    return [build_post(p, viewer, counts.get(p.id, 0), p.id in mine) for p in posts]
