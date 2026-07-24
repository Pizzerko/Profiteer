"""Paper-trading logic: execute buys/sells and value a portfolio.

All mutations happen inside the caller's DB session/transaction. Trades execute at
the latest price fetched from the market data provider (no market-hours enforcement in v1).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.holding import Holding
from app.models.portfolio import Portfolio
from app.models.trade import Trade
from app.schemas.portfolio import (
    HoldingOut,
    PortfolioHistoryPoint,
    PortfolioHistoryResponse,
    PortfolioOut,
)
from app.services.market_data import MarketDataError, get_provider


class TradingError(Exception):
    """Raised on invalid trades (insufficient cash/shares, bad price)."""


# Orders are only accepted while a US session is open: pre-market, regular, or
# after-hours. Anything else (overnight, weekends, holidays) reports CLOSED/None.
_TRADEABLE_STATES = {"PRE", "REGULAR", "POST"}
_MARKET_CLOSED_MESSAGE = (
    "The market is closed. Trading is available during pre-market (4:00 AM–9:30 AM ET), "
    "regular hours (9:30 AM–4:00 PM ET), and after-hours (4:00 PM–8:00 PM ET)."
)


def execute_trade(db: Session, portfolio: Portfolio, symbol: str, side: str, quantity: float) -> Trade:
    symbol = symbol.upper().strip()
    if quantity <= 0:
        raise TradingError("Quantity must be greater than zero.")

    try:
        quote = get_provider().get_quote(symbol)
    except MarketDataError as exc:
        raise TradingError(str(exc)) from exc

    # Reject orders when no session is open. Fail closed on an unknown state so we
    # never let an overnight order slip through on a flaky market-state probe.
    if quote.market_state not in _TRADEABLE_STATES:
        raise TradingError(_MARKET_CLOSED_MESSAGE)

    # Fill at the extended-hours price during PRE/POST, else the regular price.
    price = quote.effective_price if quote.effective_price else quote.price
    if price is None or price <= 0:
        raise TradingError(f"No tradeable price available for '{symbol}'.")

    if side == "buy":
        _execute_buy(db, portfolio, symbol, quantity, price)
    elif side == "sell":
        _execute_sell(db, portfolio, symbol, quantity, price)
    else:
        raise TradingError("Side must be 'buy' or 'sell'.")

    trade = Trade(
        portfolio_id=portfolio.id, symbol=symbol, side=side, quantity=quantity, price=price
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade


def _get_holding(db: Session, portfolio_id: int, symbol: str) -> Holding | None:
    return db.scalar(
        select(Holding).where(Holding.portfolio_id == portfolio_id, Holding.symbol == symbol)
    )


def _execute_buy(db: Session, portfolio: Portfolio, symbol: str, quantity: float, price: float) -> None:
    cost = quantity * price
    if cost > portfolio.cash_balance + 1e-9:
        raise TradingError(
            f"Insufficient cash: need ${cost:,.2f}, have ${portfolio.cash_balance:,.2f}."
        )
    portfolio.cash_balance -= cost

    holding = _get_holding(db, portfolio.id, symbol)
    if holding is None:
        holding = Holding(portfolio_id=portfolio.id, symbol=symbol, quantity=quantity, avg_cost=price)
        db.add(holding)
    else:
        total_cost = holding.avg_cost * holding.quantity + cost
        holding.quantity += quantity
        holding.avg_cost = total_cost / holding.quantity


def _execute_sell(db: Session, portfolio: Portfolio, symbol: str, quantity: float, price: float) -> None:
    holding = _get_holding(db, portfolio.id, symbol)
    if holding is None or holding.quantity + 1e-9 < quantity:
        held = holding.quantity if holding else 0
        raise TradingError(f"Insufficient shares: trying to sell {quantity}, hold {held}.")

    portfolio.cash_balance += quantity * price
    holding.quantity -= quantity
    if holding.quantity <= 1e-9:
        db.delete(holding)


def value_portfolio(db: Session, portfolio: Portfolio) -> PortfolioOut:
    """Compute live valuation and P&L for a portfolio."""
    provider = get_provider()
    holdings_out: list[HoldingOut] = []
    holdings_value = 0.0

    for h in portfolio.holdings:
        current_price: float | None = None
        try:
            q = provider.get_quote(h.symbol)
            current_price = q.effective_price if q.effective_price else q.price
        except MarketDataError:
            current_price = None

        cost_basis = h.avg_cost * h.quantity
        market_value = current_price * h.quantity if current_price is not None else None
        unrealized_pl = market_value - cost_basis if market_value is not None else None
        unrealized_pl_percent = (
            (unrealized_pl / cost_basis * 100) if unrealized_pl is not None and cost_basis else None
        )
        if market_value is not None:
            holdings_value += market_value

        holdings_out.append(
            HoldingOut(
                symbol=h.symbol,
                quantity=h.quantity,
                avg_cost=h.avg_cost,
                current_price=current_price,
                market_value=market_value,
                cost_basis=cost_basis,
                unrealized_pl=unrealized_pl,
                unrealized_pl_percent=unrealized_pl_percent,
            )
        )

    total_value = portfolio.cash_balance + holdings_value
    total_pl = total_value - portfolio.starting_balance
    total_pl_percent = (
        (total_pl / portfolio.starting_balance * 100) if portfolio.starting_balance else 0.0
    )

    holdings_out.sort(key=lambda x: (x.market_value or 0), reverse=True)

    return PortfolioOut(
        id=portfolio.id,
        name=portfolio.name,
        cash_balance=portfolio.cash_balance,
        starting_balance=portfolio.starting_balance,
        holdings_value=holdings_value,
        total_value=total_value,
        total_pl=total_pl,
        total_pl_percent=total_pl_percent,
        holdings=holdings_out,
    )


def portfolio_value_history(
    db: Session, portfolio: Portfolio, range_: str
) -> PortfolioHistoryResponse:
    """Reconstruct daily total portfolio value over a range.

    We have no historical snapshots, so we rebuild each day's value from the trade log:
    cash starts at `starting_balance` and moves with each executed buy/sell, and holdings are
    priced at that day's regular-session close (from the market-data provider). The final point
    is replaced with the live valuation so the chart ends exactly at the current total value.
    """
    provider = get_provider()
    trades = list(
        db.scalars(
            select(Trade)
            .where(Trade.portfolio_id == portfolio.id)
            .order_by(Trade.executed_at)
        )
    )
    symbols = sorted({t.symbol for t in trades})

    # symbol -> {day "YYYY-MM-DD": close}; day -> a representative ISO string for the axis.
    closes_by_symbol: dict[str, dict[str, float]] = {}
    day_iso: dict[str, str] = {}
    for sym in symbols:
        try:
            hist = provider.get_history(sym, range_, False)
        except MarketDataError:
            continue
        day_map: dict[str, float] = {}
        for p in hist.points:
            day = p.date[:10]
            day_map[day] = p.close
            day_iso.setdefault(day, p.date)
        if day_map:
            closes_by_symbol[sym] = day_map

    created_day = portfolio.created_at.date().isoformat()
    days = sorted(d for d in day_iso if d >= created_day)
    if not days:
        return PortfolioHistoryResponse(range=range_, points=[])

    points: list[PortfolioHistoryPoint] = []
    last_close: dict[str, float] = {}  # forward-filled close per symbol
    for day in days:
        # Cash + net share counts from every trade executed on/before this day.
        cash = portfolio.starting_balance
        qty: dict[str, float] = {}
        for t in trades:
            if t.executed_at.date().isoformat() > day:
                break  # trades are ordered by executed_at
            signed = t.quantity if t.side == "buy" else -t.quantity
            cash += -t.quantity * t.price if t.side == "buy" else t.quantity * t.price
            qty[t.symbol] = qty.get(t.symbol, 0.0) + signed

        for sym, day_map in closes_by_symbol.items():
            if day in day_map:
                last_close[sym] = day_map[day]

        holdings_val = 0.0
        for sym, q in qty.items():
            close = last_close.get(sym)
            if close is not None and abs(q) > 1e-9:
                holdings_val += q * close
        points.append(PortfolioHistoryPoint(date=day_iso[day], value=cash + holdings_val))

    # End the series at the live total value so it matches the dashboard's Total Value card.
    live_value = value_portfolio(db, portfolio).total_value
    today_day = datetime.now(timezone.utc).date().isoformat()
    if points[-1].date[:10] == today_day:
        points[-1] = PortfolioHistoryPoint(date=points[-1].date, value=live_value)
    else:
        points.append(PortfolioHistoryPoint(date=f"{today_day}T00:00:00", value=live_value))

    return PortfolioHistoryResponse(range=range_, points=points)
