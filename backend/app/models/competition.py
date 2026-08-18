from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String
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

    Three fields shape who may enter and what a win is worth:

    * `visibility` — "public" (anyone can join from the Public tab) or "private" (an invite-only
      lobby; joining requires a pending `CompetitionInvite` from the host).
    * `timeframe` — "day" | "week" | "month". `ends_at` is *derived* from it at creation time
      rather than being picked freehand, so every contest fits one of three comparable buckets —
      which is what makes per-timeframe win records meaningful.
    * `ranked` — whether winning this contest counts toward the winner's public record. An unranked
      contest is a friendly: it still has standings, it just never touches anyone's stats.
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

    # "public" | "private" — see app.services.competitions.PUBLIC / PRIVATE.
    visibility: Mapped[str] = mapped_column(String(10), default="public", nullable=False)
    # "day" | "week" | "month" — see app.services.competitions.TIMEFRAMES.
    timeframe: Mapped[str] = mapped_column(String(10), default="week", nullable=False)
    # Whether the winner's record on their profile counts this contest.
    ranked: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    creator: Mapped["User"] = relationship()  # noqa: F821
    # Entry portfolios. Deleting a competition removes its entries (they only exist for the contest).
    entries: Mapped[list["Portfolio"]] = relationship(  # noqa: F821
        back_populates="competition", cascade="all, delete-orphan"
    )
    invites: Mapped[list["CompetitionInvite"]] = relationship(  # noqa: F821
        back_populates="competition", cascade="all, delete-orphan"
    )
    # Invite/result notifications naming this contest. Cascaded so deleting a competition can't
    # leave a notification pointing at an id that no longer resolves.
    notifications: Mapped[list["Notification"]] = relationship(  # noqa: F821
        back_populates="competition", cascade="all, delete-orphan"
    )
