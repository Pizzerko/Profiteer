from pydantic import BaseModel


class Quote(BaseModel):
    symbol: str
    name: str | None = None
    price: float | None = None  # regular-session price (live during REGULAR, else last close)
    previous_close: float | None = None
    change: float | None = None
    change_percent: float | None = None
    currency: str | None = None
    market_state: str | None = None  # REGULAR, CLOSED, PRE, POST
    # Extended-hours (pre/post-market). Present only when market_state is PRE or POST.
    extended_price: float | None = None
    extended_change: float | None = None  # vs the regular close (`price`)
    extended_change_percent: float | None = None
    # The price a trade would fill at now: extended when in PRE/POST, else regular price.
    effective_price: float | None = None


class HistoryPoint(BaseModel):
    date: str
    close: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None


class HistoryResponse(BaseModel):
    symbol: str
    range: str
    points: list[HistoryPoint]


class NewsItem(BaseModel):
    title: str
    publisher: str | None = None
    link: str | None = None
    published_at: str | None = None


class SearchResult(BaseModel):
    symbol: str
    name: str | None = None
    exchange: str | None = None
    type: str | None = None
