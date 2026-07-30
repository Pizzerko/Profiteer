from datetime import datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OptionTrade(Base):
    """The options ledger: one row per fill or expiry settlement, for history + realized P&L.

    Kept separate from the stock `trades` table because option cash flows are per-share × 100
    and the historical portfolio-value reconstruction (which prices trades 1:1) must not treat
    them as shares.
    """

    __tablename__ = "option_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id"), index=True, nullable=False
    )
    underlying: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    occ_symbol: Mapped[str] = mapped_column(String(40), nullable=False)
    option_type: Mapped[str] = mapped_column(String(4), nullable=False)  # "call" | "put"
    strike: Mapped[float] = mapped_column(Float, nullable=False)
    expiration: Mapped[datetime] = mapped_column(Date, nullable=False)
    # "buy" | "sell" | "settle"
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)  # contracts (always positive)
    price: Mapped[float] = mapped_column(Float, nullable=False)  # premium per share (0 if worthless)
    realized_pl: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="option_trades")  # noqa: F821
