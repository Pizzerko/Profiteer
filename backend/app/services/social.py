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
    TradingStats,
    WinRecord,
)
from app.services.competitions import (
    as_utc,
    competition_status,
    counts_as_win,
    standings,
)
from app.services.market_data import MarketDataError
from app.services.trading import portfolio_value_history, value_portfolio


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


def _competition_records(db: Session, target: User) -> tuple[list[CompetitionRecord], WinRecord]:
    """The user's competition history and their win record, in one pass.

    Both come out of the same `standings` walk on purpose. Ranking an entry means valuing every
    other entry in the contest, so computing the record separately would double the most expensive
    part of rendering a profile to arrive at numbers derived from the very rows already in hand.
    """
    entries = db.scalars(
        select(Portfolio).where(
            Portfolio.user_id == target.id, Portfolio.competition_id.is_not(None)
        )
    ).all()

    records: list[CompetitionRecord] = []
    wins = WinRecord()
    for entry in entries:
        comp: Competition | None = entry.competition
        if comp is None:
            continue
        rows = standings(db, comp)
        mine = next((r for r in rows if r[0].id == entry.id), None)
        rank = mine[2] if mine else None
        won = counts_as_win(comp, rank, len(rows))
        if won and hasattr(wins, comp.timeframe):
            setattr(wins, comp.timeframe, getattr(wins, comp.timeframe) + 1)
        records.append(
            CompetitionRecord(
                competition_id=comp.id,
                name=comp.name,
                status=competition_status(comp),
                timeframe=comp.timeframe,
                ranked=comp.ranked,
                return_percent=mine[1] if mine else None,
                rank=rank,
                entrants=len(rows),
                won=won,
            )
        )
    records.sort(key=lambda r: r.competition_id, reverse=True)
    return records, wins


def _personal_portfolios(db: Session, target: User) -> list[Portfolio]:
    """The user's own portfolios — competition entries excluded, per user request."""
    return list(
        db.scalars(
            select(Portfolio).where(
                Portfolio.user_id == target.id, Portfolio.competition_id.is_(None)
            )
        )
    )


def _blended_window_pct(db: Session, portfolios: list[Portfolio], range_: str) -> float | None:
    """Dollar-weighted blended return over `range_`, across every portfolio, as a percentage.

    Summing each portfolio's start/end value first and taking one ratio (rather than averaging
    each portfolio's own percentage) means a big account moves the blend more than a small one —
    the same weighting `total_return_percent` on a single portfolio already implies.
    """
    start_total = 0.0
    end_total = 0.0
    for p in portfolios:
        try:
            hist = portfolio_value_history(db, p, range_)
        except MarketDataError:
            continue
        if not hist.points:
            continue
        start_total += hist.points[0].value
        end_total += hist.points[-1].value
    if start_total <= 0:
        return None
    return (end_total - start_total) / start_total * 100.0


def build_trading_stats(db: Session, target: User) -> TradingStats:
    """Blended P&L over a few windows, and win rate, across `target`'s personal portfolios."""
    portfolios = _personal_portfolios(db, target)
    if not portfolios:
        return TradingStats()

    portfolio_ids = [p.id for p in portfolios]
    wins = 0
    total = 0
    for realized_pl in db.scalars(
        select(Trade.realized_pl).where(
            Trade.portfolio_id.in_(portfolio_ids), Trade.realized_pl.is_not(None)
        )
    ):
        total += 1
        wins += realized_pl > 0
    for realized_pl in db.scalars(
        select(OptionTrade.realized_pl).where(
            OptionTrade.portfolio_id.in_(portfolio_ids), OptionTrade.realized_pl.is_not(None)
        )
    ):
        total += 1
        wins += realized_pl > 0

    return TradingStats(
        pnl_1d_percent=_blended_window_pct(db, portfolios, "1d"),
        pnl_3mo_percent=_blended_window_pct(db, portfolios, "3mo"),
        pnl_1y_percent=_blended_window_pct(db, portfolios, "1y"),
        win_rate_percent=(wins / total * 100.0) if total > 0 else None,
    )


def build_public_profile(db: Session, target: User, viewer: User) -> PublicProfile:
    base = build_public_user(db, target, viewer)
    portfolio = public_portfolio_of(db, target)
    holdings: list[PublicHolding] = []
    total_return: float | None = None
    if portfolio is not None:
        holdings, total_return = _public_holdings(db, portfolio)

    records, wins = _competition_records(db, target)
    # Hiding the record withholds the aggregate, not the history: individual standings are public,
    # so the contests stay listed. Owners always see their own record — otherwise the profile would
    # give no hint the toggle is on.
    show_wins = target.show_competition_stats or target.id == viewer.id
    is_owner = target.id == viewer.id
    show_stats = target.show_trading_stats or is_owner
    # Computing this walks the trade log against the market-data provider per portfolio per
    # window, so skip it entirely when the viewer isn't allowed to see the result anyway.
    trading_stats = build_trading_stats(db, target) if show_stats else None

    return PublicProfile(
        **base.model_dump(),
        portfolio_name=portfolio.name if portfolio else None,
        total_return_percent=total_return,
        holdings=holdings,
        competitions=records,
        wins=wins if show_wins else None,
        show_competition_stats=target.show_competition_stats,
        trading_stats=trading_stats,
        show_trading_stats=target.show_trading_stats,
    )


def option_label(t: OptionTrade) -> str:
    """How an option fill reads wherever it's shown: "AAPL $210 call 2026-09-18".

    Public (not `_`-prefixed) because the community feed renders attached option trades too, and
    the same contract must read identically in both places.
    """
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
                label=option_label(ot),
                side=ot.action,
                price=ot.price,
                executed_at=as_utc(ot.executed_at),
            )
        )

    items.sort(key=lambda i: i.executed_at, reverse=True)
    return items[:limit]
