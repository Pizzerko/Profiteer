"""Paper-trading logic: execute buys/sells and value a portfolio.

All mutations happen inside the caller's DB session/transaction. Trades execute at
the latest price fetched from the market data provider (no market-hours enforcement in v1).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
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

    realized_pl: float | None = None
    if side == "buy":
        _execute_buy(db, portfolio, symbol, quantity, price)
    elif side == "sell":
        realized_pl = _execute_sell(db, portfolio, symbol, quantity, price)
    else:
        raise TradingError("Side must be 'buy' or 'sell'.")

    trade = Trade(
        portfolio_id=portfolio.id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        realized_pl=realized_pl,
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


def _execute_sell(db: Session, portfolio: Portfolio, symbol: str, quantity: float, price: float) -> float:
    holding = _get_holding(db, portfolio.id, symbol)
    if holding is None or holding.quantity + 1e-9 < quantity:
        held = holding.quantity if holding else 0
        raise TradingError(f"Insufficient shares: trying to sell {quantity}, hold {held}.")

    # Realized P&L = proceeds minus the cost basis of the shares sold, valued at the position's
    # average cost (which a sell leaves unchanged). Computed before we mutate the holding.
    realized_pl = quantity * (price - holding.avg_cost)

    portfolio.cash_balance += quantity * price
    holding.quantity -= quantity
    if holding.quantity <= 1e-9:
        db.delete(holding)
    return realized_pl


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

    # Sum of realized P&L locked in across every sell in this portfolio.
    realized_pl = db.scalar(
        select(func.coalesce(func.sum(Trade.realized_pl), 0.0)).where(
            Trade.portfolio_id == portfolio.id
        )
    ) or 0.0

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
        realized_pl=realized_pl,
        holdings=holdings_out,
    )


def _as_utc(dt: datetime) -> datetime:
    """Normalize to a tz-aware UTC datetime. Trade timestamps round-trip through SQLite as naive
    (but are stored as UTC); market-bar timestamps are tz-aware. This makes them comparable."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _trade_flows(trade: Trade) -> tuple[float, float]:
    """(cash_delta, quantity_delta) for applying a trade: buys spend cash and add shares."""
    if trade.side == "buy":
        return (-trade.quantity * trade.price, trade.quantity)
    return (trade.quantity * trade.price, -trade.quantity)


_BENCHMARK_SYMBOL = "^GSPC"  # S&P 500


def _apply_benchmark_daily(
    points: list[PortfolioHistoryPoint], starting_balance: float, range_: str, provider
) -> None:
    """Overlay each daily point with the S&P 500's value of the starting balance.

    Anchored so the benchmark starts at `starting_balance` on the first point, then tracks the
    index's cumulative return, forward-filling across days the index has no bar for.
    """
    if not points:
        return
    try:
        hist = provider.get_history(_BENCHMARK_SYMBOL, range_, False)
    except MarketDataError:
        return
    by_day = {p.date[:10]: p.close for p in hist.points}
    if not by_day:
        return
    earliest = by_day[min(by_day)]

    last: float | None = None
    first_close: float | None = None
    for p in points:
        day = p.date[:10]
        if day in by_day:
            last = by_day[day]
        elif last is None:
            last = earliest  # point predates the index window — anchor at its earliest close
        if first_close is None:
            first_close = last
        if last is not None and first_close:
            p.benchmark = starting_balance * (last / first_close)


def _apply_benchmark_intraday(
    points: list[PortfolioHistoryPoint], starting_balance: float, provider
) -> None:
    """Same overlay for today's intraday points, aligned by timestamp (forward-filled)."""
    if not points:
        return
    try:
        hist = provider.get_history(_BENCHMARK_SYMBOL, "1d", True)
    except MarketDataError:
        return
    bars: list[tuple[datetime, float]] = []
    for p in hist.points:
        try:
            bars.append((_as_utc(datetime.fromisoformat(p.date)), p.close))
        except ValueError:
            continue
    bars.sort()
    if not bars:
        return
    first_close = bars[0][1]

    j = 0
    last: float | None = None
    for p in points:
        try:
            ts = _as_utc(datetime.fromisoformat(p.date))
        except ValueError:
            continue
        while j < len(bars) and bars[j][0] <= ts:
            last = bars[j][1]
            j += 1
        p.benchmark = starting_balance * ((last or first_close) / first_close)


def _intraday_value_history(
    portfolio: Portfolio, trades: list[Trade], provider, benchmark: bool = False
) -> PortfolioHistoryResponse:
    """Reconstruct today's portfolio value from 1-minute bars.

    Holdings are valued at each minute's price (extended-hours included) and cash/share counts
    step forward through any trades executed during the session, so a mid-session buy/sell moves
    the line at the moment it filled rather than being back-applied to the whole day.
    """
    symbols = sorted({t.symbol for t in trades})

    # sym -> {tz-aware timestamp: close}; plus the union of all bar timestamps.
    price_at: dict[str, dict[datetime, float]] = {}
    all_ts: set[datetime] = set()
    for sym in symbols:
        try:
            hist = provider.get_history(sym, "1d", True)  # prepost=True for the 4AM–8PM axis
        except MarketDataError:
            continue
        series: dict[datetime, float] = {}
        for p in hist.points:
            try:
                ts = datetime.fromisoformat(p.date)
            except ValueError:
                continue
            series[ts] = p.close
            all_ts.add(ts)
        if series:
            price_at[sym] = series

    ordered_ts = sorted(all_ts)
    if not ordered_ts:
        return PortfolioHistoryResponse(range="1d", points=[])

    first_ts = _as_utc(ordered_ts[0])

    # Seed cash/shares from everything settled before the session's first bar; trades during the
    # session are stepped in as we walk the timeline.
    cash = portfolio.starting_balance
    qty: dict[str, float] = {}
    window: list[Trade] = []
    for t in trades:
        if _as_utc(t.executed_at) < first_ts:
            dc, dq = _trade_flows(t)
            cash += dc
            qty[t.symbol] = qty.get(t.symbol, 0.0) + dq
        else:
            window.append(t)
    window.sort(key=lambda t: _as_utc(t.executed_at))

    points: list[PortfolioHistoryPoint] = []
    last_price: dict[str, float] = {}
    ptr = 0
    for ts in ordered_ts:
        ts_utc = _as_utc(ts)
        while ptr < len(window) and _as_utc(window[ptr].executed_at) <= ts_utc:
            dc, dq = _trade_flows(window[ptr])
            cash += dc
            qty[window[ptr].symbol] = qty.get(window[ptr].symbol, 0.0) + dq
            ptr += 1
        for sym, series in price_at.items():
            if ts in series:
                last_price[sym] = series[ts]
        holdings_val = sum(
            q * last_price[s] for s, q in qty.items() if s in last_price and abs(q) > 1e-9
        )
        points.append(PortfolioHistoryPoint(date=ts.isoformat(), value=cash + holdings_val))

    if benchmark:
        _apply_benchmark_intraday(points, portfolio.starting_balance, provider)
    return PortfolioHistoryResponse(range="1d", points=points)


def portfolio_value_history(
    db: Session, portfolio: Portfolio, range_: str, benchmark: bool = False
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

    # Intraday (today's session) needs minute bars and a different time axis, so it has its own
    # reconstruction; every other range shares the daily-close path below.
    if range_ == "1d":
        return _intraday_value_history(portfolio, trades, provider, benchmark)

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

    # No reconstructable trading days on/after creation — e.g. a brand-new account, or a coarse
    # (monthly) sampling whose only bars predate creation. Anchor at the creation baseline (all
    # cash = starting balance) so the series still renders a line up to today's live value.
    points: list[PortfolioHistoryPoint] = []
    if not days:
        points.append(
            PortfolioHistoryPoint(
                date=portfolio.created_at.isoformat(), value=portfolio.starting_balance
            )
        )

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

    if benchmark:
        _apply_benchmark_daily(points, portfolio.starting_balance, range_, provider)
    return PortfolioHistoryResponse(range=range_, points=points)
