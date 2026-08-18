from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    auth,
    community,
    competitions,
    feed,
    market,
    notifications,
    option_orders,
    options,
    orders,
    portfolio,
    portfolios,
    trades,
    users,
    watchlist,
)
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.services.orders import start_order_poller, stop_order_poller


@asynccontextmanager
async def lifespan(app: FastAPI):
    # For local dev convenience, ensure tables exist. In production, use Alembic migrations.
    Base.metadata.create_all(bind=engine)
    start_order_poller()
    yield
    stop_order_poller()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(market.router)
app.include_router(portfolio.router)
app.include_router(portfolios.router)
app.include_router(trades.router)
app.include_router(orders.router)
app.include_router(options.router)
app.include_router(option_orders.router)
app.include_router(watchlist.router)
app.include_router(users.router)
app.include_router(feed.router)
app.include_router(competitions.router)
app.include_router(notifications.router)
app.include_router(community.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
