"""Offline verification for the community feed: cashtags, posts, and attached trades.

Runs against an in-memory SQLite DB with no market data provider involved — nothing here prices
anything. Route handlers are invoked as plain functions (their `Depends(...)` defaults passed
explicitly), which exercises the real guard code without an HTTP server.

Run:  ./.venv/Scripts/python.exe scripts/test_community_offline.py
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Run directly from backend/: Python puts *this* file's directory on sys.path, not backend/, so
# `app` wouldn't import without this.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.routes.community import (
    get_attachable_trades,
    get_posts,
    like_post,
    publish_post,
    remove_post,
    unlike_post,
)
from app.db.base import Base
from app.models.follow import Follow
from app.models.option_trade import OptionTrade
from app.models.portfolio import Portfolio
from app.models.post import Post, PostLike, PostSymbol, PostTrade
from app.models.trade import Trade
from app.models.user import User
from app.schemas.community import PostCreate
from app.services.community import CommunityError, create_post, extract_symbols

# ---------------------------------------------------------------------------
# Fixtures & assertions
# ---------------------------------------------------------------------------
def fresh_db():
    """A brand-new in-memory engine per scenario → full isolation."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, future=True)()


def mk_user(db, username: str):
    u = User(email=f"{username}@example.com", username=username, hashed_password="x")
    db.add(u)
    db.flush()
    p = Portfolio(user_id=u.id, name="Default", cash_balance=100_000.0, starting_balance=100_000.0)
    db.add(p)
    db.commit()
    return u, p


def mk_trade(db, portfolio, symbol="AAPL", side="buy", quantity=10.0, price=200.0, ago=0):
    t = Trade(
        portfolio_id=portfolio.id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        executed_at=datetime.now(timezone.utc) - timedelta(minutes=ago),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def mk_option_trade(db, portfolio, action="buy", quantity=2.0, price=3.5, ago=0):
    t = OptionTrade(
        portfolio_id=portfolio.id,
        underlying="AAPL",
        occ_symbol="AAPL260918C00210000",
        option_type="call",
        strike=210.0,
        expiration=date(2026, 9, 18),
        action=action,
        quantity=quantity,
        price=price,
        executed_at=datetime.now(timezone.utc) - timedelta(minutes=ago),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def mk_follow(db, follower, followee):
    db.add(Follow(follower_id=follower.id, followee_id=followee.id))
    db.commit()


# The route takes its feed mode and paging cursor as keywords; these keep the assertions below
# reading as "the latest feed says X" rather than as argument lists.
def latest(db, user, symbol=None, limit=30, before_id=None):
    return get_posts(
        feed="latest", symbol=symbol, limit=limit, before_id=before_id, db=db, user=user
    )


def popular(db, user, symbol=None, limit=30, offset=0):
    return get_posts(feed="popular", symbol=symbol, limit=limit, offset=offset, db=db, user=user)


def following(db, user, symbol=None, limit=30, before_id=None):
    return get_posts(
        feed="following", symbol=symbol, limit=limit, before_id=before_id, db=db, user=user
    )


def age_post(db, post_id, hours):
    """Backdate a post so the age-decay half of the popularity score is actually exercised."""
    row = db.get(Post, post_id)
    row.created_at = datetime.now(timezone.utc) - timedelta(hours=hours)
    db.commit()


passed = 0
failed = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


def expect_community_error(name: str, fn, contains: str | None = None) -> None:
    global passed, failed
    try:
        fn()
        failed += 1
        print(f"  FAIL  {name}  (expected CommunityError, none raised)")
    except CommunityError as exc:
        if contains and contains.lower() not in str(exc).lower():
            failed += 1
            print(f"  FAIL  {name}  (message lacked {contains!r}: {exc})")
        else:
            passed += 1
            print(f"  PASS  {name}  -> rejected: {exc}")


def expect_http(name: str, fn, status: int | None = None) -> None:
    global passed, failed
    try:
        fn()
        failed += 1
        print(f"  FAIL  {name}  (expected HTTPException, none raised)")
    except HTTPException as exc:
        if status is not None and exc.status_code != status:
            failed += 1
            print(f"  FAIL  {name}  (expected {status}, got {exc.status_code})")
        else:
            passed += 1
            print(f"  PASS  {name}  -> {exc.status_code}: {exc.detail}")


# ---------------------------------------------------------------------------
print("\n[1] Cashtag extraction")
# ---------------------------------------------------------------------------
check("plain ticker", extract_symbols("bullish on $AAPL") == ["AAPL"])
check("uppercased", extract_symbols("$msft looks cheap") == ["MSFT"])
check("several, in order of appearance", extract_symbols("$TSLA vs $NVDA") == ["TSLA", "NVDA"])
check("repeats collapse to one", extract_symbols("$AAPL and $AAPL again") == ["AAPL"])
check("case-insensitive repeats collapse", extract_symbols("$aapl $AAPL") == ["AAPL"])
check("dollar amounts aren't tickers", extract_symbols("paid $210, worth $300") == [])
check("mixed money and tickers", extract_symbols("$AAPL at $210") == ["AAPL"])
check("class suffix kept", extract_symbols("$BRK.B forever") == ["BRK.B"])
check("hyphenated class kept", extract_symbols("$RDS-A pays well") == ["RDS-A"])
check("possessive stops at the ticker", extract_symbols("$AAPL's quarter") == ["AAPL"])
check("trailing period excluded", extract_symbols("I like $TSLA.") == ["TSLA"])
check("parenthesised", extract_symbols("($NVDA) is up") == ["NVDA"])
check("no cashtags → empty", extract_symbols("no tickers in here") == [])
check("bare dollar sign is not a tag", extract_symbols("just a $ sign") == [])
check(
    "capped at ten distinct symbols",
    len(extract_symbols(" ".join(f"$SYM{chr(65 + i)}" for i in range(15)))) == 10,
)

# ---------------------------------------------------------------------------
print("\n[2] Writing a post")
# ---------------------------------------------------------------------------
db = fresh_db()
alice, alice_p = mk_user(db, "alice")
bob, bob_p = mk_user(db, "bob")

out = publish_post(PostCreate(body="  $AAPL is a buy here  "), db, alice)
check("post returned with an id", out.id is not None)
check("body trimmed", out.body == "$AAPL is a buy here")
check("author surfaced", out.username == "alice")
check("symbols indexed from the body", out.symbols == ["AAPL"])
check("is_mine set for the author", out.is_mine is True)
check("no trades attached by default", out.trades == [])

rows = db.scalars(select(PostSymbol).where(PostSymbol.post_id == out.id)).all()
check("one index row written", len(rows) == 1)
check("index row is uppercased", rows[0].symbol == "AAPL")

expect_http("an empty body is rejected", lambda: publish_post(PostCreate(body="   "), db, alice), 400)

# The schema caps length; confirm the boundary is enforced rather than silently truncated.
try:
    PostCreate(body="x" * 1001)
    check("1001-char body rejected", False, "(schema accepted it)")
except Exception:
    check("1001-char body rejected", True)
check("1000-char body accepted", PostCreate(body="x" * 1000).body == "x" * 1000)

# ---------------------------------------------------------------------------
print("\n[3] Attaching your own trades")
# ---------------------------------------------------------------------------
t1 = mk_trade(db, alice_p, symbol="AAPL", side="buy", quantity=25.0, price=203.4, ago=30)
ot1 = mk_option_trade(db, alice_p, action="buy", quantity=2.0, price=3.5, ago=10)

out = publish_post(
    PostCreate(body="Backing this up on $AAPL", trade_refs=[f"t{t1.id}", f"o{ot1.id}"]), db, alice
)
check("both attachments published", len(out.trades) == 2)
stock = next(t for t in out.trades if t.kind == "stock")
option = next(t for t in out.trades if t.kind == "option")
check("stock size published verbatim", stock.quantity == 25.0)
check("stock fill price published verbatim", stock.price == 203.4)
check("stock side carried", stock.side == "buy")
check("stock label is the ticker", stock.label == "AAPL")
check("option contracts published", option.quantity == 2.0)
check("option premium published", option.price == 3.5)
check("option label reads like the activity feed", option.label == "AAPL $210 call 2026-09-18")
check("option symbol is the underlying", option.symbol == "AAPL")

snapshots = db.scalars(select(PostTrade).where(PostTrade.post_id == out.id)).all()
check("snapshots persisted", len(snapshots) == 2)

# The snapshot must not track the source row afterwards.
t1.quantity = 999.0
db.commit()
refreshed = latest(db, alice)
published = next(p for p in refreshed if p.id == out.id)
check(
    "editing the source trade doesn't rewrite the post",
    next(t for t in published.trades if t.kind == "stock").quantity == 25.0,
)

# ...nor should deleting the portfolio it came from take the post with it.
extra_p = Portfolio(
    user_id=alice.id, name="Scratch", cash_balance=1000.0, starting_balance=1000.0
)
db.add(extra_p)
db.commit()
t_scratch = mk_trade(db, extra_p, symbol="MSFT", quantity=5.0, price=400.0)
scratch_post = publish_post(
    PostCreate(body="one from the scratch book, $MSFT", trade_refs=[f"t{t_scratch.id}"]), db, alice
)
db.delete(extra_p)
db.commit()
survivors = latest(db, alice)
survivor = next((p for p in survivors if p.id == scratch_post.id), None)
check("the post survives its portfolio being deleted", survivor is not None)
check(
    "and still shows the fill",
    survivor is not None and survivor.trades[0].quantity == 5.0,
)

# ---------------------------------------------------------------------------
print("\n[4] You can only attach your own trades")
# ---------------------------------------------------------------------------
bob_trade = mk_trade(db, bob_p, symbol="NVDA", quantity=3.0, price=900.0)
expect_http(
    "someone else's trade is refused",
    lambda: publish_post(PostCreate(body="not mine", trade_refs=[f"t{bob_trade.id}"]), db, alice),
    400,
)
expect_community_error(
    "a trade that doesn't exist fails the same way",
    lambda: create_post(db, alice, PostCreate(body="ghost", trade_refs=["t999999"])),
    "your own trades",
)
expect_community_error(
    "an unparseable ref is rejected",
    lambda: create_post(db, alice, PostCreate(body="junk", trade_refs=["banana"])),
    "isn't a trade",
)
expect_community_error(
    "a ref with no id is rejected",
    lambda: create_post(db, alice, PostCreate(body="junk", trade_refs=["t"])),
    "isn't a trade",
)

settled = mk_option_trade(db, alice_p, action="settle", quantity=1.0, price=0.0)
expect_community_error(
    "expiry settlements can't be attached",
    lambda: create_post(db, alice, PostCreate(body="expired", trade_refs=[f"o{settled.id}"])),
    "settlement",
)

before = len(db.scalars(select(Post)).all())
try:
    create_post(db, alice, PostCreate(body="half-written", trade_refs=[f"t{t1.id}", "t999999"]))
except CommunityError:
    pass
check(
    "a bad ref aborts before anything is written",
    len(db.scalars(select(Post)).all()) == before,
)

check("attaching the same trade twice publishes it once",
      len(publish_post(
          PostCreate(body="dupe $AAPL", trade_refs=[f"t{t1.id}", f"t{t1.id}"]), db, alice
      ).trades) == 1)

try:
    PostCreate(body="too many", trade_refs=[f"t{t1.id}"] * 6)
    check("more than five attachments rejected", False, "(schema accepted it)")
except Exception:
    check("more than five attachments rejected", True)

# ---------------------------------------------------------------------------
print("\n[5] The composer's trade list")
# ---------------------------------------------------------------------------
db2 = fresh_db()
carol, carol_p = mk_user(db2, "carol")
dave, dave_p = mk_user(db2, "dave")
old = mk_trade(db2, carol_p, symbol="AAPL", ago=120)
recent = mk_trade(db2, carol_p, symbol="TSLA", ago=5)
carol_opt = mk_option_trade(db2, carol_p, ago=60)
carol_settle = mk_option_trade(db2, carol_p, action="settle", ago=1)
mk_trade(db2, dave_p, symbol="NVDA")

offered = get_attachable_trades(20, db2, carol)
refs = [t.ref for t in offered]
check("only the caller's trades are offered", len(offered) == 3)
check("newest first", refs[0] == f"t{recent.id}")
check("both ledgers merged into one list", f"o{carol_opt.id}" in refs)
check("older stock trade still offered", f"t{old.id}" in refs)
check("settlements excluded", f"o{carol_settle.id}" not in refs)
check("nobody else's trade leaks in", not any(t.symbol == "NVDA" for t in offered))
check("portfolio name shown while choosing", offered[0].portfolio_name == "Default")
check("size shown to its owner", offered[0].quantity == 10.0)
check("another trader sees only their own", [t.symbol for t in get_attachable_trades(20, db2, dave)] == ["NVDA"])

quiet, _ = mk_user(db2, "quiet")
check("a user who hasn't traded gets an empty list", get_attachable_trades(20, db2, quiet) == [])

# ---------------------------------------------------------------------------
print("\n[6] Reading the feed")
# ---------------------------------------------------------------------------
db3 = fresh_db()
erin, erin_p = mk_user(db3, "erin")
frank, frank_p = mk_user(db3, "frank")

p_apple = publish_post(PostCreate(body="long $AAPL"), db3, erin)
p_msft = publish_post(PostCreate(body="rotating into $MSFT"), db3, frank)
p_both = publish_post(PostCreate(body="$AAPL over $MSFT any day"), db3, erin)
p_none = publish_post(PostCreate(body="just vibes, no tickers"), db3, frank)

feed = latest(db3, erin)
check("everyone's posts appear, not just your own", len(feed) == 4)
check("newest first", [p.id for p in feed] == [p_none.id, p_both.id, p_msft.id, p_apple.id])
check("is_mine true for your own", next(p for p in feed if p.id == p_apple.id).is_mine is True)
check("is_mine false for others'", next(p for p in feed if p.id == p_msft.id).is_mine is False)

apple_only = latest(db3, erin, "AAPL")
check("filter returns only matching posts", {p.id for p in apple_only} == {p_apple.id, p_both.id})
check("a post naming two tickers appears under both",
      p_both.id in {p.id for p in latest(db3, erin, "MSFT")})
check("filter is case-insensitive", len(latest(db3, erin, "aapl")) == 2)
check("filter tolerates whitespace", len(latest(db3, erin, "  AAPL  ")) == 2)
check("an untagged post is in no filter", p_none.id not in {p.id for p in apple_only})
check("an unknown ticker returns nothing", latest(db3, erin, "ZZZZ") == [])

page1 = latest(db3, erin, limit=2)
page2 = latest(db3, erin, limit=2, before_id=page1[-1].id)
check("a page respects the limit", len(page1) == 2)
check("the cursor continues where the page ended", [p.id for p in page2] == [p_msft.id, p_apple.id])
check("pages don't overlap", not ({p.id for p in page1} & {p.id for p in page2}))
check(
    "the cursor is honoured alongside a filter",
    [p.id for p in latest(db3, erin, "AAPL", before_id=p_both.id)] == [p_apple.id],
)

# ---------------------------------------------------------------------------
print("\n[7] Deleting a post")
# ---------------------------------------------------------------------------
expect_http("you can't delete someone else's post",
            lambda: remove_post(p_msft.id, db3, erin), 404)
expect_http("deleting an unknown post 404s", lambda: remove_post(999999, db3, erin), 404)
check("the post survived the failed attempts",
      p_msft.id in {p.id for p in latest(db3, erin)})

erin_trade = mk_trade(db3, erin_p, symbol="AAPL", quantity=7.0, price=201.0)
doomed = publish_post(
    PostCreate(body="deleting this $AAPL take", trade_refs=[f"t{erin_trade.id}"]), db3, erin
)
remove_post(doomed.id, db3, erin)
check("your own post is deleted", doomed.id not in {p.id for p in latest(db3, erin)})
check("its cashtag index rows go with it",
      db3.scalars(select(PostSymbol).where(PostSymbol.post_id == doomed.id)).all() == [])
check("its attached trades go with it",
      db3.scalars(select(PostTrade).where(PostTrade.post_id == doomed.id)).all() == [])
check("the underlying trade is untouched", db3.get(Trade, erin_trade.id) is not None)

# ---------------------------------------------------------------------------
print("\n[8] Posts follow their author out")
# ---------------------------------------------------------------------------
db4 = fresh_db()
gina, gina_p = mk_user(db4, "gina")
gina_trade = mk_trade(db4, gina_p)
publish_post(PostCreate(body="$AAPL thoughts", trade_refs=[f"t{gina_trade.id}"]), db4, gina)
check("post exists first", len(db4.scalars(select(Post)).all()) == 1)
db4.delete(gina)
db4.commit()
check("deleting the user removes their posts", db4.scalars(select(Post)).all() == [])
check("and the cashtag index", db4.scalars(select(PostSymbol)).all() == [])
check("and the attached snapshots", db4.scalars(select(PostTrade)).all() == [])

# ---------------------------------------------------------------------------
print("\n[9] Liking a post")
# ---------------------------------------------------------------------------
db5 = fresh_db()
hank, hank_p = mk_user(db5, "hank")
iris, _ = mk_user(db5, "iris")

subject = publish_post(PostCreate(body="worth a like, $AAPL"), db5, hank)
check("a new post starts with no likes", subject.like_count == 0)
check("and isn't liked by its author", subject.liked_by_me is False)

r = like_post(subject.id, db5, iris)
check("liking counts it", r.like_count == 1)
check("and reports it back as liked", r.liked_by_me is True)
check("the like is addressed to the right post", r.post_id == subject.id)

r = like_post(subject.id, db5, iris)
check("liking twice is idempotent", r.like_count == 1)
check("one row per person per post",
      len(db5.scalars(select(PostLike).where(PostLike.post_id == subject.id)).all()) == 1)

r = like_post(subject.id, db5, hank)
check("a second person adds to the count", r.like_count == 2)
check("you may like your own post", r.liked_by_me is True)

seen_by_iris = next(p for p in latest(db5, iris) if p.id == subject.id)
check("the feed carries the count", seen_by_iris.like_count == 2)
check("liked_by_me is true for someone who liked it", seen_by_iris.liked_by_me is True)

third, _ = mk_user(db5, "jane")
seen_by_jane = next(p for p in latest(db5, third) if p.id == subject.id)
check("the same post reads unliked to someone who hasn't", seen_by_jane.liked_by_me is False)
check("but the count is the same for everyone", seen_by_jane.like_count == 2)

r = unlike_post(subject.id, db5, iris)
check("unliking decrements", r.like_count == 1)
check("and reports it back as unliked", r.liked_by_me is False)
r = unlike_post(subject.id, db5, iris)
check("unliking something you never liked is a no-op", r.like_count == 1)
check("nobody else's like was touched", r.liked_by_me is False)

expect_http("liking a post that doesn't exist 404s", lambda: like_post(999999, db5, iris), 404)
expect_http("unliking one that doesn't exist 404s", lambda: unlike_post(999999, db5, iris), 404)

liked_then_deleted = publish_post(PostCreate(body="short-lived"), db5, hank)
like_post(liked_then_deleted.id, db5, iris)
remove_post(liked_then_deleted.id, db5, hank)
check("deleting a post takes its likes with it",
      db5.scalars(select(PostLike).where(PostLike.post_id == liked_then_deleted.id)).all() == [])

# A like left on someone else's post is owned by the liker, not the post's author.
outlives = publish_post(PostCreate(body="hank's post, iris's like"), db5, hank)
like_post(outlives.id, db5, iris)
db5.delete(iris)
db5.commit()
check("deleting a user removes likes they left elsewhere",
      db5.scalars(select(PostLike).where(PostLike.post_id == outlives.id)).all() == [])
check("but leaves the post they liked standing", db5.get(Post, outlives.id) is not None)

# ---------------------------------------------------------------------------
print("\n[10] The popular feed")
# ---------------------------------------------------------------------------
db6 = fresh_db()
kate, _ = mk_user(db6, "kate")


def like_n(db, post_id, n, tag):
    """`n` distinct people like a post — real user rows, so the unique pair is genuinely exercised."""
    for i in range(n):
        voter, _ = mk_user(db, f"{tag}{i}")
        like_post(post_id, db, voter)


quiet_post = publish_post(PostCreate(body="nobody liked this $AAPL take"), db6, kate)
loved_post = publish_post(PostCreate(body="everyone liked this $AAPL take"), db6, kate)
like_n(db6, loved_post.id, 3, "fan")

ranked = [p.id for p in popular(db6, kate)]
check("at equal age, likes decide", ranked[0] == loved_post.id)
check("the unliked post still appears", quiet_post.id in ranked)

# Same likes, different age → the fresher one wins.
db7 = fresh_db()
liam, _ = mk_user(db7, "liam")
stale = publish_post(PostCreate(body="yesterday's news"), db7, liam)
fresh = publish_post(PostCreate(body="this morning's news"), db7, liam)
age_post(db7, stale.id, 48)
check("at equal likes, fresher wins", [p.id for p in popular(db7, liam)][0] == fresh.id)

# Decay is strong enough that a stale favourite loses to a fresh post...
db8 = fresh_db()
mia, _ = mk_user(db8, "mia")
old_hit = publish_post(PostCreate(body="last week's banger"), db8, mia)
like_n(db8, old_hit.id, 5, "old")
age_post(db8, old_hit.id, 48)
new_post = publish_post(PostCreate(body="posted just now"), db8, mia)
check("a stale favourite decays below a fresh post",
      [p.id for p in popular(db8, mia)][0] == new_post.id)

# ...but enough likes still outrank recency, or the tab would just be "latest" with extra steps.
big_hit = publish_post(PostCreate(body="a real hit"), db8, mia)
like_n(db8, big_hit.id, 20, "big")
age_post(db8, big_hit.id, 12)
check("enough likes still beat recency", [p.id for p in popular(db8, mia)][0] == big_hit.id)

# With nothing liked at all, popular should read as newest-first rather than arriving empty.
db9 = fresh_db()
nina, _ = mk_user(db9, "nina")
first = publish_post(PostCreate(body="one"), db9, nina)
second = publish_post(PostCreate(body="two"), db9, nina)
third_post = publish_post(PostCreate(body="three"), db9, nina)
check("an unliked feed degrades to newest-first",
      [p.id for p in popular(db9, nina)] == [third_post.id, second.id, first.id])

check("popular respects the limit", len(popular(db9, nina, limit=2)) == 2)
check("popular pages by offset",
      [p.id for p in popular(db9, nina, limit=2, offset=2)] == [first.id])
check("offset past the end returns nothing", popular(db9, nina, offset=99) == [])

publish_post(PostCreate(body="untagged post"), db9, nina)
publish_post(PostCreate(body="tagged $TSLA post"), db9, nina)
tesla = popular(db9, nina, symbol="TSLA")
check("popular honours the symbol filter", len(tesla) == 1)
check("and filters case-insensitively", len(popular(db9, nina, symbol="tsla")) == 1)
check("popular carries like counts", all(hasattr(p, "like_count") for p in popular(db9, nina)))

# ---------------------------------------------------------------------------
print("\n[11] The following feed")
# ---------------------------------------------------------------------------
db10 = fresh_db()
me, _ = mk_user(db10, "me")
followed, _ = mk_user(db10, "followed")
stranger, _ = mk_user(db10, "stranger")
mk_follow(db10, me, followed)

mine_post = publish_post(PostCreate(body="my own $AAPL take"), db10, me)
theirs = publish_post(PostCreate(body="a followee's $AAPL take"), db10, followed)
strangers = publish_post(PostCreate(body="a stranger's $AAPL take"), db10, stranger)

ids = {p.id for p in following(db10, me)}
check("a followee's posts appear", theirs.id in ids)
check("your own posts appear", mine_post.id in ids)
check("a stranger's posts don't", strangers.id not in ids)
check("exactly those two", ids == {mine_post.id, theirs.id})

check("the stranger sees only their own", {p.id for p in following(db10, stranger)} == {strangers.id})
check("following is one-way", mine_post.id not in {p.id for p in following(db10, followed)})

check("following is newest-first", [p.id for p in following(db10, me)] == [theirs.id, mine_post.id])
check("following pages by cursor",
      [p.id for p in following(db10, me, before_id=theirs.id)] == [mine_post.id])
check("following honours the symbol filter", len(following(db10, me, symbol="AAPL")) == 2)
check("and excludes untagged posts under a filter",
      following(db10, me, symbol="ZZZZ") == [])

# Unfollowing takes the posts back out of the feed.
db10.delete(db10.scalar(select(Follow).where(Follow.follower_id == me.id)))
db10.commit()
check("unfollowing removes their posts", {p.id for p in following(db10, me)} == {mine_post.id})

# The latest feed is unaffected by who you follow.
check("latest still shows everyone", len(latest(db10, me)) == 3)

print(f"\n==== {passed} passed, {failed} failed ====")
sys.exit(1 if failed else 0)
