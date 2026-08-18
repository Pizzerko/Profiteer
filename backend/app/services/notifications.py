"""Creating and reading notifications.

Notifications are written at the moment an event happens and never recomputed — see the docstring
on `models.notification.Notification` for why the text is frozen rather than derived.

Nothing in here commits. Callers own the transaction, so an invite and the notification announcing
it land in the same commit: a user can never see "you were invited" for an invite that failed to
save, and an invite can never exist silently.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.notification import Notification


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def notify(
    db: Session,
    *,
    user_id: int,
    kind: str,
    title: str,
    body: str | None = None,
    competition_id: int | None = None,
) -> Notification:
    """Queue a notification for `user_id`. Added to the session, not committed."""
    n = Notification(
        user_id=user_id,
        kind=kind,
        title=title,
        body=body,
        competition_id=competition_id,
    )
    db.add(n)
    return n


def list_for(db: Session, user_id: int, limit: int = 50) -> list[Notification]:
    """A user's notifications, newest first."""
    return list(
        db.scalars(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
        )
    )


def unread_count(db: Session, user_id: int) -> int:
    return (
        db.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id, Notification.read_at.is_(None)
            )
        )
        or 0
    )


def mark_read(db: Session, user_id: int, notification_id: int) -> Notification | None:
    """Mark one notification read. Returns None if it isn't this user's (or doesn't exist)."""
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user_id:
        return None
    if n.read_at is None:
        n.read_at = _utcnow()
        db.commit()
    return n


def mark_all_read(db: Session, user_id: int) -> int:
    """Mark every unread notification read. Returns how many were affected."""
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=_utcnow())
    )
    db.commit()
    return result.rowcount or 0
