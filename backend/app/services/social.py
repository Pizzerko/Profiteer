"""Social projections: what one user is allowed to see about another.

Every function here builds a *public* shape from private data. The projection is the privacy
boundary, so it lives in one place rather than being re-derived per route — see the module docstring
of `schemas/social.py` for exactly what's withheld (email, dollar amounts, position sizes).
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.competition import Competition
from app.models.follow import Follow
from app.models.option_trade import OptionTrade
from app.models.portfolio import Portfolio
from app.models.trade import Trade
from app.models.user import User
from app.schemas.social import (
    CompetitionRecord,
    FeedItem,
    PublicHolding,
    PublicProfile,
    PublicUser,
)
from app.services.competitions import as_utc, competition_status, standings
from app.services.trading import value_portfolio


def public_portfolio_of(db: Session, user: User) -> Portfolio | None:
    """The portfolio `user` publishes, or None.

    `public_portfolio_id` carries no DB-level foreign key (see the comment on the model), so this
    re-checks that the id still resolves to a portfolio the user actually owns. A stale or
    tampered-with id reads as "no public portfolio" rather than leaking someone else's book.
    """
    if user.public_portfolio_id is None:
        return None
    p = db.get(Portfolio, user.public_portfolio_id)
    if p is None or p.user_id != user.id:
        return None
    return p


def follow_counts(db: Session, user_id: int) -> tuple[int, int]:
    """(followers, following) for a user."""
    followers = db.scalar(
        select(func.count(Follow.id)).where(Follow.followee_id == user_id)
    ) or 0
    following = db.scalar(
        select(func.count(Follow.id)).where(Follow.follower_id == user_id)
    ) or 0
    return followers, following


def is_following(db: Session, follower_id: int, followee_id: int) -> bool:
    return db.scalar(
        select(Follow.id).where(
            Follow.follower_id == follower_id, Follow.followee_id == followee_id
        )
    ) is not None


def build_public_user(db: Session, target: User, viewer: User) -> PublicUser:
    followers, following = follow_counts(db, target.id)
    return PublicUser(
        id=target.id,
        username=target.username,
        display_name=target.display_name,
        bio=target.bio,
        created_at=as_utc(target.created_at),
        follower_count=followers,
        following_count=following,
        is_following=target.id != viewer.id and is_following(db, viewer.id, target.id),
        is_me=target.id == viewer.id,
    )


def search_users(db: Session, q: str, viewer: User, limit: int = 20) -> list[PublicUser]:
    """Users whose username or display name contains `q` (case-insensitive), excluding the viewer."""
    term = f"%{q.strip().lower()}%"
    rows = db.scalars(
        select(User)
        .where(
            User.id != viewer.id,
            or_(
                func.lower(User.username).like(term),
                func.lower(func.coalesce(User.display_name, "")).like(term),
            ),
        )
        .order_by(User.username)
        .limit(limit)
    )
    return [build_public_user(db, u, viewer) for u in rows]


def _public_holdings(db: Session, portfolio: Portfolio) -> tuple[list[PublicHolding], float | None]:
    """(holdings, total_return_percent) for a published portfolio.

    Positions are reduced to symbol + weight + return: `weight_percent` is the position's share of
    gross market value, so it conveys concentration without revealing quantity or dollar value.
    """
    valued = value_portfolio(db, portfolio)
    gross = sum(abs(h.market_value) for h in valued.holdings if h.market_value is not None)
    gross += sum(
        abs(p.market_value) for p in valued.option_positions if p.market_value is not None
    )

    out: list[PublicHolding] = []
    for h in valued.holdings:
        weight = (
            abs(h.market_value) / gross * 100.0
            if h.market_value is not None and gross > 0
            else None
        )
        out.append(
            PublicHolding(
                symbol=h.symbol,
                weight_percent=weight,
                unrealized_pl_percent=h.unrealized_pl_percent,
            )
        )
    for p in valued.option_positions:
        weight = (
            abs(p.market_value) / gross * 100.0
            if p.market_value is not None and gross > 0
            else None
        )
        out.append(
            PublicHolding(
                symbol=f"{p.underlying} {p.strike:g}{p.option_type[0].upper()}",
                weight_percent=weight,
                unrealized_pl_percent=p.unrealized_pl_percent,
            )
        )
    out.sort(key=lambda x: x.weight_percent or 0, reverse=True)
    return out, valued.total_pl_percent


def _competition_records(db: Session, target: User) -> list[CompetitionRecord]:
    """The user's competition history, with their rank in each."""
    entries = db.scalars(
        select(Portfolio).where(
            Portfolio.user_id == target.id, Portfolio.competition_id.is_not(None)
        )
    ).all()

    records: list[CompetitionRecord] = []
    for entry in entries:
        comp: Competition | None = entry.competition
        if comp is None:
            continue
        rows = standings(db, comp)
        mine = next((r for r in rows if r[0].id == entry.id), None)
        records.append(
            CompetitionRecord(
                competition_id=comp.id,
                name=comp.name,
                status=competition_status(comp),
                return_percent=mine[1] if mine else None,
                rank=mine[2] if mine else None,
                entrants=len(rows),
            )
        )
    records.sort(key=lambda r: r.competition_id, reverse=True)
    return records


def build_public_profile(db: Session, target: User, viewer: User) -> PublicProfile:
    base = build_public_user(db, target, viewer)
    portfolio = public_portfolio_of(db, target)
    holdings: list[PublicHolding] = []
    total_return: float | None = None
    if portfolio is not None:
        holdings, total_return = _public_holdings(db, portfolio)

    return PublicProfile(
        **base.model_dump(),
        portfolio_name=portfolio.name if portfolio else None,
        total_return_percent=total_return,
        holdings=holdings,
        competitions=_competition_records(db, target),
    )


def _option_label(t: OptionTrade) -> str:
    return f"{t.underlying} ${t.strike:g} {t.option_type} {t.expiration.isoformat()}"


def build_feed(db: Session, viewer: User, limit: int = 30) -> list[FeedItem]:
    """Recent trades from the people `viewer` follows, newest first.

    Only each followee's *published* portfolio is sourced — trades in their other portfolios stay
    private, and competition activity is surfaced through standings instead. Option settlements are
    excluded: they're an automatic expiry event, not something the user did.
    """
    followee_ids = select(Follow.followee_id).where(Follow.follower_id == viewer.id)
    followees = db.scalars(select(User).where(User.id.in_(followee_ids))).all()

    owner_by_portfolio: dict[int, User] = {}
    for f in followees:
        p = public_portfolio_of(db, f)
        if p is not None:
            owner_by_portfolio[p.id] = f
    if not owner_by_portfolio:
        return []

    portfolio_ids = list(owner_by_portfolio)
    items: list[FeedItem] = []

    for t in db.scalars(
        select(Trade)
        .where(Trade.portfolio_id.in_(portfolio_ids))
        .order_by(Trade.executed_at.desc())
        .limit(limit)
    ):
        owner = owner_by_portfolio[t.portfolio_id]
        items.append(
            FeedItem(
                id=f"t{t.id}",
                kind="stock",
                username=owner.username,
                display_name=owner.display_name,
                symbol=t.symbol,
                label=t.symbol,
                side=t.side,
                price=t.price,
                executed_at=as_utc(t.executed_at),
            )
        )

    for ot in db.scalars(
        select(OptionTrade)
        .where(OptionTrade.portfolio_id.in_(portfolio_ids), OptionTrade.action != "settle")
        .order_by(OptionTrade.executed_at.desc())
        .limit(limit)
    ):
        owner = owner_by_portfolio[ot.portfolio_id]
        items.append(
            FeedItem(
                id=f"o{ot.id}",
                kind="option",
                username=owner.username,
                display_name=owner.display_name,
                symbol=ot.underlying,
                label=_option_label(ot),
                side=ot.action,
                price=ot.price,
                executed_at=as_utc(ot.executed_at),
            )
        )

    items.sort(key=lambda i: i.executed_at, reverse=True)
    return items[:limit]
