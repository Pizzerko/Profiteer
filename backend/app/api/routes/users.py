from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.follow import Follow
from app.models.portfolio import Portfolio
from app.models.user import User
from app.schemas.auth import UserOut
from app.schemas.social import ProfileUpdate, PublicProfile, PublicUser
from app.services.social import build_public_profile, build_public_user, search_users

router = APIRouter(prefix="/users", tags=["users"])


def _by_username(db: Session, username: str) -> User:
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# Literal paths are declared before "/{username}" so they aren't swallowed by it.
@router.get("/search", response_model=list[PublicUser])
def search(
    q: str = Query(min_length=1, max_length=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PublicUser]:
    return search_users(db, q, user)


@router.patch("/me", response_model=UserOut)
def update_me(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    """Update your own profile. Omitted fields are left alone; explicit nulls clear them."""
    fields = payload.model_fields_set

    if "display_name" in fields:
        name = (payload.display_name or "").strip()
        user.display_name = name or None
    if "bio" in fields:
        bio = (payload.bio or "").strip()
        user.bio = bio or None
    if "public_portfolio_id" in fields:
        pid = payload.public_portfolio_id
        if pid is None:
            user.public_portfolio_id = None
        else:
            portfolio = db.get(Portfolio, pid)
            if portfolio is None or portfolio.user_id != user.id:
                raise HTTPException(status_code=404, detail="Portfolio not found")
            if portfolio.competition_id is not None:
                raise HTTPException(
                    status_code=400,
                    detail="A competition entry can't be your public portfolio.",
                )
            user.public_portfolio_id = portfolio.id

    db.commit()
    db.refresh(user)
    return user


@router.get("/{username}", response_model=PublicProfile)
def profile(
    username: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PublicProfile:
    return build_public_profile(db, _by_username(db, username), user)


@router.post("/{username}/follow", response_model=PublicUser, status_code=201)
def follow(
    username: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PublicUser:
    target = _by_username(db, username)
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="You can't follow yourself.")
    existing = db.scalar(
        select(Follow).where(Follow.follower_id == user.id, Follow.followee_id == target.id)
    )
    if existing is None:  # idempotent — following twice is a no-op, not a duplicate row
        db.add(Follow(follower_id=user.id, followee_id=target.id))
        db.commit()
    return build_public_user(db, target, user)


@router.delete("/{username}/follow", response_model=PublicUser)
def unfollow(
    username: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PublicUser:
    target = _by_username(db, username)
    existing = db.scalar(
        select(Follow).where(Follow.follower_id == user.id, Follow.followee_id == target.id)
    )
    if existing is not None:
        db.delete(existing)
        db.commit()
    return build_public_user(db, target, user)
