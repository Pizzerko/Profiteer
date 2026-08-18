"""Competition engine: derived status, the trading time-gate, standings, and finalization.

A competition's state is never stored — it's computed from `starts_at`/`ends_at` every time it's
asked for, so it can't drift out of sync with the clock. Three consequences worth knowing:

* Entries can only trade while the competition is *active*. That rule is enforced in
  `assert_competition_open`, which the two trade choke points (`services.trading.execute_trade` and
  `services.options.place_option_order`) call before touching cash — so market orders, resting-order
  fills, and option orders are all covered by one check.
* When a competition ends, `finalize_ended_competitions` snapshots each entry's total value into
  `Portfolio.final_value` and cancels its open resting orders. Standings then read the snapshot
  instead of live prices, so final results stay put.
* Standings rank by return percent. Since every entry starts from the same `starting_cash`, that
  ordering is identical to ranking by total value — without publishing a dollar figure.

Three more rules govern who may enter and what a result is worth:

* **Timeframe.** A contest runs for a day, a week or a month; `ends_at` is derived from
  `starts_at` + the timeframe rather than picked freehand. Three comparable buckets is what makes a
  per-timeframe win record meaningful — "3 weekly wins" says something, "3 wins over arbitrary
  windows" doesn't.
* **Start gate.** A contest must begin inside a regular trading session, so nobody's entry sits
  frozen through a weekend before anyone can place a trade.
* **Visibility.** Public contests are open to anyone; private ones are invite-only lobbies where
  `assert_can_join` requires an invite from the host.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.competition import Competition
from app.models.competition_invite import CompetitionInvite
from app.models.notification import Notification
from app.models.portfolio import Portfolio
from app.services.notifications import notify
from app.services.trading import TradingError, value_portfolio

logger = logging.getLogger("app.competitions")

UPCOMING = "upcoming"
ACTIVE = "active"
ENDED = "ended"

PUBLIC = "public"
PRIVATE = "private"
VISIBILITIES = (PUBLIC, PRIVATE)

DAY = "day"
WEEK = "week"
MONTH = "month"
# The only three contest lengths. Deliberately calendar-naive fixed spans: a "day" contest is 24h
# from its start, not "until the next close", so two day-contests started at different times are
# still the same length and their winners are comparable.
TIMEFRAMES: dict[str, timedelta] = {
    DAY: timedelta(days=1),
    WEEK: timedelta(days=7),
    MONTH: timedelta(days=30),
}

# A solo entrant is not a winner. A ranked contest only contributes to someone's record once there
# was somebody to beat.
MIN_RANKED_ENTRANTS = 2

_ET = ZoneInfo("America/New_York")
_SESSION_OPEN = time(9, 30)
_SESSION_CLOSE = time(16, 0)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    """Normalize to tz-aware UTC. Datetimes round-trip through SQLite as naive (stored as UTC)."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def competition_status(comp: Competition, now: datetime | None = None) -> str:
    """Derive status from the clock: upcoming → active → ended."""
    now = now or _utcnow()
    if now < as_utc(comp.starts_at):
        return UPCOMING
    if now > as_utc(comp.ends_at):
        return ENDED
    return ACTIVE


# ---------------------------------------------------------------------------
# Timeframes and the start gate
# ---------------------------------------------------------------------------
def ends_at_for(starts_at: datetime, timeframe: str) -> datetime:
    """The derived close of a contest. Raises ValueError on an unknown timeframe."""
    span = TIMEFRAMES.get(timeframe)
    if span is None:
        raise ValueError(f"Timeframe must be one of {', '.join(TIMEFRAMES)}.")
    return as_utc(starts_at) + span


def market_is_open_at(dt: datetime) -> bool:
    """Whether `dt` falls inside a regular US session (Mon–Fri, 9:30–16:00 ET).

    Weekday-and-clock only: this does not know about market holidays, so a contest can be scheduled
    to start on Thanksgiving. That's a deliberate limit rather than an oversight — the holiday
    calendar isn't available offline, and the cost of the gap is a contest that opens on a closed
    day, not a bad trade: the trading choke points check the *live* market state independently
    (`services.trading._TRADEABLE_STATES`), so no order fills on a closed market either way.
    """
    et = as_utc(dt).astimezone(_ET)
    if et.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        return False
    return _SESSION_OPEN <= et.time() < _SESSION_CLOSE


def assert_startable_at(starts_at: datetime) -> None:
    """Reject a start time outside regular trading hours."""
    if market_is_open_at(starts_at):
        return
    et = as_utc(starts_at).astimezone(_ET)
    raise TradingError(
        "Competitions can only start while the market is open (Mon–Fri, 9:30–16:00 ET) — "
        f"{et:%a %b %d at %H:%M} ET is outside a trading session."
    )


# ---------------------------------------------------------------------------
# Visibility and invites
# ---------------------------------------------------------------------------
def invite_for(db: Session, competition_id: int, user_id: int) -> CompetitionInvite | None:
    return db.scalar(
        select(CompetitionInvite).where(
            CompetitionInvite.competition_id == competition_id,
            CompetitionInvite.invitee_id == user_id,
        )
    )


def has_entry(comp: Competition, user_id: int) -> bool:
    return any(e.user_id == user_id for e in comp.entries)


def can_view(db: Session, comp: Competition, user_id: int) -> bool:
    """Whether a user may see a competition at all.

    Public contests are visible to everyone. A private one is visible only to its host, the people
    they invited, and anyone already entered — so a private lobby never shows up in a stranger's
    list, not even as a name they can't join.
    """
    if comp.visibility == PUBLIC:
        return True
    if comp.creator_id == user_id or has_entry(comp, user_id):
        return True
    return invite_for(db, comp.id, user_id) is not None


def assert_can_join(db: Session, comp: Competition, user_id: int) -> None:
    """Raise unless this user is allowed through the door of a private lobby."""
    if comp.visibility != PRIVATE:
        return
    if comp.creator_id == user_id:
        return  # the host is always welcome in their own lobby
    invite = invite_for(db, comp.id, user_id)
    if invite is None or invite.status == "declined":
        raise TradingError(
            f"'{comp.name}' is a private competition — you need an invite from the host to join."
        )


# ---------------------------------------------------------------------------
# Win records
# ---------------------------------------------------------------------------
def counts_as_win(comp: Competition, rank: int | None, entrants: int) -> bool:
    """Whether finishing at `rank` in `comp` belongs on the winner's public record.

    Four conditions, all necessary: the contest was ranked (the host opted in), it's over, it had
    somebody to beat, and this entry finished first. Ties share rank 1, so a two-way tie counts as
    a win for both — the alternative is a rank the standings themselves don't show.
    """
    return (
        comp.ranked
        and competition_status(comp) == ENDED
        and entrants >= MIN_RANKED_ENTRANTS
        and rank == 1
    )


def empty_win_record() -> dict[str, int]:
    return {tf: 0 for tf in TIMEFRAMES}


def assert_competition_open(portfolio: Portfolio) -> None:
    """Reject trades on a competition entry outside the contest window.

    A no-op for ordinary portfolios. Called from the trade choke points, so it applies equally to
    manual market orders, poller-triggered limit/stop fills, and option orders.
    """
    comp = portfolio.competition
    if comp is None:
        return
    status = competition_status(comp)
    if status == UPCOMING:
        raise TradingError(
            f"'{comp.name}' hasn't started yet — trading opens "
            f"{as_utc(comp.starts_at):%b %d, %Y at %H:%M} UTC."
        )
    if status == ENDED:
        raise TradingError(
            f"'{comp.name}' has ended — this entry is now read-only."
        )


def entry_value(db: Session, entry: Portfolio) -> float:
    """An entry's total value: the frozen snapshot once ended, else a live valuation."""
    if entry.final_value is not None:
        return entry.final_value
    return value_portfolio(db, entry).total_value


def entry_return_percent(db: Session, entry: Portfolio) -> float:
    """Percent return against the entry's starting balance."""
    base = entry.starting_balance
    if not base:
        return 0.0
    return (entry_value(db, entry) - base) / base * 100.0


def standings(db: Session, comp: Competition) -> list[tuple[Portfolio, float, int]]:
    """(entry, return_percent, rank) ordered best-first. Ties share a rank."""
    scored = [(e, entry_return_percent(db, e)) for e in comp.entries]
    scored.sort(key=lambda row: row[1], reverse=True)

    out: list[tuple[Portfolio, float, int]] = []
    last_pct: float | None = None
    last_rank = 0
    for i, (entry, pct) in enumerate(scored, start=1):
        if last_pct is not None and abs(pct - last_pct) < 1e-9:
            rank = last_rank  # tie → same rank as the entry above
        else:
            rank = i
            last_pct, last_rank = pct, rank
        out.append((entry, pct, rank))
    return out


def _notify_results(db: Session, comp: Competition) -> None:
    """Tell every entrant where they finished. Called once, as a competition is frozen."""
    rows = standings(db, comp)
    entrants = len(rows)
    for entry, pct, rank in rows:
        won = counts_as_win(comp, rank, entrants)
        if won:
            title = f"You won {comp.name}!"
        else:
            title = f"{comp.name} has ended"
        placing = f"You finished #{rank} of {entrants} with {pct:+.2f}%."
        if won and comp.ranked:
            placing += f" Added to your {comp.timeframe} record."
        notify(
            db,
            user_id=entry.user_id,
            kind=Notification.KIND_COMPETITION_RESULT,
            title=title,
            body=placing,
            competition_id=comp.id,
        )


def finalize_ended_competitions(db: Session) -> None:
    """Freeze results for competitions whose window has closed.

    Snapshots each entry's total value and cancels its resting orders, then notifies every entrant
    of their placing. Runs on the order poller, so the snapshot is taken within one poll interval of
    `ends_at` rather than exactly at it.

    Idempotent, and that matters twice over here: an entry with `final_value` already set is
    skipped, and the result notifications only fire for a competition where this pass actually froze
    something — so a contest can't announce its results a second time on the next poll.
    """
    now = _utcnow()
    changed = False
    for comp in db.scalars(select(Competition)):
        if competition_status(comp, now) != ENDED:
            continue
        froze_any = False
        for entry in comp.entries:
            if entry.final_value is not None:
                continue
            entry.final_value = value_portfolio(db, entry).total_value
            for o in entry.orders:
                if o.status == "open":
                    o.status = "cancelled"
                    o.note = "Competition ended"
            for oo in entry.option_orders:
                if oo.status == "open":
                    oo.status = "cancelled"
                    oo.note = "Competition ended"
            logger.info(
                "Finalized competition %s entry %s at %.2f", comp.id, entry.id, entry.final_value
            )
            froze_any = True
        if froze_any:
            _notify_results(db, comp)
            changed = True
    if changed:
        db.commit()
