from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_selected_portfolio
from app.db.session import get_db
from app.models.option_trade import OptionTrade
from app.models.portfolio import Portfolio
from app.models.user import User
from app.schemas.market import OptionChain
from app.schemas.portfolio import OptionOrderRequest, OptionTradeOut
from app.services.market_data import MarketDataError, get_provider
from app.services.options import place_option_order
from app.services.trading import TradingError

router = APIRouter(prefix="/options", tags=["options"])


@router.get("/{symbol}/expirations", response_model=list[str])
def expirations(symbol: str, _: User = Depends(get_current_user)) -> list[str]:
    try:
        return get_provider().get_option_expirations(symbol)
    except MarketDataError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{symbol}/chain", response_model=OptionChain)
def chain(
    symbol: str,
    expiration: str | None = Query(None),
    _: User = Depends(get_current_user),
) -> OptionChain:
    try:
        return get_provider().get_option_chain(symbol, expiration)
    except MarketDataError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/orders", response_model=OptionTradeOut, status_code=201)
def create_option_order(
    payload: OptionOrderRequest,
    portfolio: Portfolio = Depends(get_selected_portfolio),
    db: Session = Depends(get_db),
) -> OptionTrade:
    try:
        return place_option_order(db, portfolio, payload)
    except TradingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/trades", response_model=list[OptionTradeOut])
def option_trades(
    portfolio: Portfolio = Depends(get_selected_portfolio), db: Session = Depends(get_db)
) -> list[OptionTrade]:
    return list(
        db.scalars(
            select(OptionTrade)
            .where(OptionTrade.portfolio_id == portfolio.id)
            .order_by(OptionTrade.executed_at.desc())
        )
    )
