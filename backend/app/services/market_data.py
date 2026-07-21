"""Market data access, behind a swappable provider interface.

Only this module talks to Yahoo (via yfinance). To move to an official API later
(Finnhub, Alpha Vantage, ...), implement a new MarketDataProvider and swap
`get_provider()` — the rest of the app is unaffected.

All Yahoo calls are wrapped in short-lived TTL caches because yfinance scrapes
Yahoo and will rate-limit / block under repeated load.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from datetime import datetime, time as dtime

import yfinance as yf
from cachetools import TTLCache

from app.core.config import settings
from app.schemas.market import HistoryPoint, HistoryResponse, NewsItem, Quote, SearchResult

# range -> (yfinance period, interval). 1m granularity is only allowed for ~the last week.
_RANGE_MAP: dict[str, tuple[str, str]] = {
    "1d": ("1d", "1m"),
    "5d": ("5d", "5m"),
    "1mo": ("1mo", "1d"),
    "3mo": ("3mo", "1d"),
    "6mo": ("6mo", "1d"),
    "1y": ("1y", "1d"),
    "5y": ("5y", "1wk"),
    "max": ("max", "1mo"),
}

# US equity session boundaries (exchange local time). Pre: 04:00–09:30, Regular: 09:30–16:00,
# Post: 16:00–20:00. Used to classify the latest prepost bar into a market state.
_REGULAR_OPEN = dtime(9, 30)
_REGULAR_CLOSE = dtime(16, 0)


class MarketDataError(Exception):
    """Raised when market data cannot be retrieved for a symbol."""


class MarketDataProvider(ABC):
    @abstractmethod
    def get_quote(self, symbol: str) -> Quote: ...

    @abstractmethod
    def get_history(self, symbol: str, range_: str, prepost: bool = False) -> HistoryResponse: ...

    @abstractmethod
    def get_news(self, symbol: str) -> list[NewsItem]: ...

    @abstractmethod
    def search(self, query: str) -> list[SearchResult]: ...


class YahooProvider(MarketDataProvider):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._quote_cache: TTLCache = TTLCache(maxsize=512, ttl=settings.quote_cache_ttl)
        self._history_cache: TTLCache = TTLCache(maxsize=256, ttl=settings.history_cache_ttl)
        self._news_cache: TTLCache = TTLCache(maxsize=256, ttl=settings.news_cache_ttl)
        self._search_cache: TTLCache = TTLCache(maxsize=256, ttl=settings.news_cache_ttl)
        # Company names rarely change — cache them for a long time to avoid heavy .info calls.
        self._profile_cache: TTLCache = TTLCache(maxsize=1024, ttl=3600)

    # -- helpers ---------------------------------------------------------
    def _cache_get(self, cache: TTLCache, key: str):
        with self._lock:
            return cache.get(key)

    def _cache_set(self, cache: TTLCache, key: str, value) -> None:
        with self._lock:
            cache[key] = value

    def _name(self, symbol: str, ticker: "yf.Ticker") -> str | None:
        """Best-effort company name, cached for a long time (names rarely change)."""
        cached = self._cache_get(self._profile_cache, symbol)
        if cached is not None:
            return cached
        name: str | None = None
        try:
            info = ticker.info or {}
            name = info.get("shortName") or info.get("longName")
        except Exception:
            pass
        # Cache even a None result briefly-ish to avoid hammering the heavy .info endpoint.
        self._cache_set(self._profile_cache, symbol, name or "")
        return name or None

    def _extended(self, ticker: "yf.Ticker") -> tuple[str | None, float | None]:
        """Fresh (market_state, extended_price) derived from the latest prepost bar.

        Uses a 2-minute prepost history pull (fast, reliable) instead of the heavy .info
        endpoint. extended_price is set only when the latest bar falls in a PRE/POST session.
        """
        try:
            df = ticker.history(period="1d", interval="2m", prepost=True)
        except Exception:
            return (None, None)
        if df is None or len(df) == 0:
            return (None, None)

        last_ts = df.index[-1]
        last_close = _safe_float(df["Close"].iloc[-1])
        try:
            now = datetime.now(last_ts.tzinfo)
        except Exception:
            return (None, last_close if last_close else None)

        if last_ts.date() != now.date():
            state = "CLOSED"
        else:
            t = last_ts.time()
            if t < _REGULAR_OPEN:
                state = "PRE"
            elif t < _REGULAR_CLOSE:
                state = "REGULAR"
            else:
                state = "POST"

        extended_price = last_close if state in ("PRE", "POST") else None
        return (state, extended_price)

    # -- interface -------------------------------------------------------
    def get_quote(self, symbol: str) -> Quote:
        symbol = symbol.upper().strip()
        cached = self._cache_get(self._quote_cache, symbol)
        if cached is not None:
            return cached

        ticker = yf.Ticker(symbol)
        try:
            fi = ticker.fast_info
            price = _safe_float(getattr(fi, "last_price", None))
            previous_close = _safe_float(getattr(fi, "previous_close", None))
            currency = getattr(fi, "currency", None)
        except Exception as exc:  # noqa: BLE001
            raise MarketDataError(f"Could not fetch quote for '{symbol}'") from exc

        if price is None and previous_close is None:
            raise MarketDataError(f"Unknown or unavailable symbol '{symbol}'")

        change = None
        change_percent = None
        if price is not None and previous_close:
            change = price - previous_close
            change_percent = (change / previous_close) * 100 if previous_close else None

        name = self._name(symbol, ticker)
        market_state, extended_price = self._extended(ticker)

        extended_change = None
        extended_change_percent = None
        if extended_price is not None and price:
            extended_change = extended_price - price
            extended_change_percent = (extended_change / price) * 100 if price else None

        # Trades fill at the extended price during PRE/POST, otherwise the regular price.
        effective_price = (
            extended_price if market_state in ("PRE", "POST") and extended_price else price
        )

        quote = Quote(
            symbol=symbol,
            name=name,
            price=price,
            previous_close=previous_close,
            change=change,
            change_percent=change_percent,
            currency=currency,
            market_state=market_state,
            extended_price=extended_price,
            extended_change=extended_change,
            extended_change_percent=extended_change_percent,
            effective_price=effective_price,
        )
        self._cache_set(self._quote_cache, symbol, quote)
        return quote

    def get_history(self, symbol: str, range_: str, prepost: bool = False) -> HistoryResponse:
        symbol = symbol.upper().strip()
        range_ = range_ if range_ in _RANGE_MAP else "1mo"
        # prepost only affects intraday intervals; harmless (ignored by Yahoo) for daily+.
        key = f"{symbol}:{range_}:{int(prepost)}"
        cached = self._cache_get(self._history_cache, key)
        if cached is not None:
            return cached

        period, interval = _RANGE_MAP[range_]
        try:
            df = yf.Ticker(symbol).history(
                period=period, interval=interval, prepost=prepost, auto_adjust=False
            )
        except Exception as exc:  # noqa: BLE001
            raise MarketDataError(f"Could not fetch history for '{symbol}'") from exc

        points: list[HistoryPoint] = []
        for idx, row in df.iterrows():
            close = _safe_float(row.get("Close"))
            if close is None:
                continue
            points.append(
                HistoryPoint(
                    date=idx.isoformat(),
                    close=close,
                    open=_safe_float(row.get("Open")),
                    high=_safe_float(row.get("High")),
                    low=_safe_float(row.get("Low")),
                    volume=_safe_float(row.get("Volume")),
                )
            )
        result = HistoryResponse(symbol=symbol, range=range_, points=points)
        self._cache_set(self._history_cache, key, result)
        return result

    def get_news(self, symbol: str) -> list[NewsItem]:
        symbol = symbol.upper().strip()
        cached = self._cache_get(self._news_cache, symbol)
        if cached is not None:
            return cached

        try:
            raw = yf.Ticker(symbol).news or []
        except Exception:  # noqa: BLE001
            raw = []

        items: list[NewsItem] = []
        for entry in raw:
            items.append(_parse_news_entry(entry))
        items = [i for i in items if i.title]
        self._cache_set(self._news_cache, symbol, items)
        return items

    def search(self, query: str) -> list[SearchResult]:
        query = query.strip()
        if not query:
            return []
        cached = self._cache_get(self._search_cache, query.lower())
        if cached is not None:
            return cached

        results: list[SearchResult] = []
        try:
            quotes = yf.Search(query, max_results=10).quotes or []
            for q in quotes:
                symbol = q.get("symbol")
                if not symbol:
                    continue
                results.append(
                    SearchResult(
                        symbol=symbol,
                        name=q.get("shortname") or q.get("longname"),
                        exchange=q.get("exchange"),
                        type=q.get("quoteType"),
                    )
                )
        except Exception:  # noqa: BLE001
            results = []
        self._cache_set(self._search_cache, query.lower(), results)
        return results


def _safe_float(value) -> float | None:
    try:
        if value is None:
            return None
        f = float(value)
        # yfinance can yield NaN for missing cells.
        if f != f:  # NaN check
            return None
        return f
    except (TypeError, ValueError):
        return None


def _parse_news_entry(entry: dict) -> NewsItem:
    """Handle both the legacy flat news format and the newer nested `content` format."""
    if "content" in entry and isinstance(entry["content"], dict):
        c = entry["content"]
        provider = (c.get("provider") or {}).get("displayName")
        link = (c.get("canonicalUrl") or {}).get("url") or (c.get("clickThroughUrl") or {}).get("url")
        return NewsItem(
            title=c.get("title") or "",
            publisher=provider,
            link=link,
            published_at=c.get("pubDate"),
        )
    return NewsItem(
        title=entry.get("title") or "",
        publisher=entry.get("publisher"),
        link=entry.get("link"),
        published_at=str(entry.get("providerPublishTime")) if entry.get("providerPublishTime") else None,
    )


_provider: MarketDataProvider | None = None


def get_provider() -> MarketDataProvider:
    """Return the singleton market data provider (swap implementation here)."""
    global _provider
    if _provider is None:
        _provider = YahooProvider()
    return _provider
