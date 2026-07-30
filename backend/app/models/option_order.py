from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OptionOrder(Base):
    """A resting (non-immediate) option order: limit, stop, or trailing stop.

    Mirrors the stock `Order` stack but for a single option contract. Orders sit at status "open"
    until the background poller (app/services/orders.py) sees the contract's mark cross the trigger
    during a regular session and fills them via app/services/options.py::place_option_order.
    Immediate market option orders don't live here — they go straight through POST /options/orders.
    """

    __tablename__ = "option_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id"), index=True, nullable=False
    )
    underlying: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    occ_symbol: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    option_type: Mapped[str] = mapped_column(String(4), nullable=False)  # "call" | "put"
    strike: Mapped[float] = mapped_column(Float, nullable=False)
    expiration: Mapped[date] = mapped_column(Date, nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # "buy" | "sell"
    # "limit" | "stop" | "trailing_stop"
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)  # whole contracts

    # Exactly one of these is set depending on order_type. All evaluate against the contract's mark.
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
    filled_option_trade_id: Mapped[int | None] = mapped_column(
        ForeignKey("option_trades.id"), nullable=True
    )

    portfolio: Mapped["Portfolio"] = relationship(back_populates="option_orders")  # noqa: F821
