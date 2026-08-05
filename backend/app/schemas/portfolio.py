from datetime import date, datetime
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
    # Total gain since buying the currently-held shares (= market_value − cost_basis).
    unrealized_pl: float | None = None
    unrealized_pl_percent: float | None = None
    # Today's gain: the position's move since the prior regular-session close.
    todays_pl: float | None = None
    todays_pl_percent: float | None = None


class OptionOrderRequest(BaseModel):
    """Place a market option order (immediate fill during regular hours).

    The contract is identified by `occ_symbol`; the remaining fields come from the chain row the
    user clicked and are validated against the live chain on the server.
    """

    occ_symbol: str = Field(min_length=1, max_length=40)
    underlying: str = Field(min_length=1, max_length=20)
    expiration: str = Field(min_length=1, max_length=10)  # "YYYY-MM-DD"
    option_type: Literal["call", "put"]
    strike: float = Field(gt=0)
    side: Literal["buy", "sell"]
    quantity: int = Field(gt=0)  # whole contracts


class OptionRestingOrderRequest(BaseModel):
    """Place a resting option order (limit / stop / trailing stop).

    The trigger price is evaluated against the contract's own mark (per-share premium). Fills route
    through the same collateral/no-naked rules as market option orders when the poller triggers them.
    """

    occ_symbol: str = Field(min_length=1, max_length=40)
    underlying: str = Field(min_length=1, max_length=20)
    expiration: str = Field(min_length=1, max_length=10)  # "YYYY-MM-DD"
    option_type: Literal["call", "put"]
    strike: float = Field(gt=0)
    side: Literal["buy", "sell"]
    quantity: int = Field(gt=0)  # whole contracts
    order_type: Literal["limit", "stop", "trailing_stop"]
    limit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    trail_percent: float | None = Field(default=None, gt=0, lt=100)

    @model_validator(mode="after")
    def _require_price_for_type(self) -> "OptionRestingOrderRequest":
        """Each order type needs exactly its own trigger field."""
        required = {
            "limit": "limit_price",
            "stop": "stop_price",
            "trailing_stop": "trail_percent",
        }[self.order_type]
        if getattr(self, required) is None:
            raise ValueError(f"{self.order_type} order requires {required}.")
        return self


class OptionOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    underlying: str
    occ_symbol: str
    option_type: str
    strike: float
    expiration: date  # serialized as "YYYY-MM-DD"
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
    filled_option_trade_id: int | None = None


class OptionPositionOut(BaseModel):
    underlying: str
    occ_symbol: str
    option_type: str
    strike: float
    expiration: str  # "YYYY-MM-DD"
    quantity: float  # signed: + long, − written
    avg_price: float  # premium per share
    collateral_kind: str | None = None  # "covered" | "cash_secured" | None
    current_price: float | None = None  # per-share mark
    market_value: float | None = None  # signed, × 100
    cost_basis: float  # signed, × 100
    unrealized_pl: float | None = None
    unrealized_pl_percent: float | None = None
    days_to_expiry: int | None = None


class OptionTradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    underlying: str
    occ_symbol: str
    option_type: str
    strike: float
    expiration: date  # serialized as "YYYY-MM-DD"
    action: str
    quantity: float
    price: float
    realized_pl: float | None = None
    note: str | None = None
    executed_at: datetime


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
    reserved_cash: float = 0.0  # cash locked as collateral by cash-secured puts
    locked: bool = False
    holdings: list[HoldingOut]
    option_positions: list[OptionPositionOut] = []


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    starting_cash: float | None = Field(default=None, gt=0)


class PortfolioSummary(BaseModel):
    """Lightweight row for the portfolio switcher.

    Competition entries are included but tagged, so the switcher can group them separately and
    hide actions (rename/delete) that don't apply to them.
    """

    id: int
    name: str
    cash_balance: float
    starting_balance: float
    total_value: float
    locked: bool = False
    competition_id: int | None = None
    competition_name: str | None = None
    competition_status: str | None = None  # "upcoming" | "active" | "ended"


class PortfolioHistoryPoint(BaseModel):
    date: str  # ISO datetime string (daily granularity)
    value: float  # reconstructed total portfolio value on that day
    # What the starting balance would be worth invested in the S&P 500 over the same window.
    # Only populated when the history is requested with benchmark=true.
    benchmark: float | None = None


class PortfolioHistoryResponse(BaseModel):
    range: str
    points: list[PortfolioHistoryPoint]
