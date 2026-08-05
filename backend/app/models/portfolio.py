from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Portfolio(Base):
    __tablename__ = "portfolios"
    # One entry per user per competition. NULLs aren't compared, so a user can still hold any
    # number of ordinary (non-competition) portfolios.
    __table_args__ = (
        UniqueConstraint("user_id", "competition_id", name="uq_portfolio_competition_entry"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), default="Default", nullable=False)
    cash_balance: Mapped[float] = mapped_column(Float, nullable=False)
    starting_balance: Mapped[float] = mapped_column(Float, nullable=False)
    # Set True when the portfolio is wiped out (total value ≤ 0). Trading is frozen until the user
    # acknowledges by resetting ("Start over").
    locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # --- Competition entry ------------------------------------------------
    # Set when this portfolio is a competition entry rather than one of the user's own portfolios.
    # Entries are hidden from the portfolio switcher and can't be deleted directly (leave instead).
    competition_id: Mapped[int | None] = mapped_column(
        ForeignKey("competitions.id"), index=True, nullable=True
    )
    # Total value snapshotted when the competition ended, so standings stay frozen afterwards
    # instead of drifting with live prices.
    final_value: Mapped[float | None] = mapped_column(Float, nullable=True)

    user: Mapped["User"] = relationship(back_populates="portfolios")  # noqa: F821
    competition: Mapped["Competition | None"] = relationship(  # noqa: F821
        back_populates="entries"
    )
    holdings: Mapped[list["Holding"]] = relationship(  # noqa: F821
        back_populates="portfolio", cascade="all, delete-orphan"
    )
    trades: Mapped[list["Trade"]] = relationship(  # noqa: F821
        back_populates="portfolio", cascade="all, delete-orphan"
    )
    orders: Mapped[list["Order"]] = relationship(  # noqa: F821
        back_populates="portfolio", cascade="all, delete-orphan"
    )
    option_positions: Mapped[list["OptionPosition"]] = relationship(  # noqa: F821
        back_populates="portfolio", cascade="all, delete-orphan"
    )
    option_trades: Mapped[list["OptionTrade"]] = relationship(  # noqa: F821
        back_populates="portfolio", cascade="all, delete-orphan"
    )
    option_orders: Mapped[list["OptionOrder"]] = relationship(  # noqa: F821
        back_populates="portfolio", cascade="all, delete-orphan"
    )
