from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_default_portfolio
from app.db.session import get_db
from app.models.portfolio import Portfolio
from app.models.trade import Trade
from app.schemas.portfolio import PortfolioHistoryResponse, PortfolioOut, TradeOut
from app.services.trading import portfolio_value_history, value_portfolio

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioOut)
def get_portfolio(
    portfolio: Portfolio = Depends(get_default_portfolio), db: Session = Depends(get_db)
) -> PortfolioOut:
    return value_portfolio(db, portfolio)


@router.get("/trades", response_model=list[TradeOut])
def get_trades(
    portfolio: Portfolio = Depends(get_default_portfolio), db: Session = Depends(get_db)
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
    portfolio: Portfolio = Depends(get_default_portfolio),
    db: Session = Depends(get_db),
) -> PortfolioHistoryResponse:
    return portfolio_value_history(db, portfolio, range)
