from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.portfolio import Portfolio
from app.models.user import User
from app.schemas.portfolio import PortfolioCreate, PortfolioSummary
from app.services.competitions import competition_status
from app.services.trading import value_portfolio

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


def _summary(db: Session, p: Portfolio) -> PortfolioSummary:
    # An ended entry's value is frozen at its final snapshot, matching what standings show.
    valued = value_portfolio(db, p)
    comp = p.competition
    return PortfolioSummary(
        id=p.id,
        name=p.name,
        cash_balance=p.cash_balance,
        starting_balance=p.starting_balance,
        total_value=p.final_value if p.final_value is not None else valued.total_value,
        locked=p.locked,
        competition_id=comp.id if comp else None,
        competition_name=comp.name if comp else None,
        competition_status=competition_status(comp) if comp else None,
    )


@router.get("", response_model=list[PortfolioSummary])
def list_portfolios(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[PortfolioSummary]:
    """All of the user's portfolios — own ones first, then competition entries."""
    portfolios = db.scalars(
        select(Portfolio)
        .where(Portfolio.user_id == user.id)
        .order_by(Portfolio.competition_id.is_(None).desc(), Portfolio.id)
    )
    return [_summary(db, p) for p in portfolios]


@router.post("", response_model=PortfolioSummary, status_code=201)
def create_portfolio(
    payload: PortfolioCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PortfolioSummary:
    starting = payload.starting_cash if payload.starting_cash is not None else settings.starting_cash
    portfolio = Portfolio(
        user_id=user.id,
        name=payload.name.strip(),
        cash_balance=starting,
        starting_balance=starting,
    )
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    return _summary(db, portfolio)


@router.delete("/{portfolio_id}", status_code=204)
def delete_portfolio(
    portfolio_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    portfolio = db.get(Portfolio, portfolio_id)
    if portfolio is None or portfolio.user_id != user.id:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    if portfolio.competition_id is not None:
        raise HTTPException(
            status_code=400,
            detail="This is a competition entry — leave the competition to remove it.",
        )
    # Only the user's own portfolios count toward the "keep at least one" rule; competition entries
    # come and go with their contests.
    count = db.scalar(
        select(func.count(Portfolio.id)).where(
            Portfolio.user_id == user.id, Portfolio.competition_id.is_(None)
        )
    )
    if count is not None and count <= 1:
        raise HTTPException(status_code=400, detail="You can't delete your only portfolio.")

    # `users.public_portfolio_id` has no FK (see the model), so clear it here rather than leaving a
    # dangling reference behind.
    if user.public_portfolio_id == portfolio.id:
        user.public_portfolio_id = None
    db.delete(portfolio)  # cascades holdings/trades/orders
    db.commit()
