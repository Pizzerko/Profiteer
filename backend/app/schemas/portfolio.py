from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TradeRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)


class OrderRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    side: Literal["buy", "sell"]
    order_type: Literal["limit", "stop", "trailing_stop"]
    quantity: float = Field(gt=0)
    limit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    trail_percent: float | None = Field(default=None, gt=0, lt=100)

    @model_validator(mode="after")
    def _require_price_for_type(self) -> "OrderRequest":
        """Each order type needs exactly its own trigger field."""
        required = {
            "limit": "limit_price",
            "stop": "stop_price",
            "trailing_stop": "trail_percent",
        }[self.order_type]
        if getattr(self, required) is None:
            raise ValueError(f"{self.order_type} order requires {required}.")
        return self


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    side: str
    order_type: str
    quantity: float
    limit_price: float | None = None
    stop_price: float | None = None
    trail_percent: float | None = None
    peak_price: float | None = None
    status: str
    note: str | None = None
    created_at: datetime
    filled_at: datetime | None = None
    fill_price: float | None = None
    filled_trade_id: int | None = None


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
    buying_power: float = 0.0
    locked: bool = False
    holdings: list[HoldingOut]


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    starting_cash: float | None = Field(default=None, gt=0)


class PortfolioSummary(BaseModel):
    """Lightweight row for the portfolio switcher."""

    id: int
    name: str
    cash_balance: float
    starting_balance: float
    total_value: float
    locked: bool = False


class PortfolioHistoryPoint(BaseModel):
    date: str  # ISO datetime string (daily granularity)
    value: float  # reconstructed total portfolio value on that day
    # What the starting balance would be worth invested in the S&P 500 over the same window.
    # Only populated when the history is requested with benchmark=true.
    benchmark: float | None = None


class PortfolioHistoryResponse(BaseModel):
    range: str
    points: list[PortfolioHistoryPoint]
