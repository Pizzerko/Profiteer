from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Order(Base):
    """A resting (non-immediate) order: limit, stop, or trailing stop.

    Orders sit at status "open" until a background poller (app/services/orders.py) sees the market
    price cross the trigger during a tradeable session and fills them via the normal trading path.
    Immediate market orders don't live here — they go straight through POST /trades.
    """

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id"), index=True, nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # "buy" | "sell"
    # "limit" | "stop" | "trailing_stop"
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)

    # Exactly one of these is set depending on order_type.
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    trail_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    # High-/low-water mark the poller tracks for trailing stops (peak for sells, trough for buys).
    peak_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    # "open" | "filled" | "cancelled" | "rejected"
    status: Mapped[str] = mapped_column(String(12), default="open", index=True, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)  # e.g. rejection reason

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    filled_trade_id: Mapped[int | None] = mapped_column(
        ForeignKey("trades.id"), nullable=True
    )

    portfolio: Mapped["Portfolio"] = relationship(back_populates="orders")  # noqa: F821
