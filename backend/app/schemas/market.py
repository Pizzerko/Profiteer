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


class Fundamentals(BaseModel):
    """Company profile + key statistics, from the heavy Yahoo `.info` endpoint."""

    symbol: str
    name: str | None = None
    exchange: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    pe_ratio: float | None = None  # trailing P/E
    forward_pe: float | None = None
    eps: float | None = None  # trailing EPS
    dividend_yield: float | None = None  # percent (e.g. 0.52 == 0.52%)
    beta: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    open: float | None = None
    previous_close: float | None = None
    volume: float | None = None
    avg_volume: float | None = None


class MoverQuote(BaseModel):
    """Compact quote for market-overview lists (indices, movers, ETFs)."""

    symbol: str
    name: str | None = None
    price: float | None = None
    change: float | None = None
    change_percent: float | None = None
    market_state: str | None = None


class MarketOverview(BaseModel):
    indices: list[MoverQuote]
    gainers: list[MoverQuote]
    losers: list[MoverQuote]
    etfs: list[MoverQuote]


class OptionContract(BaseModel):
    """A single option contract row from the chain."""

    occ_symbol: str  # OCC contract symbol, e.g. "AAPL250815C00190000"
    option_type: str  # "call" | "put"
    strike: float
    last_price: float | None = None
    bid: float | None = None
    ask: float | None = None
    mark: float | None = None  # mid(bid, ask) when both > 0, else last_price
    change: float | None = None
    percent_change: float | None = None
    volume: float | None = None
    open_interest: float | None = None
    implied_volatility: float | None = None
    in_the_money: bool | None = None


class OptionChain(BaseModel):
    underlying: str
    expiration: str  # "YYYY-MM-DD" — the expiration this chain is for
    expirations: list[str]  # all available expiration dates for the underlying
    calls: list[OptionContract]
    puts: list[OptionContract]
