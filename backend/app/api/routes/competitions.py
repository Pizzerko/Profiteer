from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.competition import Competition
from app.models.portfolio import Portfolio
from app.models.user import User
from app.schemas.social import CompetitionCreate, CompetitionOut, StandingRow
from app.services.competitions import (
    ACTIVE,
    ENDED,
    UPCOMING,
    as_utc,
    competition_status,
    finalize_ended_competitions,
    standings,
)

router = APIRouter(prefix="/competitions", tags=["competitions"])

# Live contests first, then ones about to start, then the archive.
_STATUS_ORDER = {ACTIVE: 0, UPCOMING: 1, ENDED: 2}


def _get(db: Session, competition_id: int) -> Competition:
    comp = db.get(Competition, competition_id)
    if comp is None:
        raise HTTPException(status_code=404, detail="Competition not found")
    return comp


def _entry_of(comp: Competition, user_id: int) -> Portfolio | None:
    return next((e for e in comp.entries if e.user_id == user_id), None)


def _out(db: Session, comp: Competition, user: User) -> CompetitionOut:
    mine = _entry_of(comp, user.id)
    return CompetitionOut(
        id=comp.id,
        name=comp.name,
        description=comp.description,
        status=competition_status(comp),
        starting_cash=comp.starting_cash,
        starts_at=as_utc(comp.starts_at),
        ends_at=as_utc(comp.ends_at),
        created_at=as_utc(comp.created_at),
        creator_username=comp.creator.username,
        entrants=len(comp.entries),
        joined=mine is not None,
        entry_portfolio_id=mine.id if mine else None,
        is_creator=comp.creator_id == user.id,
    )


@router.get("", response_model=list[CompetitionOut])
def list_competitions(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[CompetitionOut]:
    comps = list(db.scalars(select(Competition)))
    comps.sort(key=lambda c: (_STATUS_ORDER[competition_status(c)], -c.id))
    return [_out(db, c, user) for c in comps]


@router.post("", response_model=CompetitionOut, status_code=201)
def create_competition(
    payload: CompetitionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CompetitionOut:
    """Create a contest. `starts_at` may be in the past (it starts immediately), but it must not
    already be over — otherwise nobody could ever trade in it."""
    starts_at = as_utc(payload.starts_at)
    ends_at = as_utc(payload.ends_at)
    if ends_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="The end time must be in the future.")

    comp = Competition(
        name=payload.name.strip(),
        description=(payload.description or "").strip() or None,
        creator_id=user.id,
        starting_cash=payload.starting_cash,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    db.add(comp)
    db.commit()
    db.refresh(comp)
    return _out(db, comp, user)


@router.post("/{competition_id}/join", response_model=CompetitionOut, status_code=201)
def join_competition(
    competition_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CompetitionOut:
    """Join by creating a dedicated entry portfolio funded with the contest's starting cash."""
    comp = _get(db, competition_id)
    if competition_status(comp) == ENDED:
        raise HTTPException(status_code=400, detail="This competition has already ended.")
    if _entry_of(comp, user.id) is not None:
        raise HTTPException(status_code=409, detail="You've already joined this competition.")

    db.add(
        Portfolio(
            user_id=user.id,
            name=comp.name,
            cash_balance=comp.starting_cash,
            starting_balance=comp.starting_cash,
            competition_id=comp.id,
        )
    )
    db.commit()
    db.refresh(comp)
    return _out(db, comp, user)


@router.delete("/{competition_id}/leave", status_code=204)
def leave_competition(
    competition_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Withdraw and discard the entry portfolio. Blocked once results are final."""
    comp = _get(db, competition_id)
    if competition_status(comp) == ENDED:
        raise HTTPException(
            status_code=400, detail="This competition has ended — its results are final."
        )
    entry = _entry_of(comp, user.id)
    if entry is None:
        raise HTTPException(status_code=404, detail="You haven't joined this competition.")

    if user.public_portfolio_id == entry.id:  # defensive: entries can't be published anyway
        user.public_portfolio_id = None
    db.delete(entry)  # cascades holdings/trades/orders
    db.commit()


@router.delete("/{competition_id}", status_code=204)
def delete_competition(
    competition_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Creator-only. Ended competitions are kept as a permanent record of their results."""
    comp = _get(db, competition_id)
    if comp.creator_id != user.id:
        raise HTTPException(status_code=403, detail="Only the creator can delete a competition.")
    if competition_status(comp) == ENDED:
        raise HTTPException(
            status_code=400, detail="An ended competition is kept as a record and can't be deleted."
        )
    db.delete(comp)  # cascades entry portfolios
    db.commit()


@router.get("/{competition_id}/standings", response_model=list[StandingRow])
def competition_standings(
    competition_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[StandingRow]:
    comp = _get(db, competition_id)
    if competition_status(comp) == ENDED:
        # Freeze on first read rather than waiting for the next poller pass, so the standings a
        # user sees right after the bell are already the final ones. Idempotent.
        finalize_ended_competitions(db)

    return [
        StandingRow(
            rank=rank,
            username=entry.user.username,
            display_name=entry.user.display_name,
            return_percent=pct,
            is_me=entry.user_id == user.id,
            final=entry.final_value is not None,
        )
        for entry, pct, rank in standings(db, comp)
    ]
