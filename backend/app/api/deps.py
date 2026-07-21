from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.portfolio import Portfolio
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    subject = decode_access_token(token)
    if subject is None:
        raise _credentials_exc
    try:
        user_id = int(subject)
    except ValueError:
        raise _credentials_exc
    user = db.get(User, user_id)
    if user is None:
        raise _credentials_exc
    return user


def get_default_portfolio(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Portfolio:
    """The user's default (first) portfolio. v1 has one portfolio per user."""
    portfolio = db.scalar(
        select(Portfolio).where(Portfolio.user_id == user.id).order_by(Portfolio.id)
    )
    if portfolio is None:
        raise HTTPException(status_code=404, detail="No portfolio found for user")
    return portfolio
