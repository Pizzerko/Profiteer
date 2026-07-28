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
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time as dtime

import yfinance as yf
from cachetools import TTLCache

from app.core.config import settings
from app.schemas.market import (
    Fundamentals,
    HistoryPoint,
    HistoryResponse,
    MarketOverview,
    MoverQuote,
    NewsItem,
    Quote,
    SearchResult,
)

# Curated symbol sets for the market-overview page. Movers are ranked from UNIVERSE_SYMBOLS
# (a fixed large-cap list) rather than a live screener — robust and predictable.
INDEX_SYMBOLS = ["^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX"]
ETF_SYMBOLS = ["SPY", "QQQ", "VOO", "VTI", "DIA", "IWM", "ARKK", "XLK", "XLF", "XLE"]
UNIVERSE_SYMBOLS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "BRK-B", "JPM", "V",
    "WMT", "MA", "UNH", "HD", "PG", "COST", "JNJ", "ORCL", "BAC", "KO",
    "DIS", "ADBE", "CRM", "NFLX", "AMD", "INTC", "PEP", "CSCO", "MCD", "QCOM",
]

# range -> (yfinance period, interval). 1m granularity is only allowed for ~the last week.
_RANGE_MAP: dict[str, tuple[str, str]] = {
    "1d": ("1d", "1m"),
    "5d": ("5d", "5m"),
    "1w": ("5d", "1d"),  # weekly view: last ~5 trading days at daily granularity
    "1mo": ("1mo", "1d"),
    "3mo": ("3mo", "1d"),
    "6mo": ("6mo", "1d"),
    "ytd": ("ytd", "1d"),
    "1y": ("1y", "1d"),
    "5y": ("5y", "1wk"),
    "all": ("max", "1mo"),
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

    @abstractmethod
    def get_fundamentals(self, symbol: str) -> Fundamentals: ...

    @abstractmethod
    def get_overview(self) -> MarketOverview: ...


class YahooProvider(MarketDataProvider):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._quote_cache: TTLCache = TTLCache(maxsize=512, ttl=settings.quote_cache_ttl)
        self._history_cache: TTLCache = TTLCache(maxsize=256, ttl=settings.history_cache_ttl)
        self._news_cache: TTLCache = TTLCache(maxsize=256, ttl=settings.news_cache_ttl)
        self._search_cache: TTLCache = TTLCache(maxsize=256, ttl=settings.news_cache_ttl)
        # Company names rarely change — cache them for a long time to avoid heavy .info calls.
        self._profile_cache: TTLCache = TTLCache(maxsize=1024, ttl=3600)
        # Fundamentals also come from the heavy .info call; cache them a while.
        self._fundamentals_cache: TTLCache = TTLCache(
            maxsize=512, ttl=settings.fundamentals_cache_ttl
        )
        # Whole market-overview response, keyed by a single constant.
        self._overview_cache: TTLCache = TTLCache(maxsize=1, ttl=settings.overview_cache_ttl)

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

    def _session(self, ticker: "yf.Ticker") -> tuple[str | None, float | None, date | None]:
        """Fresh (market_state, extended_price, market_local_today) from the latest prepost bar.

        Uses a 2-minute prepost history pull (fast, reliable) instead of the heavy .info
        endpoint. extended_price is the current pre/post-market price, set only when the latest
        bar falls in a PRE/POST session. market_local_today is the exchange-local calendar date,
        used to tell completed regular sessions apart from the one in progress.
        """
        try:
            df = ticker.history(period="1d", interval="2m", prepost=True)
        except Exception:
            return (None, None, None)
        if df is None or len(df) == 0:
            return (None, None, None)

        last_ts = df.index[-1]
        last_close = _safe_float(df["Close"].iloc[-1])
        try:
            now = datetime.now(last_ts.tzinfo)
        except Exception:
            return (None, last_close if last_close else None, None)

        now_date = now.date()
        if last_ts.date() != now_date:
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
        return (state, extended_price, now_date)

    def _daily_closes(self, ticker: "yf.Ticker") -> list[tuple[date, float]]:
        """Recent regular-session daily closes (oldest first), for the daily change.

        prepost=False so each close is a true regular-session close, independent of any
        pre/after-hours activity.
        """
        try:
            df = ticker.history(period="1mo", interval="1d", prepost=False, auto_adjust=False)
        except Exception:
            return []
        if df is None or len(df) == 0:
            return []
        out: list[tuple[date, float]] = []
        for idx, row in df.iterrows():
            close = _safe_float(row.get("Close"))
            if close is None:
                continue
            try:
                out.append((idx.date(), close))
            except Exception:
                continue
        return out

    @staticmethod
    def _regular_prices(
        daily: list[tuple[date, float]],
        now_date: date | None,
        state: str | None,
        live_price: float | None,
        fast_prev_close: float | None,
    ) -> tuple[float | None, float | None]:
        """(regular_price, previous_close) driving the *daily* change.

        Derived from completed daily closes so the daily change reflects the last finished
        regular session and does NOT move during pre/after-hours — it only rolls forward once
        the next 9:30 ET open begins. During REGULAR it tracks the live price vs the prior close.
        """
        closes = [c for _, c in daily]
        if not closes:
            # No daily history — fall back to fast_info's own fields.
            return (live_price, fast_prev_close)

        # Sessions strictly before today are "completed"; today's bar (if any) is in progress.
        completed = [c for d, c in daily if d < now_date] if now_date is not None else closes
        today_close = (
            next((c for d, c in daily if d == now_date), None) if now_date is not None else None
        )
        prev_completed = completed[-1] if completed else (closes[-2] if len(closes) >= 2 else fast_prev_close)

        if state == "REGULAR":
            # Today's session is live: current price vs yesterday's close.
            return (live_price or today_close or closes[-1], prev_completed)
        if state == "POST":
            # Today's session just closed: today's close vs yesterday's close.
            return (today_close or closes[-1], prev_completed)
        # PRE, CLOSED, or unknown: last completed regular session vs the one before it.
        if len(completed) >= 2:
            return (completed[-1], completed[-2])
        if len(closes) >= 2:
            return (closes[-1], closes[-2])
        return (closes[-1], fast_prev_close)

    # -- interface -------------------------------------------------------
    def get_quote(self, symbol: str) -> Quote:
        symbol = symbol.upper().strip()
        cached = self._cache_get(self._quote_cache, symbol)
        if cached is not None:
            return cached

        ticker = yf.Ticker(symbol)
        try:
            fi = ticker.fast_info
            live_price = _safe_float(getattr(fi, "last_price", None))
            fast_prev_close = _safe_float(getattr(fi, "previous_close", None))
            currency = getattr(fi, "currency", None)
        except Exception as exc:  # noqa: BLE001
            raise MarketDataError(f"Could not fetch quote for '{symbol}'") from exc

        market_state, extended_price, now_date = self._session(ticker)

        # `price`/`previous_close` describe the regular session (from daily closes), so the
        # daily change stays put through pre/after-hours; `extended_price` carries the live
        # pre/post move separately.
        price, previous_close = self._regular_prices(
            self._daily_closes(ticker), now_date, market_state, live_price, fast_prev_close
        )

        if price is None and previous_close is None:
            raise MarketDataError(f"Unknown or unavailable symbol '{symbol}'")

        change = None
        change_percent = None
        if price is not None and previous_close:
            change = price - previous_close
            change_percent = (change / previous_close) * 100 if previous_close else None

        name = self._name(symbol, ticker)

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

    def get_fundamentals(self, symbol: str) -> Fundamentals:
        symbol = symbol.upper().strip()
        cached = self._cache_get(self._fundamentals_cache, symbol)
        if cached is not None:
            return cached

        try:
            info = yf.Ticker(symbol).info or {}
        except Exception as exc:  # noqa: BLE001
            raise MarketDataError(f"Could not fetch fundamentals for '{symbol}'") from exc
        if not info:
            raise MarketDataError(f"No fundamentals available for '{symbol}'")

        # This yfinance version reports dividendYield already as a percent (AAPL 0.32,
        # KO 2.58, VZ 6.1), so pass it straight through — no fraction→percent scaling.
        dividend_yield = _safe_float(info.get("dividendYield"))

        result = Fundamentals(
            symbol=symbol,
            name=info.get("shortName") or info.get("longName"),
            exchange=info.get("exchange"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            market_cap=_safe_float(info.get("marketCap")),
            pe_ratio=_safe_float(info.get("trailingPE")),
            forward_pe=_safe_float(info.get("forwardPE")),
            eps=_safe_float(info.get("trailingEps")),
            dividend_yield=dividend_yield,
            beta=_safe_float(info.get("beta")),
            fifty_two_week_high=_safe_float(info.get("fiftyTwoWeekHigh")),
            fifty_two_week_low=_safe_float(info.get("fiftyTwoWeekLow")),
            day_high=_safe_float(info.get("dayHigh")),
            day_low=_safe_float(info.get("dayLow")),
            open=_safe_float(info.get("open")),
            previous_close=_safe_float(info.get("regularMarketPreviousClose")),
            volume=_safe_float(info.get("volume")),
            avg_volume=_safe_float(info.get("averageVolume")),
        )
        self._cache_set(self._fundamentals_cache, symbol, result)
        return result

    def get_overview(self) -> MarketOverview:
        cached = self._cache_get(self._overview_cache, "overview")
        if cached is not None:
            return cached

        # Fetch every symbol's quote concurrently; the 15s quote cache dedups repeat calls.
        symbols = INDEX_SYMBOLS + ETF_SYMBOLS + UNIVERSE_SYMBOLS
        quotes: dict[str, Quote] = {}
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(self.get_quote, s): s for s in symbols}
            for fut, sym in futures.items():
                try:
                    quotes[sym] = fut.result()
                except Exception:  # noqa: BLE001
                    continue  # skip symbols that fail; overview is best-effort

        def mover(sym: str) -> MoverQuote | None:
            q = quotes.get(sym)
            if q is None:
                return None
            return MoverQuote(
                symbol=q.symbol,
                name=q.name,
                price=q.price,
                change=q.change,
                change_percent=q.change_percent,
                market_state=q.market_state,
            )

        def movers(syms: list[str]) -> list[MoverQuote]:
            return [m for s in syms if (m := mover(s)) is not None]

        universe = movers(UNIVERSE_SYMBOLS)
        ranked = [m for m in universe if m.change_percent is not None]
        gainers = sorted(ranked, key=lambda m: m.change_percent, reverse=True)[:5]
        losers = sorted(ranked, key=lambda m: m.change_percent)[:5]

        result = MarketOverview(
            indices=movers(INDEX_SYMBOLS),
            gainers=gainers,
            losers=losers,
            etfs=movers(ETF_SYMBOLS),
        )
        self._cache_set(self._overview_cache, "overview", result)
        return result


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
