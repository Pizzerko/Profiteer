from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.community import (
    AttachableTrade,
    FeedMode,
    PostCreate,
    PostLikeOut,
    PostOut,
)
from app.services.community import (
    CommunityError,
    attachable_trades,
    build_post,
    build_posts,
    create_post,
    delete_post,
    list_posts,
    set_like,
)

router = APIRouter(prefix="/community", tags=["community"])


# Declared before "/posts" so the literal path isn't shadowed by anything dynamic added later.
@router.get("/attachable-trades", response_model=list[AttachableTrade])
def get_attachable_trades(
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AttachableTrade]:
    """Your own recent fills, for the composer to offer. Never anyone else's."""
    return attachable_trades(db, user, limit)


@router.get("/posts", response_model=list[PostOut])
def get_posts(
    feed: FeedMode = Query("popular"),
    symbol: str | None = Query(None, max_length=20),
    limit: int = Query(30, ge=1, le=100),
    before_id: int | None = Query(None, ge=1),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PostOut]:
    """The community feed, optionally filtered to one ticker.

    `feed` picks the ordering and with it the paging cursor: "popular" pages by `offset`, while
    "following" and "latest" page by `before_id`. See `services.community.list_posts` for why the
    two differ.
    """
    posts = list_posts(
        db, user, feed=feed, symbol=symbol, limit=limit, before_id=before_id, offset=offset
    )
    return build_posts(db, posts, user)


@router.post("/posts", response_model=PostOut, status_code=201)
def publish_post(
    payload: PostCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PostOut:
    try:
        post = create_post(db, user, payload)
    except CommunityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return build_post(post, user)


@router.put("/posts/{post_id}/like", response_model=PostLikeOut)
def like_post(
    post_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PostLikeOut:
    """Like a post. Idempotent — liking one you already like just reports the current count."""
    result = set_like(db, user, post_id, True)
    if result is None:
        raise HTTPException(status_code=404, detail="Post not found")
    count, liked = result
    return PostLikeOut(post_id=post_id, like_count=count, liked_by_me=liked)


@router.delete("/posts/{post_id}/like", response_model=PostLikeOut)
def unlike_post(
    post_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PostLikeOut:
    """Take a like back. Idempotent in the same way as liking."""
    result = set_like(db, user, post_id, False)
    if result is None:
        raise HTTPException(status_code=404, detail="Post not found")
    count, liked = result
    return PostLikeOut(post_id=post_id, like_count=count, liked_by_me=liked)


@router.delete("/posts/{post_id}", status_code=204)
def remove_post(
    post_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    # Someone else's post reports 404 rather than 403: whether it exists isn't the caller's business.
    if not delete_post(db, user, post_id):
        raise HTTPException(status_code=404, detail="Post not found")
