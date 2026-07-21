"""Paper-trading logic: execute buys/sells and value a portfolio.

All mutations happen inside the caller's DB session/transaction. Trades execute at
the latest price fetched from the market data provider (no market-hours enforcement in v1).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.holding import Holding
from app.models.portfolio import Portfolio
from app.models.trade import Trade
from app.schemas.portfolio import HoldingOut, PortfolioOut
from app.services.market_data import MarketDataError, get_provider


class TradingError(Exception):
    """Raised on invalid trades (insufficient cash/shares, bad price)."""


def execute_trade(db: Session, portfolio: Portfolio, symbol: str, side: str, quantity: float) -> Trade:
    symbol = symbol.upper().strip()
    if quantity <= 0:
        raise TradingError("Quantity must be greater than zero.")

    try:
        quote = get_provider().get_quote(symbol)
    except MarketDataError as exc:
        raise TradingError(str(exc)) from exc

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
