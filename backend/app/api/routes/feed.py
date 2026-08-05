from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.social import FeedItem
from app.services.social import build_feed

router = APIRouter(prefix="/feed", tags=["feed"])


@router.get("", response_model=list[FeedItem])
def feed(
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FeedItem]:
    """Trades from the people you follow, newest first (see services.social.build_feed)."""
    return build_feed(db, user, limit)
