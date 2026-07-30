"""Options trading: fills, collateral, market-hours rules, live valuation, expiry settlement.

This is a cash account — options are never naked. Long options are pure cash debits; written
options must be collateralised: a written put is cash-secured (strike × 100 cash reserved) and a
written call is covered (100 underlying shares per contract held). Contract multiplier is 100.

Market-hours rules (mirroring Robinhood): options trade only during REGULAR hours, and a 0DTE
contract (expiring today) can't be traded in the final `option_0dte_cutoff_minutes` unless the
underlying is an index (index_option_underlyings).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.holding import Holding
from app.models.option_order import OptionOrder
from app.models.option_position import OptionPosition
from app.models.option_trade import OptionTrade
from app.models.portfolio import Portfolio
from app.schemas.market import OptionContract
from app.schemas.portfolio import OptionOrderRequest, OptionPositionOut
from app.services.market_data import MarketDataError, get_provider
from app.services.trading import TradingError, value_portfolio

logger = logging.getLogger("app.options")

_ET = ZoneInfo("America/New_York")
_MULTIPLIER = 100  # shares per option contract
_REGULAR_CLOSE_HOUR = 16


def _now_et() -> datetime:
    return datetime.now(_ET)


# ---------------------------------------------------------------------------
# Market-hours gate
# ---------------------------------------------------------------------------
def _assert_option_tradeable(underlying: str, expiration: date, quote) -> None:
    """Reject option orders outside regular hours, and 0DTE in the final minutes (non-index)."""
    if quote is None or quote.market_state != "REGULAR":
        raise TradingError(
            "Options trade only during regular market hours (9:30 AM–4:00 PM ET)."
        )

    now_et = _now_et()
    if expiration == now_et.date():
        close_dt = now_et.replace(
            hour=_REGULAR_CLOSE_HOUR, minute=0, second=0, microsecond=0
        )
        cutoff_dt = close_dt - timedelta(minutes=settings.option_0dte_cutoff_minutes)
        is_index = underlying.upper() in settings.index_option_underlyings
        if now_et >= cutoff_dt and not is_index:
            raise TradingError(
                "0DTE contracts can't be traded in the final "
                f"{settings.option_0dte_cutoff_minutes} minutes of regular hours."
            )


# ---------------------------------------------------------------------------
# Collateral helpers
# ---------------------------------------------------------------------------
def _reserved_cash(portfolio: Portfolio, exclude_occ: str | None = None) -> float:
    """Cash locked as collateral by cash-secured (written) puts."""
    total = 0.0
    for p in portfolio.option_positions:
        if p.occ_symbol == exclude_occ:
            continue
        if p.quantity < 0 and p.collateral_kind == "cash_secured":
            total += p.strike * _MULTIPLIER * abs(p.quantity)
    return total


def _short_call_contracts(portfolio: Portfolio, underlying: str, exclude_occ: str | None = None) -> float:
    """Number of written call contracts on `underlying` (each locks 100 shares)."""
    total = 0.0
    for p in portfolio.option_positions:
        if p.occ_symbol == exclude_occ:
            continue
        if p.quantity < 0 and p.option_type == "call" and p.underlying == underlying:
            total += abs(p.quantity)
    return total


def _owned_shares(db: Session, portfolio_id: int, underlying: str) -> float:
    h = db.scalar(
        select(Holding).where(
            Holding.portfolio_id == portfolio_id, Holding.symbol == underlying
        )
    )
    return h.quantity if h and h.quantity > 0 else 0.0


# ---------------------------------------------------------------------------
# Placing an order
# ---------------------------------------------------------------------------
def place_option_order(db: Session, portfolio: Portfolio, req: OptionOrderRequest) -> OptionTrade:
    """Fill an option market order immediately (regular hours only), enforcing collateral."""
    if portfolio.locked:
        raise TradingError("Portfolio is locked — it was wiped out. Start over to continue.")

    underlying = req.underlying.upper().strip()
    option_type = req.option_type
    qty = float(req.quantity)
    try:
        expiration = date.fromisoformat(req.expiration)
    except ValueError as exc:
        raise TradingError("Invalid expiration date.") from exc

    # Resolve the live contract (source of truth for occ_symbol + fill price).
    contract = get_provider().get_option_contract(underlying, req.expiration, option_type, req.strike)
    if contract is None:
        raise TradingError(
            f"Contract not found for {underlying} {req.strike} {option_type} {req.expiration}."
        )

    # Market-hours + 0DTE gate (needs the underlying's session state).
    try:
        quote = get_provider().get_quote(underlying)
    except MarketDataError as exc:
        raise TradingError(str(exc)) from exc
    _assert_option_tradeable(underlying, expiration, quote)

    price = contract.mark
    if price is None or price <= 0:
        raise TradingError(f"No tradeable price available for {contract.occ_symbol}.")

    occ = contract.occ_symbol
    position = db.scalar(
        select(OptionPosition).where(
            OptionPosition.portfolio_id == portfolio.id, OptionPosition.occ_symbol == occ
        )
    )
    pos = position.quantity if position else 0.0
    signed = qty if req.side == "buy" else -qty
    new_pos = pos + signed
    notional = qty * price * _MULTIPLIER

    # --- Collateral / buying-power gates -------------------------------
    if req.side == "buy":
        # Opening/adding a long spends cash; buying to close a short returns collateral, so only
        # gate against cash not already reserved by *other* positions.
        free_cash = portfolio.cash_balance - _reserved_cash(portfolio, exclude_occ=occ)
        if free_cash < notional - 1e-6:
            raise TradingError(
                f"Not enough buying power: this costs {notional:,.2f}, "
                f"{free_cash:,.2f} available."
            )
    else:  # sell
        if new_pos < -1e-9:  # ends net short → this is a write (or increases a short)
            short_after = abs(new_pos)
            if option_type == "put":
                other_reserve = _reserved_cash(portfolio, exclude_occ=occ)
                this_reserve = req.strike * _MULTIPLIER * short_after
                # After receiving premium, free cash must cover this contract's reservation too.
                if (portfolio.cash_balance + notional) - other_reserve < this_reserve - 1e-6:
                    raise TradingError(
                        f"Cash-secured put needs {this_reserve:,.2f} collateral; "
                        "not enough cash available."
                    )
            else:  # call → must be covered by owned shares
                owned = _owned_shares(db, portfolio.id, underlying)
                other_short = _short_call_contracts(portfolio, underlying, exclude_occ=occ)
                need_shares = _MULTIPLIER * (other_short + short_after)
                if owned < need_shares - 1e-6:
                    raise TradingError(
                        f"Covered call requires {int(need_shares)} shares of {underlying}; "
                        f"you own {int(owned)}. Naked calls aren't allowed."
                    )

    # --- Apply the fill (signed position, weighted-avg entry, realized on the close) ---
    realized = _apply_option_fill(
        db, portfolio, contract, underlying, expiration, new_pos, pos, signed, price
    )

    # Cash flow: buys debit, sells credit (premium × 100 × contracts).
    portfolio.cash_balance += -notional if req.side == "buy" else notional

    trade = OptionTrade(
        portfolio_id=portfolio.id,
        underlying=underlying,
        occ_symbol=occ,
        option_type=option_type,
        strike=req.strike,
        expiration=expiration,
        action=req.side,
        quantity=qty,
        price=price,
        realized_pl=realized,
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)

    # A losing option trade could in principle wipe the account; lock if so (as with stocks).
    if value_portfolio(db, portfolio).total_value <= 1e-9:
        portfolio.locked = True
        db.commit()
    return trade


def _apply_option_fill(
    db: Session,
    portfolio: Portfolio,
    contract: OptionContract,
    underlying: str,
    expiration: date,
    new_pos: float,
    pos: float,
    signed: float,
    price: float,
) -> float | None:
    """Update the OptionPosition row; return realized P&L on any closed contracts (× 100)."""
    position = db.scalar(
        select(OptionPosition).where(
            OptionPosition.portfolio_id == portfolio.id,
            OptionPosition.occ_symbol == contract.occ_symbol,
        )
    )
    avg = position.avg_price if position else 0.0

    realized: float | None = None
    if pos != 0 and (pos > 0) != (signed > 0):
        closed = min(abs(signed), abs(pos))
        realized = closed * _MULTIPLIER * (price - avg) * (1.0 if pos > 0 else -1.0)

    if abs(new_pos) <= 1e-9:
        new_avg = 0.0
    elif pos == 0 or (pos > 0) == (signed > 0):
        new_avg = (avg * abs(pos) + price * abs(signed)) / (abs(pos) + abs(signed))
    elif abs(signed) <= abs(pos):
        new_avg = avg
    else:
        new_avg = price  # flipped through zero

    # Written positions carry collateral; longs/flat don't.
    collateral = None
    if new_pos < -1e-9:
        collateral = "cash_secured" if contract.option_type == "put" else "covered"

    if abs(new_pos) <= 1e-9:
        if position is not None:
            db.delete(position)
    elif position is None:
        db.add(
            OptionPosition(
                portfolio_id=portfolio.id,
                underlying=underlying,
                occ_symbol=contract.occ_symbol,
                option_type=contract.option_type,
                strike=contract.strike,
                expiration=expiration,
                quantity=new_pos,
                avg_price=new_avg,
                collateral_kind=collateral,
            )
        )
    else:
        position.quantity = new_pos
        position.avg_price = new_avg
        position.collateral_kind = collateral
    return realized


# ---------------------------------------------------------------------------
# Resting option orders (limit / stop / trailing stop)
# ---------------------------------------------------------------------------
def evaluate_option_order(order: OptionOrder, mark: float) -> bool:
    """Whether `order` should fill at the contract's current `mark`. Updates the trailing peak.

    Same trigger logic as the stock engine (orders.py::evaluate_order), evaluated on the option's
    per-share premium. Callers must have confirmed the session is REGULAR.
    """
    if order.order_type == "limit":
        if order.side == "buy":
            return mark <= order.limit_price
        return mark >= order.limit_price

    if order.order_type == "stop":
        if order.side == "buy":
            return mark >= order.stop_price
        return mark <= order.stop_price

    if order.order_type == "trailing_stop":
        trail = (order.trail_percent or 0) / 100.0
        if order.side == "sell":
            # Protect a long: track the high-water mark, sell if the mark falls `trail` below it.
            order.peak_price = mark if order.peak_price is None else max(order.peak_price, mark)
            return mark <= order.peak_price * (1 - trail)
        # Buy trailing stop: track the low-water mark, buy if the mark rises `trail` above it.
        order.peak_price = mark if order.peak_price is None else min(order.peak_price, mark)
        return mark >= order.peak_price * (1 + trail)

    return False


def process_open_option_orders(db: Session) -> None:
    """One poll pass: fill any open option orders whose trigger is met during regular hours."""
    orders = list(db.scalars(select(OptionOrder).where(OptionOrder.status == "open")))
    if not orders:
        return

    provider = get_provider()
    # Cache the underlying's session state so we only query each symbol once per pass.
    market_states: dict[str, str | None] = {}
    dirty = False

    for order in orders:
        underlying = order.underlying
        if underlying not in market_states:
            try:
                q = provider.get_quote(underlying)
                market_states[underlying] = q.market_state if q else None
            except MarketDataError:
                market_states[underlying] = None
        # Options only trade regular hours — leave the order open otherwise.
        if market_states[underlying] != "REGULAR":
            continue

        exp_iso = order.expiration.isoformat()
        try:
            contract = provider.get_option_contract(
                underlying, exp_iso, order.option_type, order.strike
            )
        except MarketDataError:
            contract = None
        mark = contract.mark if contract else None
        if mark is None or mark <= 0:
            continue  # can't price the contract — leave it open

        triggered = evaluate_option_order(order, mark)  # may update peak_price
        dirty = True  # peak_price and/or status changed; persist at the end
        if not triggered:
            continue

        req = OptionOrderRequest(
            occ_symbol=order.occ_symbol,
            underlying=underlying,
            expiration=exp_iso,
            option_type=order.option_type,
            strike=order.strike,
            side=order.side,
            quantity=int(order.quantity),
        )
        try:
            trade = place_option_order(db, order.portfolio, req)  # commits internally
            order.status = "filled"
            order.filled_at = datetime.now(timezone.utc)
            order.fill_price = trade.price
            order.filled_option_trade_id = trade.id
            logger.info(
                "Filled option order %s (%s %s %s @ %s)",
                order.id, order.side, order.quantity, order.occ_symbol, trade.price,
            )
        except TradingError as exc:
            # Unfillable (collateral/buying power, locked, hours). Don't retry.
            order.status = "rejected"
            order.note = str(exc)[:255]
            logger.info("Rejected option order %s: %s", order.id, exc)

    if dirty:
        db.commit()


# ---------------------------------------------------------------------------
# Valuation
# ---------------------------------------------------------------------------
def option_positions_view(
    db: Session, portfolio: Portfolio
) -> tuple[list[OptionPositionOut], float, float]:
    """(rows, gross_exposure, reserved_cash) — live-priced option positions for a portfolio."""
    provider = get_provider()
    today = _now_et().date()
    rows: list[OptionPositionOut] = []
    gross = 0.0
    reserved = 0.0

    for p in portfolio.option_positions:
        exp_iso = p.expiration.isoformat()
        mark: float | None = None
        try:
            contract = provider.get_option_contract(p.underlying, exp_iso, p.option_type, p.strike)
            mark = contract.mark if contract else None
        except MarketDataError:
            mark = None

        cost_basis = p.avg_price * _MULTIPLIER * p.quantity
        market_value = mark * _MULTIPLIER * p.quantity if mark is not None else None
        unrealized_pl = market_value - cost_basis if market_value is not None else None
        unrealized_pl_percent = (
            (unrealized_pl / abs(cost_basis) * 100)
            if unrealized_pl is not None and cost_basis
            else None
        )
        if market_value is not None:
            gross += abs(market_value)
        if p.quantity < 0 and p.collateral_kind == "cash_secured":
            reserved += p.strike * _MULTIPLIER * abs(p.quantity)

        rows.append(
            OptionPositionOut(
                underlying=p.underlying,
                occ_symbol=p.occ_symbol,
                option_type=p.option_type,
                strike=p.strike,
                expiration=exp_iso,
                quantity=p.quantity,
                avg_price=p.avg_price,
                collateral_kind=p.collateral_kind,
                current_price=mark,
                market_value=market_value,
                cost_basis=cost_basis,
                unrealized_pl=unrealized_pl,
                unrealized_pl_percent=unrealized_pl_percent,
                days_to_expiry=(p.expiration - today).days,
            )
        )

    rows.sort(key=lambda r: (r.expiration, r.underlying, r.strike))
    return rows, gross, reserved


# ---------------------------------------------------------------------------
# Expiry settlement (called from the order poller)
# ---------------------------------------------------------------------------
def settle_expired_options(db: Session) -> None:
    """Auto-settle option positions at/after their expiration's regular close.

    Long ITM → receive intrinsic; short ITM → pay intrinsic (assignment, cash-settled here);
    OTM → worthless. Collateral is released implicitly by deleting the position.
    """
    now_et = _now_et()
    provider = get_provider()
    changed = False

    positions = list(db.scalars(select(OptionPosition)))
    underlying_price: dict[str, float | None] = {}

    for p in positions:
        # Settle once we're past 4:00 PM ET on/after the expiration date.
        expired_before_today = p.expiration < now_et.date()
        expiring_today_closed = p.expiration == now_et.date() and now_et.hour >= _REGULAR_CLOSE_HOUR
        if not (expired_before_today or expiring_today_closed):
            continue

        if p.underlying not in underlying_price:
            try:
                q = provider.get_quote(p.underlying)
                underlying_price[p.underlying] = q.price if q and q.price else None
            except MarketDataError:
                underlying_price[p.underlying] = None
        spot = underlying_price[p.underlying]
        if spot is None:
            continue  # can't price the underlying yet; try again next cycle

        if p.option_type == "call":
            intrinsic = max(0.0, spot - p.strike)
        else:
            intrinsic = max(0.0, p.strike - spot)

        contracts = abs(p.quantity)
        payoff = intrinsic * _MULTIPLIER * contracts  # dollar value of the position at expiry
        cost_basis = p.avg_price * _MULTIPLIER * contracts

        if p.quantity > 0:
            # Long: receive intrinsic; realized = payoff − premium paid.
            portfolio_cash_delta = payoff
            realized = payoff - cost_basis
        else:
            # Short (covered/cash-secured): pay intrinsic if assigned; keep premium received.
            portfolio_cash_delta = -payoff
            realized = cost_basis - payoff  # cost_basis is premium received (avg_price × 100 × n)

        portfolio = db.get(Portfolio, p.portfolio_id)
        if portfolio is None:
            continue
        portfolio.cash_balance += portfolio_cash_delta

        note = (
            f"expired {'ITM' if intrinsic > 0 else 'worthless'} "
            f"(spot {spot:.2f} vs strike {p.strike:.2f})"
        )
        db.add(
            OptionTrade(
                portfolio_id=p.portfolio_id,
                underlying=p.underlying,
                occ_symbol=p.occ_symbol,
                option_type=p.option_type,
                strike=p.strike,
                expiration=p.expiration,
                action="settle",
                quantity=contracts,
                price=intrinsic,
                realized_pl=realized,
                note=note[:255],
            )
        )
        db.delete(p)
        changed = True
        logger.info(
            "Settled option %s (%s contracts) intrinsic=%.2f realized=%.2f",
            p.occ_symbol, contracts, intrinsic, realized,
        )

    if changed:
        db.commit()
