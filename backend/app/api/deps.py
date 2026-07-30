from fastapi import Depends, HTTPException, Query, status
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
    """The user's default (lowest-id) portfolio."""
    portfolio = db.scalar(
        select(Portfolio).where(Portfolio.user_id == user.id).order_by(Portfolio.id)
    )
    if portfolio is None:
        raise HTTPException(status_code=404, detail="No portfolio found for user")
    return portfolio


def get_selected_portfolio(
    portfolio_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Portfolio:
    """The portfolio named by ?portfolio_id (scoped to the user), else the default one.

    Backward compatible: with no portfolio_id this behaves exactly like get_default_portfolio.
    """
    if portfolio_id is None:
        return get_default_portfolio(db, user)
    portfolio = db.get(Portfolio, portfolio_id)
    if portfolio is None or portfolio.user_id != user.id:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return portfolio
