from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Notification(Base):
    """Something that happened *to* a user and that they haven't necessarily seen yet.

    Deliberately dumb: the title and body are rendered once, at the moment the event occurs, and
    stored as plain text. A notification is a record of what was true when it fired, so it must not
    re-derive itself from live state later — "Ann invited you to Summer Cup" should still read that
    way after Ann leaves or the contest ends.

    `competition_id` is the only structured payload, and it is what makes a notification
    *actionable*: for an invite the frontend turns it into Accept / Decline buttons, and for a
    result it becomes a link to the final standings. There is no `invite_id` column on purpose —
    invites are unique per (competition, invitee), so the pending invite behind a
    "competition_invite" notification is always recoverable from `competition_id` + `user_id`,
    and there is no second reference that can dangle.

    Read state is a nullable timestamp rather than a boolean so "when did they see it" is available
    without a second column; `read` is exposed to the API as `read_at is not None`.
    """

    __tablename__ = "notifications"

    KIND_COMPETITION_INVITE = "competition_invite"
    KIND_COMPETITION_RESULT = "competition_result"
    KIND_INVITE_ACCEPTED = "invite_accepted"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str | None] = mapped_column(String(300), nullable=True)
    competition_id: Mapped[int | None] = mapped_column(
        ForeignKey("competitions.id"), index=True, nullable=True
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped["User"] = relationship(back_populates="notifications")  # noqa: F821
    competition: Mapped["Competition"] = relationship(  # noqa: F821
        back_populates="notifications"
    )
