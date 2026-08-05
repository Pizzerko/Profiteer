from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_selected_portfolio
from app.db.session import get_db
from app.models.portfolio import Portfolio
from app.models.trade import Trade
from app.schemas.portfolio import PortfolioHistoryResponse, PortfolioOut, TradeOut
from app.services.trading import portfolio_value_history, value_portfolio

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioOut)
def get_portfolio(
    portfolio: Portfolio = Depends(get_selected_portfolio), db: Session = Depends(get_db)
) -> PortfolioOut:
    return value_portfolio(db, portfolio)


@router.post("/reset", response_model=PortfolioOut)
def reset_portfolio(
    portfolio: Portfolio = Depends(get_selected_portfolio), db: Session = Depends(get_db)
) -> PortfolioOut:
    """Wipe holdings/trades/orders, restore starting cash, and unlock.

    Doubles as the manual reset and the "Start over" acknowledgement after a bankruptcy lock.
    """
    if portfolio.competition_id is not None:
        # Otherwise an entrant could erase a losing streak and start the contest over.
        raise HTTPException(
            status_code=400,
            detail="A competition entry can't be reset — that would erase your result.",
        )
    for h in list(portfolio.holdings):
        db.delete(h)
    for t in list(portfolio.trades):
        db.delete(t)
    for o in list(portfolio.orders):
        db.delete(o)
    portfolio.cash_balance = portfolio.starting_balance
    portfolio.locked = False
    db.commit()
    return value_portfolio(db, portfolio)


@router.get("/trades", response_model=list[TradeOut])
def get_trades(
    portfolio: Portfolio = Depends(get_selected_portfolio), db: Session = Depends(get_db)
) -> list[Trade]:
    return list(
        db.scalars(
            select(Trade)
            .where(Trade.portfolio_id == portfolio.id)
            .order_by(Trade.executed_at.desc())
        )
    )


@router.get("/history", response_model=PortfolioHistoryResponse)
def get_history(
    range: str = Query("1mo"),
    benchmark: bool = Query(False),
    portfolio: Portfolio = Depends(get_selected_portfolio),
    db: Session = Depends(get_db),
) -> PortfolioHistoryResponse:
    return portfolio_value_history(db, portfolio, range, benchmark)
