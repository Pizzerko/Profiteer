from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.market import HistoryResponse, NewsItem, Quote, SearchResult
from app.services.market_data import MarketDataError, get_provider

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/search", response_model=list[SearchResult])
def search(q: str = Query(min_length=1), _: User = Depends(get_current_user)) -> list[SearchResult]:
    return get_provider().search(q)


@router.get("/quote/{symbol}", response_model=Quote)
def quote(symbol: str, _: User = Depends(get_current_user)) -> Quote:
    try:
        return get_provider().get_quote(symbol)
    except MarketDataError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/history/{symbol}", response_model=HistoryResponse)
def history(
    symbol: str,
    range: str = Query("1mo"),
    prepost: bool = Query(False),
    _: User = Depends(get_current_user),
) -> HistoryResponse:
    try:
        return get_provider().get_history(symbol, range, prepost)
    except MarketDataError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/news/{symbol}", response_model=list[NewsItem])
def news(symbol: str, _: User = Depends(get_current_user)) -> list[NewsItem]:
    return get_provider().get_news(symbol)
