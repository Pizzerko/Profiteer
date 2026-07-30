from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_selected_portfolio
from app.db.session import get_db
from app.models.option_order import OptionOrder
from app.models.portfolio import Portfolio
from app.schemas.portfolio import OptionOrderOut, OptionRestingOrderRequest
from app.services.market_data import MarketDataError, get_provider

router = APIRouter(prefix="/option-orders", tags=["option-orders"])


@router.post("", response_model=OptionOrderOut, status_code=201)
def create_option_order(
    payload: OptionRestingOrderRequest,
    portfolio: Portfolio = Depends(get_selected_portfolio),
    db: Session = Depends(get_db),
) -> OptionOrder:
    if portfolio.locked:
        raise HTTPException(
            status_code=400,
            detail="Portfolio is locked — it was wiped out. Start over to continue.",
        )
    try:
        expiration = date.fromisoformat(payload.expiration)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid expiration date.") from exc

    # Seed the trailing-stop water mark from the current contract mark so it trails from now.
    # Best-effort: if the mark is unavailable, the poller seeds it on its first regular-hours pass.
    peak_price: float | None = None
    if payload.order_type == "trailing_stop":
        try:
            contract = get_provider().get_option_contract(
                payload.underlying, payload.expiration, payload.option_type, payload.strike
            )
            peak_price = contract.mark if contract else None
        except MarketDataError:
            peak_price = None

    order = OptionOrder(
        portfolio_id=portfolio.id,
        underlying=payload.underlying.upper().strip(),
        occ_symbol=payload.occ_symbol,
        option_type=payload.option_type,
        strike=payload.strike,
        expiration=expiration,
        side=payload.side,
        order_type=payload.order_type,
        quantity=payload.quantity,
        limit_price=payload.limit_price,
        stop_price=payload.stop_price,
        trail_percent=payload.trail_percent,
        peak_price=peak_price,
        status="open",
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@router.get("", response_model=list[OptionOrderOut])
def list_option_orders(
    status: str | None = Query(None),
    portfolio: Portfolio = Depends(get_selected_portfolio),
    db: Session = Depends(get_db),
) -> list[OptionOrder]:
    stmt = select(OptionOrder).where(OptionOrder.portfolio_id == portfolio.id)
    if status is not None:
        stmt = stmt.where(OptionOrder.status == status)
    return list(db.scalars(stmt.order_by(OptionOrder.created_at.desc())))


@router.delete("/{order_id}", response_model=OptionOrderOut)
def cancel_option_order(
    order_id: int,
    portfolio: Portfolio = Depends(get_selected_portfolio),
    db: Session = Depends(get_db),
) -> OptionOrder:
    order = db.get(OptionOrder, order_id)
    if order is None or order.portfolio_id != portfolio.id:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "open":
        raise HTTPException(status_code=400, detail=f"Order is already {order.status}.")
    order.status = "cancelled"
    db.commit()
    db.refresh(order)
    return order
