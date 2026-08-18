from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.competition import Competition
from app.models.competition_invite import CompetitionInvite
from app.models.notification import Notification
from app.models.portfolio import Portfolio
from app.models.user import User
from app.schemas.social import (
    CompetitionCreate,
    CompetitionInviteOut,
    CompetitionOut,
    InviteCreate,
    StandingRow,
)
from app.services.competitions import (
    ACTIVE,
    ENDED,
    PRIVATE,
    UPCOMING,
    as_utc,
    assert_can_join,
    assert_startable_at,
    can_view,
    competition_status,
    ends_at_for,
    finalize_ended_competitions,
    invite_for,
    standings,
)
from app.services.notifications import notify
from app.services.trading import TradingError

router = APIRouter(prefix="/competitions", tags=["competitions"])

# Live contests first, then ones about to start, then the archive.
_STATUS_ORDER = {ACTIVE: 0, UPCOMING: 1, ENDED: 2}


def _get(db: Session, competition_id: int, user: User) -> Competition:
    """Fetch a competition the user is allowed to see.

    A private lobby they weren't invited to is reported as 404, not 403 — a stranger shouldn't be
    able to probe for the existence of someone else's private contest.
    """
    comp = db.get(Competition, competition_id)
    if comp is None or not can_view(db, comp, user.id):
        raise HTTPException(status_code=404, detail="Competition not found")
    return comp


def _entry_of(comp: Competition, user_id: int) -> Portfolio | None:
    return next((e for e in comp.entries if e.user_id == user_id), None)


def _out(db: Session, comp: Competition, user: User) -> CompetitionOut:
    mine = _entry_of(comp, user.id)
    status = competition_status(comp)
    invite = invite_for(db, comp.id, user.id) if comp.visibility == PRIVATE else None

    if mine is not None or status == ENDED:
        can_join = False
    elif comp.visibility == PRIVATE:
        # The host can always enter their own lobby; everyone else needs an invite they didn't turn
        # down. (A declined invite can be re-sent, which flips it back to pending.)
        can_join = comp.creator_id == user.id or (
            invite is not None and invite.status != "declined"
        )
    else:
        can_join = True

    return CompetitionOut(
        id=comp.id,
        name=comp.name,
        description=comp.description,
        status=status,
        starting_cash=comp.starting_cash,
        starts_at=as_utc(comp.starts_at),
        ends_at=as_utc(comp.ends_at),
        created_at=as_utc(comp.created_at),
        creator_username=comp.creator.username,
        entrants=len(comp.entries),
        visibility=comp.visibility,
        timeframe=comp.timeframe,
        ranked=comp.ranked,
        joined=mine is not None,
        entry_portfolio_id=mine.id if mine else None,
        is_creator=comp.creator_id == user.id,
        invite_status=invite.status if invite else None,
        can_join=can_join,
    )


@router.get("", response_model=list[CompetitionOut])
def list_competitions(
    visibility: str | None = Query(None, pattern="^(public|private)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CompetitionOut]:
    """Competitions this user can see, optionally narrowed to one tab.

    The public/private split is a filter over the same visibility rules, not a second permission
    model: `can_view` already hides private lobbies the user has nothing to do with, so the
    "private" tab shows exactly the ones they host, were invited to, or already entered.
    """
    comps = [c for c in db.scalars(select(Competition)) if can_view(db, c, user.id)]
    if visibility is not None:
        comps = [c for c in comps if c.visibility == visibility]
    comps.sort(key=lambda c: (_STATUS_ORDER[competition_status(c)], -c.id))
    return [_out(db, c, user) for c in comps]


@router.post("", response_model=CompetitionOut, status_code=201)
def create_competition(
    payload: CompetitionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CompetitionOut:
    """Host a contest.

    The end time isn't the host's to choose — it's `starts_at` + the timeframe. The start must land
    inside a regular trading session, so an entry is never created into a market that won't open for
    days. A start in the past is still allowed (the contest begins immediately) as long as it hasn't
    already run out.
    """
    starts_at = as_utc(payload.starts_at)
    try:
        assert_startable_at(starts_at)
        ends_at = ends_at_for(starts_at, payload.timeframe)
    except (TradingError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if ends_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400, detail="That competition would already be over — pick a later start."
        )

    comp = Competition(
        name=payload.name.strip(),
        description=(payload.description or "").strip() or None,
        creator_id=user.id,
        starting_cash=payload.starting_cash,
        starts_at=starts_at,
        ends_at=ends_at,
        visibility=payload.visibility,
        timeframe=payload.timeframe,
        ranked=payload.ranked,
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
    """Join by creating a dedicated entry portfolio funded with the contest's starting cash.

    This is also how an invite is accepted: joining a private lobby marks the invite accepted and
    tells the host, so there's one code path for entering a competition rather than two that could
    drift apart.
    """
    comp = _get(db, competition_id, user)
    if competition_status(comp) == ENDED:
        raise HTTPException(status_code=400, detail="This competition has already ended.")
    if _entry_of(comp, user.id) is not None:
        raise HTTPException(status_code=409, detail="You've already joined this competition.")
    try:
        assert_can_join(db, comp, user.id)
    except TradingError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    db.add(
        Portfolio(
            user_id=user.id,
            name=comp.name,
            cash_balance=comp.starting_cash,
            starting_balance=comp.starting_cash,
            competition_id=comp.id,
        )
    )

    invite = invite_for(db, comp.id, user.id)
    if invite is not None and invite.status != "accepted":
        invite.status = "accepted"
        invite.responded_at = datetime.now(timezone.utc)
        notify(
            db,
            user_id=invite.inviter_id,
            kind=Notification.KIND_INVITE_ACCEPTED,
            title=f"@{user.username} joined {comp.name}",
            body="They accepted your invite.",
            competition_id=comp.id,
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
    comp = _get(db, competition_id, user)
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
    # Leaving a private lobby returns the invite to "pending" rather than deleting it, so the host
    # doesn't have to re-invite someone who left by accident.
    invite = invite_for(db, comp.id, user.id)
    if invite is not None and invite.status == "accepted":
        invite.status = "pending"
        invite.responded_at = None
    db.commit()


@router.delete("/{competition_id}", status_code=204)
def delete_competition(
    competition_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Creator-only. Ended competitions are kept as a permanent record of their results."""
    comp = _get(db, competition_id, user)
    if comp.creator_id != user.id:
        raise HTTPException(status_code=403, detail="Only the creator can delete a competition.")
    if competition_status(comp) == ENDED:
        raise HTTPException(
            status_code=400, detail="An ended competition is kept as a record and can't be deleted."
        )
    db.delete(comp)  # cascades entry portfolios, invites and notifications
    db.commit()


# ---------------------------------------------------------------------------
# Invites
# ---------------------------------------------------------------------------


@router.get("/{competition_id}/invites", response_model=list[CompetitionInviteOut])
def list_invites(
    competition_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CompetitionInviteOut]:
    """Who the host has invited, and what they said. Creator-only — it's the host's guest list."""
    comp = _get(db, competition_id, user)
    if comp.creator_id != user.id:
        raise HTTPException(status_code=403, detail="Only the host can see the invite list.")
    return [
        CompetitionInviteOut(
            id=i.id,
            username=i.invitee.username,
            display_name=i.invitee.display_name,
            status=i.status,
            created_at=as_utc(i.created_at),
        )
        for i in sorted(comp.invites, key=lambda i: i.id)
    ]


@router.post("/{competition_id}/invites", response_model=CompetitionInviteOut, status_code=201)
def invite_user(
    competition_id: int,
    payload: InviteCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CompetitionInviteOut:
    """Invite someone by username, and notify them.

    Re-inviting reuses the existing row rather than inserting a duplicate — which is what makes a
    declined invite re-sendable: the status flips back to "pending" and a fresh notification goes
    out. The invite and its notification share one commit, so neither can exist without the other.
    """
    comp = _get(db, competition_id, user)
    if comp.creator_id != user.id:
        raise HTTPException(status_code=403, detail="Only the host can invite people.")
    if competition_status(comp) == ENDED:
        raise HTTPException(status_code=400, detail="This competition has already ended.")

    target = db.scalar(select(User).where(User.username == payload.username.strip()))
    if target is None:
        raise HTTPException(status_code=404, detail="No user with that username.")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="You're already the host.")
    if _entry_of(comp, target.id) is not None:
        raise HTTPException(status_code=409, detail=f"@{target.username} has already joined.")

    invite = invite_for(db, comp.id, target.id)
    if invite is None:
        invite = CompetitionInvite(
            competition_id=comp.id, inviter_id=user.id, invitee_id=target.id, status="pending"
        )
        db.add(invite)
    elif invite.status == "pending":
        raise HTTPException(status_code=409, detail=f"@{target.username} already has an invite.")
    else:
        invite.status = "pending"
        invite.responded_at = None

    host = user.display_name or f"@{user.username}"
    notify(
        db,
        user_id=target.id,
        kind=Notification.KIND_COMPETITION_INVITE,
        title=f"{host} invited you to {comp.name}",
        # Describes the contest as it is, rather than assuming private — a host may also invite
        # people to a public one, where the invite is a nudge rather than the only way in.
        body=(
            f"A {comp.visibility} {comp.timeframe}-long competition"
            f"{' · counts toward your record' if comp.ranked else ' · just for fun'}."
        ),
        competition_id=comp.id,
    )
    db.commit()
    db.refresh(invite)
    return CompetitionInviteOut(
        id=invite.id,
        username=target.username,
        display_name=target.display_name,
        status=invite.status,
        created_at=as_utc(invite.created_at),
    )


@router.post("/{competition_id}/invites/decline", status_code=204)
def decline_invite(
    competition_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Turn down an invite. The host can send another one later."""
    comp = _get(db, competition_id, user)
    invite = invite_for(db, comp.id, user.id)
    if invite is None:
        raise HTTPException(status_code=404, detail="You don't have an invite to this competition.")
    if invite.status == "accepted":
        raise HTTPException(
            status_code=400, detail="You've already joined — leave the competition instead."
        )
    invite.status = "declined"
    invite.responded_at = datetime.now(timezone.utc)
    db.commit()


@router.get("/{competition_id}/standings", response_model=list[StandingRow])
def competition_standings(
    competition_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[StandingRow]:
    comp = _get(db, competition_id, user)
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
