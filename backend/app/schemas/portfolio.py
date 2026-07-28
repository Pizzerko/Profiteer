from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TradeRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)


class TradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    side: str
    quantity: float
    price: float
    realized_pl: float | None = None
    executed_at: datetime


class HoldingOut(BaseModel):
    symbol: str
    quantity: float
    avg_cost: float
    current_price: float | None = None
    market_value: float | None = None
    cost_basis: float
    unrealized_pl: float | None = None
    unrealized_pl_percent: float | None = None


class PortfolioOut(BaseModel):
    id: int
    name: str
    cash_balance: float
    starting_balance: float
    holdings_value: float
    total_value: float
    total_pl: float
    total_pl_percent: float
    realized_pl: float
    holdings: list[HoldingOut]


class PortfolioHistoryPoint(BaseModel):
    date: str  # ISO datetime string (daily granularity)
    value: float  # reconstructed total portfolio value on that day
    # What the starting balance would be worth invested in the S&P 500 over the same window.
    # Only populated when the history is requested with benchmark=true.
    benchmark: float | None = None


class PortfolioHistoryResponse(BaseModel):
    range: str
    points: list[PortfolioHistoryPoint]
