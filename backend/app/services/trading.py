"""Paper-trading logic: execute buys/sells and value a portfolio.

All mutations happen inside the caller's DB session/transaction. Trades execute at
the latest price fetched from the market data provider (no market-hours enforcement in v1).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.holding import Holding
from app.models.option_trade import OptionTrade
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
    if portfolio.locked:
        raise TradingError("Portfolio is locked — it was wiped out. Start over to continue.")

    # Competition entries can only trade inside the contest window. Lazy import breaks the
    # competitions.py ↔ trading.py cycle. This is the single choke point for stock trades —
    # poller-triggered limit/stop fills route through here too.
    from app.services.competitions import assert_competition_open

    assert_competition_open(portfolio)

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

    if side not in ("buy", "sell"):
        raise TradingError("Side must be 'buy' or 'sell'.")

    # Buying power gate (covers longs on margin and shorting alike); then apply the fill.
    _assert_margin(db, portfolio, symbol, side, quantity, price)
    realized_pl = _apply_fill(db, portfolio, symbol, side, quantity, price)

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

    # A trade can wipe out the account (e.g. covering a short at a huge loss). Lock if so.
    if value_portfolio(db, portfolio).total_value <= 1e-9:
        portfolio.locked = True
        db.commit()
    return trade


def _get_holding(db: Session, portfolio_id: int, symbol: str) -> Holding | None:
    return db.scalar(
        select(Holding).where(Holding.portfolio_id == portfolio_id, Holding.symbol == symbol)
    )


def _position_price(provider, symbol: str, avg_cost: float) -> float:
    """Current price for a held symbol (extended if in PRE/POST), falling back to avg cost."""
    try:
        q = provider.get_quote(symbol)
        p = q.effective_price if q.effective_price else q.price
    except MarketDataError:
        p = None
    return p if p is not None and p > 0 else avg_cost


def _assert_margin(
    db: Session, portfolio: Portfolio, symbol: str, side: str, quantity: float, price: float
) -> None:
    """Reject the trade if, after it fills, equity would fall below the maintenance requirement.

    equity = cash + Σ(signed_qty * price); gross_exposure = Σ|signed_qty * price|.
    We require equity ≥ maintenance_margin_ratio * gross_exposure. This single gate limits both
    long leverage and short size, and lets cash go negative (margin borrowing) within that bound.
    """
    signed = quantity if side == "buy" else -quantity
    cash = portfolio.cash_balance + (-quantity * price if side == "buy" else quantity * price)

    positions = {h.symbol: h.quantity for h in portfolio.holdings}
    positions[symbol] = positions.get(symbol, 0.0) + signed

    provider = get_provider()
    avg_by_symbol = {h.symbol: h.avg_cost for h in portfolio.holdings}
    equity = cash
    gross = 0.0
    for sym, qty in positions.items():
        if abs(qty) <= 1e-9:
            continue
        p = price if sym == symbol else _position_price(provider, sym, avg_by_symbol.get(sym, 0.0))
        equity += qty * p
        gross += abs(qty * p)

    if gross > 0 and equity < settings.maintenance_margin_ratio * gross - 1e-9:
        raise TradingError(
            "Insufficient buying power / margin for this order."
        )


def _apply_fill(
    db: Session, portfolio: Portfolio, symbol: str, side: str, quantity: float, price: float
) -> float | None:
    """Apply a buy/sell to the (signed) position, returning realized P&L when it closes/covers.

    Positions are signed: positive = long, negative = short, `avg_cost` = average entry of the open
    side. Buying reduces cash and covers shorts / opens longs; selling adds cash and closes longs /
    opens shorts. Realized P&L is booked only on the portion that reduces an existing opposite side.
    """
    signed = quantity if side == "buy" else -quantity
    holding = _get_holding(db, portfolio.id, symbol)
    pos = holding.quantity if holding else 0.0
    avg = holding.avg_cost if holding else 0.0
    new_pos = pos + signed

    # Booked P&L when this trade reduces an opposite-side position.
    realized: float | None = None
    if pos != 0 and (pos > 0) != (signed > 0):
        closed = min(abs(signed), abs(pos))
        realized = closed * (price - avg) * (1.0 if pos > 0 else -1.0)

    portfolio.cash_balance += -quantity * price if side == "buy" else quantity * price

    if abs(new_pos) <= 1e-9:
        new_avg = 0.0
    elif pos == 0 or (pos > 0) == (signed > 0):
        # Opening or adding on the same side: weighted-average the entry price.
        new_avg = (avg * abs(pos) + price * abs(signed)) / (abs(pos) + abs(signed))
    elif abs(signed) <= abs(pos):
        # Partial/full close, same side remains: average entry unchanged.
        new_avg = avg
    else:
        # Flipped through zero: the remainder opens a fresh position at this price.
        new_avg = price

    if abs(new_pos) <= 1e-9:
        if holding is not None:
            db.delete(holding)
    elif holding is None:
        db.add(Holding(portfolio_id=portfolio.id, symbol=symbol, quantity=new_pos, avg_cost=new_avg))
    else:
        holding.quantity = new_pos
        holding.avg_cost = new_avg
    return realized


def value_portfolio(db: Session, portfolio: Portfolio) -> PortfolioOut:
    """Compute live valuation and P&L for a portfolio."""
    provider = get_provider()
    holdings_out: list[HoldingOut] = []
    holdings_value = 0.0
    gross_exposure = 0.0  # Σ|market value|, for the margin/buying-power calc

    for h in portfolio.holdings:
        current_price: float | None = None
        previous_close: float | None = None
        try:
            q = provider.get_quote(h.symbol)
            current_price = q.effective_price if q.effective_price else q.price
            previous_close = q.previous_close
        except MarketDataError:
            current_price = None

        cost_basis = h.avg_cost * h.quantity
        market_value = current_price * h.quantity if current_price is not None else None
        unrealized_pl = market_value - cost_basis if market_value is not None else None
        # Percent is against the absolute cost basis so shorts (negative basis) read correctly.
        unrealized_pl_percent = (
            (unrealized_pl / abs(cost_basis) * 100)
            if unrealized_pl is not None and cost_basis
            else None
        )
        # Today's gain: the position's move since the prior regular close (signed by quantity, so
        # shorts read correctly). Percent is against yesterday's position value.
        todays_pl = (
            (current_price - previous_close) * h.quantity
            if current_price is not None and previous_close is not None
            else None
        )
        todays_pl_percent = (
            (todays_pl / abs(previous_close * h.quantity) * 100)
            if todays_pl is not None and previous_close and h.quantity
            else None
        )
        if market_value is not None:
            holdings_value += market_value
            gross_exposure += abs(market_value)

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
                todays_pl=todays_pl,
                todays_pl_percent=todays_pl_percent,
            )
        )

    # Option positions: live-priced, signed market value adds to total & gross; cash-secured puts
    # reserve cash. Lazy import breaks the options.py ↔ trading.py cycle.
    from app.services.options import option_positions_view

    option_positions_out, option_gross, reserved_cash = option_positions_view(db, portfolio)
    option_value = sum(p.market_value for p in option_positions_out if p.market_value is not None)
    gross_exposure += option_gross

    total_value = portfolio.cash_balance + holdings_value + option_value
    total_pl = total_value - portfolio.starting_balance
    total_pl_percent = (
        (total_pl / portfolio.starting_balance * 100) if portfolio.starting_balance else 0.0
    )

    # Buying power = the additional gross exposure allowed before hitting the maintenance floor
    # (equity ≥ ratio * gross ⇒ max gross = equity / ratio). Clamped at zero. Cash already pledged
    # as collateral by cash-secured puts is unavailable, so subtract it.
    ratio = settings.maintenance_margin_ratio
    buying_power = max(0.0, total_value / ratio - gross_exposure) if ratio > 0 else 0.0
    buying_power = max(0.0, buying_power - reserved_cash)

    # Sum of realized P&L locked in across every stock sell + option close/settlement.
    realized_pl = db.scalar(
        select(func.coalesce(func.sum(Trade.realized_pl), 0.0)).where(
            Trade.portfolio_id == portfolio.id
        )
    ) or 0.0
    realized_pl += db.scalar(
        select(func.coalesce(func.sum(OptionTrade.realized_pl), 0.0)).where(
            OptionTrade.portfolio_id == portfolio.id
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
        buying_power=buying_power,
        reserved_cash=reserved_cash,
        locked=portfolio.locked,
        holdings=holdings_out,
        option_positions=option_positions_out,
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
    portfolio: Portfolio,
    trades: list[Trade],
    option_trades: list[OptionTrade],
    provider,
    benchmark: bool = False,
) -> PortfolioHistoryResponse:
    """Reconstruct today's portfolio value from 1-minute bars.

    Holdings are valued at each minute's price (extended-hours included) and cash/share counts
    step forward through any trades executed during the session, so a mid-session buy/sell moves
    the line at the moment it filled rather than being back-applied to the whole day.

    Options have no historical per-contract marks available, so open positions can't be live-priced
    on past bars. We approximate their contribution as cumulative *realized* P&L only (see the
    identity in `portfolio_value_history`'s docstring) — the line treats an open position's
    unrealized P&L as flat until it closes or settles, then jumps by exactly the realized amount.
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

    option_realized = 0.0
    option_window: list[OptionTrade] = []
    for t in option_trades:
        if _as_utc(t.executed_at) < first_ts:
            option_realized += t.realized_pl or 0.0
        else:
            option_window.append(t)
    option_window.sort(key=lambda t: _as_utc(t.executed_at))

    points: list[PortfolioHistoryPoint] = []
    last_price: dict[str, float] = {}
    ptr = 0
    optr = 0
    for ts in ordered_ts:
        ts_utc = _as_utc(ts)
        while ptr < len(window) and _as_utc(window[ptr].executed_at) <= ts_utc:
            dc, dq = _trade_flows(window[ptr])
            cash += dc
            qty[window[ptr].symbol] = qty.get(window[ptr].symbol, 0.0) + dq
            ptr += 1
        while optr < len(option_window) and _as_utc(option_window[optr].executed_at) <= ts_utc:
            option_realized += option_window[optr].realized_pl or 0.0
            optr += 1
        for sym, series in price_at.items():
            if ts in series:
                last_price[sym] = series[ts]
        holdings_val = sum(
            q * last_price[s] for s, q in qty.items() if s in last_price and abs(q) > 1e-9
        )
        points.append(
            PortfolioHistoryPoint(date=ts.isoformat(), value=cash + holdings_val + option_realized)
        )

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

    Options have no historical per-contract marks, so an open position can't be live-priced on a
    past day. Instead we add each day's *cumulative realized* option P&L to the stock-only total.
    This is exact, not just a rough stand-in: buying/adding to a position debits cash by exactly its
    cost basis, so "cash + cost-basis-of-open-positions" only ever moves by realized P&L (the same
    quantity `_apply_option_fill`/`settle_expired_options` compute on each close). Since our
    approximation of an open position's value *is* its cost basis (flat, no unrealized swing), the
    stock-only reconstruction plus cumulative realized option P&L equals cash + stock value + (cost
    basis of open option positions) — i.e. exactly what we'd get if we could price options at cost.
    The only gap versus the true live number is any *unrealized* P&L on currently-open positions,
    which is why the last point is still patched with the live valuation below.
    """
    provider = get_provider()
    trades = list(
        db.scalars(
            select(Trade)
            .where(Trade.portfolio_id == portfolio.id)
            .order_by(Trade.executed_at)
        )
    )
    option_trades = list(
        db.scalars(
            select(OptionTrade)
            .where(OptionTrade.portfolio_id == portfolio.id)
            .order_by(OptionTrade.executed_at)
        )
    )

    # Intraday (today's session) needs minute bars and a different time axis, so it has its own
    # reconstruction; every other range shares the daily-close path below.
    if range_ == "1d":
        return _intraday_value_history(portfolio, trades, option_trades, provider, benchmark)

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

        option_realized = sum(
            t.realized_pl or 0.0
            for t in option_trades
            if t.executed_at.date().isoformat() <= day
        )
        points.append(
            PortfolioHistoryPoint(date=day_iso[day], value=cash + holdings_val + option_realized)
        )

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
