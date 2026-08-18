from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CompetitionInvite(Base):
    """The host's invitation for one user to enter one competition.

    This is the access-control record for a private lobby: `services.competitions.can_join` only
    lets a user into a private competition if they hold an invite here. It is *not* the thing the
    invitee sees — that's a `Notification`, created alongside it, which links back to this row.

    Status is stored rather than derived (unlike the competition's own state) because it records a
    decision a person made, not a position of the clock:

    * "pending"  — sent, not yet answered.
    * "accepted" — the invitee joined. Set when their entry portfolio is created.
    * "declined" — the invitee said no. They can still be re-invited (the host re-sends, which
      flips the row back to "pending" rather than inserting a duplicate).

    One row per (competition, invitee): re-inviting updates the existing row.
    """

    __tablename__ = "competition_invites"
    __table_args__ = (
        UniqueConstraint("competition_id", "invitee_id", name="uq_competition_invitee"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id"), index=True, nullable=False
    )
    inviter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    invitee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    competition: Mapped["Competition"] = relationship(back_populates="invites")  # noqa: F821
    inviter: Mapped["User"] = relationship(foreign_keys=[inviter_id])  # noqa: F821
    invitee: Mapped["User"] = relationship(foreign_keys=[invitee_id])  # noqa: F821
