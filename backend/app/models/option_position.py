from datetime import datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OptionPosition(Base):
    """An open option position (one row per distinct contract per portfolio).

    `quantity` is signed like a stock holding: positive = long (bought), negative = written
    (short). `avg_price` is the average premium *per share* of the open side (× 100 for the
    contract's dollar value). Written positions are always collateralised — `collateral_kind`
    is "covered" (100 underlying shares per contract held) or "cash_secured" (strike × 100 cash
    reserved); naked writing is disallowed.
    """

    __tablename__ = "option_positions"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "occ_symbol", name="uq_option_portfolio_occ"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id"), index=True, nullable=False
    )
    underlying: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    # OCC contract symbol, e.g. "AAPL250815C00190000" — uniquely identifies the contract.
    occ_symbol: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    option_type: Mapped[str] = mapped_column(String(4), nullable=False)  # "call" | "put"
    strike: Mapped[float] = mapped_column(Float, nullable=False)
    expiration: Mapped[datetime] = mapped_column(Date, index=True, nullable=False)
    # Signed: positive = long, negative = written/short.
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    # Average premium per share of the open side.
    avg_price: Mapped[float] = mapped_column(Float, nullable=False)
    # "covered" | "cash_secured" for a short; None for a long.
    collateral_kind: Mapped[str | None] = mapped_column(String(12), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="option_positions")  # noqa: F821
