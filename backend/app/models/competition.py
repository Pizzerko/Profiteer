from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Competition(Base):
    """A time-boxed trading contest. Each entrant gets a dedicated portfolio.

    There is no stored status column — status is derived from `starts_at`/`ends_at` (see
    `app.services.competitions.competition_status`) so it can never drift out of sync with the
    clock. Every entry starts with the same `starting_cash`, which is what lets standings rank
    by return percent without ever publishing dollar values.
    """

    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    starting_cash: Mapped[float] = mapped_column(Float, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    creator: Mapped["User"] = relationship()  # noqa: F821
    # Entry portfolios. Deleting a competition removes its entries (they only exist for the contest).
    entries: Mapped[list["Portfolio"]] = relationship(  # noqa: F821
        back_populates="competition", cascade="all, delete-orphan"
    )
