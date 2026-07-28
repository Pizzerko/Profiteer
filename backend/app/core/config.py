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

    # Market data cache TTL (seconds) — yfinance scrapes Yahoo; caching avoids rate limits.
    quote_cache_ttl: int = 15
    history_cache_ttl: int = 300
    news_cache_ttl: int = 300
    fundamentals_cache_ttl: int = 900  # .info is heavy; fundamentals change slowly
    overview_cache_ttl: int = 60  # market-overview page (indices/movers/ETFs)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
