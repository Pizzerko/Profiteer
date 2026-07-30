from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment / .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "Profiteer API"
    environment: str = "development"

    # Database — SQLite for local dev; swap DATABASE_URL for Postgres later.
    database_url: str = "sqlite:///./profiteer.db"

    # Auth
    secret_key: str = "dev-secret-change-me"  # override in .env for anything real
    access_token_expire_minutes: int = 60 * 24  # 24h for dev
    jwt_algorithm: str = "HS256"

    # CORS — the Vite dev server origins allowed to call this API.
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # Allow any localhost/127.0.0.1 port during dev (Vite may auto-pick a port).
    cors_origin_regex: str = r"^http://(localhost|127\.0\.0\.1):\d+$"

    # Paper trading defaults
    starting_cash: float = 100_000.0
    # Maintenance margin: equity must stay ≥ this fraction of gross exposure. 1.0 ⇒ NO leverage —
    # gross exposure can't exceed equity, so buying power = cash for a long book (shorts still work
    # but consume buying power 1:1). Lower it (e.g. 0.5 ⇒ 2x, 0.25 ⇒ 4x) to allow margin.
    maintenance_margin_ratio: float = 1.0

    # Market data cache TTL (seconds) — yfinance scrapes Yahoo; caching avoids rate limits.
    quote_cache_ttl: int = 15
    history_cache_ttl: int = 300
    news_cache_ttl: int = 300
    fundamentals_cache_ttl: int = 900  # .info is heavy; fundamentals change slowly
    overview_cache_ttl: int = 60  # market-overview page (indices/movers/ETFs)

    # How often the background poller checks resting orders (limit/stop/trailing) for fills.
    order_poll_interval_seconds: int = 30

    # Options
    option_cache_ttl: int = 45  # option-chain pulls are heavy; cache a bit longer than quotes
    # 0DTE contracts can't be opened/closed in the final N minutes of the regular session, unless
    # the underlying is an index (see index_option_underlyings) — mirrors Robinhood's rule.
    option_0dte_cutoff_minutes: int = 15
    # Index underlyings exempt from the 0DTE last-N-minutes lockout (they cash-settle, no assignment
    # risk). Include Yahoo caret aliases so ^GSPC/^NDX/etc. resolve too.
    index_option_underlyings: set[str] = {
        "SPX", "SPXW", "NDX", "NDXP", "VIX", "RUT", "XSP",
        "^GSPC", "^NDX", "^RUT", "^VIX", "^SPX",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
