from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.social import NotificationOut
from app.services.competitions import invite_for
from app.services.notifications import list_for, mark_all_read, mark_read, unread_count

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _out(db: Session, n: Notification, user: User) -> NotificationOut:
    """Project a notification, resolving whether it still needs an answer.

    `actionable` is computed at read time rather than stored: an invite notification stops offering
    Accept / Decline the moment the invite is answered *anywhere* — by the buttons here, by joining
    from the competition page, or by leaving. One source of truth (the invite's own status) instead
    of a flag that has to be kept in step with it.
    """
    actionable = False
    if n.kind == Notification.KIND_COMPETITION_INVITE and n.competition_id is not None:
        invite = invite_for(db, n.competition_id, user.id)
        actionable = invite is not None and invite.status == "pending"

    return NotificationOut(
        id=n.id,
        kind=n.kind,
        title=n.title,
        body=n.body,
        competition_id=n.competition_id,
        read=n.read_at is not None,
        created_at=n.created_at,
        actionable=actionable,
    )


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[NotificationOut]:
    return [_out(db, n, user) for n in list_for(db, user.id)]


@router.get("/unread-count")
def get_unread_count(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict[str, int]:
    """Cheap enough for the navbar to poll — a single COUNT, no joins."""
    return {"count": unread_count(db, user.id)}


@router.post("/read-all", status_code=204)
def read_all(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> None:
    mark_all_read(db, user.id)


@router.post("/{notification_id}/read", response_model=NotificationOut)
def read_one(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationOut:
    n = mark_read(db, user.id, notification_id)
    if n is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return _out(db, n, user)
