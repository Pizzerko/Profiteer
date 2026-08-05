from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Follow(Base):
    """A directed follow edge: `follower` sees `followee`'s activity in their feed.

    Following is one-way (no approval step) and the pair is unique — following twice is a no-op
    rather than a duplicate row.
    """

    __tablename__ = "follows"
    __table_args__ = (UniqueConstraint("follower_id", "followee_id", name="uq_follow_pair"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    follower_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    followee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    follower: Mapped["User"] = relationship(  # noqa: F821
        foreign_keys=[follower_id], back_populates="following"
    )
    followee: Mapped["User"] = relationship(  # noqa: F821
        foreign_keys=[followee_id], back_populates="followers"
    )
