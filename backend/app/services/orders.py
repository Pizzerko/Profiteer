"""Resting-order engine: evaluate limit/stop/trailing orders and fill them via the trading path.

A single background thread (started from the app lifespan) polls open orders every
`settings.order_poll_interval_seconds`. When the market price crosses an order's trigger during a
tradeable session, the order is filled by calling `execute_trade` — the same code path as a manual
market order — so all the cash/holdings/margin logic is shared.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.order import Order
from app.models.portfolio import Portfolio
from app.services.market_data import MarketDataError, get_provider
from app.services.trading import (
    _TRADEABLE_STATES,
    TradingError,
    execute_trade,
    value_portfolio,
)

logger = logging.getLogger("app.orders")


def evaluate_order(order: Order, price: float) -> bool:
    """Whether `order` should fill at the current `price`. Updates the trailing peak as a side effect.

    Callers must have already confirmed the session is tradeable.
    """
    if order.order_type == "limit":
        if order.side == "buy":
            return price <= order.limit_price
        return price >= order.limit_price

    if order.order_type == "stop":
        if order.side == "buy":
            return price >= order.stop_price
        return price <= order.stop_price

    if order.order_type == "trailing_stop":
        trail = (order.trail_percent or 0) / 100.0
        if order.side == "sell":
            # Protect a long: track the high-water mark, sell if price falls `trail` below it.
            order.peak_price = price if order.peak_price is None else max(order.peak_price, price)
            return price <= order.peak_price * (1 - trail)
        # Buy trailing stop: track the low-water mark, buy if price rises `trail` above it.
        order.peak_price = price if order.peak_price is None else min(order.peak_price, price)
        return price >= order.peak_price * (1 + trail)

    return False


def process_open_orders(db: Session) -> None:
    """One poll pass: fill any open orders whose trigger is met in a tradeable session."""
    orders = list(db.scalars(select(Order).where(Order.status == "open")))
    if not orders:
        return

    provider = get_provider()
    quotes: dict[str, object] = {}  # symbol -> Quote (fetched once per symbol per pass)
    dirty = False

    for order in orders:
        if order.symbol not in quotes:
            try:
                quotes[order.symbol] = provider.get_quote(order.symbol)
            except MarketDataError:
                quotes[order.symbol] = None
        quote = quotes[order.symbol]
        if quote is None or quote.market_state not in _TRADEABLE_STATES:
            continue  # can't price it or market closed — leave the order open

        price = quote.effective_price if quote.effective_price else quote.price
        if price is None or price <= 0:
            continue

        triggered = evaluate_order(order, price)  # may update peak_price
        dirty = True  # peak_price and/or status changed; persist at the end
        if not triggered:
            continue

        try:
            trade = execute_trade(db, order.portfolio, order.symbol, order.side, order.quantity)
            order.status = "filled"
            order.filled_at = datetime.now(timezone.utc)
            order.fill_price = trade.price
            order.filled_trade_id = trade.id
            logger.info("Filled order %s (%s %s %s @ %s)", order.id, order.side,
                        order.quantity, order.symbol, trade.price)
        except TradingError as exc:
            # Unfillable (insufficient buying power / shares, market closed, locked). Don't retry.
            order.status = "rejected"
            order.note = str(exc)[:255]
            logger.info("Rejected order %s: %s", order.id, exc)

    if dirty:
        db.commit()


def monitor_bankruptcies(db: Session) -> None:
    """Lock any portfolio whose total value has fallen to ≤ 0 (e.g. a short gone against it).

    A wiped-out portfolio is frozen and its open orders cancelled; the user resets to continue.
    """
    changed = False
    for p in db.scalars(select(Portfolio).where(Portfolio.locked.is_(False))):
        if not p.holdings:
            continue  # all-cash can't be ≤ 0
        if value_portfolio(db, p).total_value <= 1e-9:
            p.locked = True
            for o in p.orders:
                if o.status == "open":
                    o.status = "cancelled"
                    o.note = "Portfolio wiped out"
            logger.info("Locked portfolio %s (wiped out)", p.id)
            changed = True
    if changed:
        db.commit()


class _OrderPoller:
    """A daemon thread that runs `process_open_orders` on an interval until stopped."""

    def __init__(self, interval: int) -> None:
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="order-poller", daemon=True)
        self._thread.start()
        logger.info("Order poller started (interval=%ss)", self._interval)

    def _run(self) -> None:
        while not self._stop.is_set():
            db = SessionLocal()
            try:
                process_open_orders(db)
                monitor_bankruptcies(db)
            except Exception:  # noqa: BLE001 — never let one bad cycle kill the thread
                logger.exception("Order poll cycle failed")
                db.rollback()
            finally:
                db.close()
            self._stop.wait(self._interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        logger.info("Order poller stopped")


_poller: _OrderPoller | None = None


def start_order_poller() -> None:
    global _poller
    if _poller is None:
        _poller = _OrderPoller(settings.order_poll_interval_seconds)
        _poller.start()


def stop_order_poller() -> None:
    global _poller
    if _poller is not None:
        _poller.stop()
        _poller = None
