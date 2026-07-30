from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_selected_portfolio
from app.db.session import get_db
from app.models.portfolio import Portfolio
from app.schemas.portfolio import TradeOut, TradeRequest
from app.services.trading import TradingError, execute_trade

router = APIRouter(prefix="/trades", tags=["trades"])


@router.post("", response_model=TradeOut, status_code=201)
def create_trade(
    payload: TradeRequest,
    portfolio: Portfolio = Depends(get_selected_portfolio),
    db: Session = Depends(get_db),
) -> TradeOut:
    try:
        return execute_trade(db, portfolio, payload.symbol, payload.side, payload.quantity)
    except TradingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
