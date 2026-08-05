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
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.competition import Competition
from app.models.portfolio import Portfolio
from app.services.trading import TradingError, value_portfolio

logger = logging.getLogger("app.competitions")

UPCOMING = "upcoming"
ACTIVE = "active"
ENDED = "ended"


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


def finalize_ended_competitions(db: Session) -> None:
    """Freeze results for competitions whose window has closed.

    Snapshots each entry's total value and cancels its resting orders. Runs on the order poller, so
    the snapshot is taken within one poll interval of `ends_at` rather than exactly at it.
    Idempotent: an entry with `final_value` already set is skipped.
    """
    now = _utcnow()
    changed = False
    for comp in db.scalars(select(Competition)):
        if competition_status(comp, now) != ENDED:
            continue
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
            changed = True
    if changed:
        db.commit()
