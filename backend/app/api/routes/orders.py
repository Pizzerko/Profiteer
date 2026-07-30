from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_selected_portfolio
from app.db.session import get_db
from app.models.order import Order
from app.models.portfolio import Portfolio
from app.schemas.portfolio import OrderOut, OrderRequest
from app.services.market_data import MarketDataError, get_provider

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=OrderOut, status_code=201)
def create_order(
    payload: OrderRequest,
    portfolio: Portfolio = Depends(get_selected_portfolio),
    db: Session = Depends(get_db),
) -> Order:
    if portfolio.locked:
        raise HTTPException(
            status_code=400,
            detail="Portfolio is locked — it was wiped out. Start over to continue.",
        )
    symbol = payload.symbol.upper().strip()

    # Seed the trailing-stop water mark from the current price so it trails from now, not from the
    # first poll. Best-effort: if the quote fails, the poller seeds it on its first tradeable pass.
    peak_price: float | None = None
    if payload.order_type == "trailing_stop":
        try:
            quote = get_provider().get_quote(symbol)
            peak_price = quote.effective_price if quote.effective_price else quote.price
        except MarketDataError:
            peak_price = None

    order = Order(
        portfolio_id=portfolio.id,
        symbol=symbol,
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


@router.get("", response_model=list[OrderOut])
def list_orders(
    status: str | None = Query(None),
    portfolio: Portfolio = Depends(get_selected_portfolio),
    db: Session = Depends(get_db),
) -> list[Order]:
    stmt = select(Order).where(Order.portfolio_id == portfolio.id)
    if status is not None:
        stmt = stmt.where(Order.status == status)
    return list(db.scalars(stmt.order_by(Order.created_at.desc())))


@router.delete("/{order_id}", response_model=OrderOut)
def cancel_order(
    order_id: int,
    portfolio: Portfolio = Depends(get_selected_portfolio),
    db: Session = Depends(get_db),
) -> Order:
    order = db.get(Order, order_id)
    if order is None or order.portfolio_id != portfolio.id:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "open":
        raise HTTPException(status_code=400, detail=f"Order is already {order.status}.")
    order.status = "cancelled"
    db.commit()
    db.refresh(order)
    return order
