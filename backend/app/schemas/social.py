"""Schemas for the social layer: public profiles, the activity feed, and competitions.

These shapes are deliberately narrower than the owner-facing ones in `schemas/portfolio.py`.
Anything published to other users omits, by construction:

* email addresses,
* cash balances and dollar totals (portfolio value, position value, cost basis),
* position sizes (share/contract quantities).

What's left is *relative* information — return percentages and portfolio weights — plus the prices
trades filled at, which are public market data anyway. Competition standings can rank purely on
return percent because every entry in a competition starts from the same `starting_cash`, so the
ordering is identical to ranking by total value without ever publishing a total.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Profiles & following
# ---------------------------------------------------------------------------


class ProfileUpdate(BaseModel):
    """PATCH /users/me. Fields left out are untouched; explicit `null` clears them.

    Routes distinguish the two cases with `model_fields_set`, so sending
    `{"bio": null}` clears the bio while `{}` leaves it alone.
    """

    display_name: str | None = Field(default=None, max_length=50)
    bio: str | None = Field(default=None, max_length=280)
    public_portfolio_id: int | None = None


class PublicUser(BaseModel):
    """A user as seen by anyone else. Note the absence of `email`."""

    id: int
    username: str
    display_name: str | None = None
    bio: str | None = None
    created_at: datetime
    follower_count: int = 0
    following_count: int = 0
    # Relationship of the *requesting* user to this one.
    is_following: bool = False
    is_me: bool = False


class PublicHolding(BaseModel):
    """A position on a public profile: what they hold and how it's doing — never how much."""

    symbol: str
    # Share of the portfolio's total value held in this position (a ratio, not a dollar figure).
    weight_percent: float | None = None
    unrealized_pl_percent: float | None = None


class CompetitionRecord(BaseModel):
    """One line of a user's competition history, shown on their profile."""

    competition_id: int
    name: str
    status: str  # "upcoming" | "active" | "ended"
    return_percent: float | None = None
    rank: int | None = None
    entrants: int = 0


class PublicProfile(PublicUser):
    """A full public profile: identity, the portfolio they chose to publish, and their record."""

    portfolio_name: str | None = None
    total_return_percent: float | None = None
    holdings: list[PublicHolding] = []
    competitions: list[CompetitionRecord] = []


# ---------------------------------------------------------------------------
# Activity feed
# ---------------------------------------------------------------------------


class FeedItem(BaseModel):
    """A trade by someone you follow.

    Carries the fill *price* (public market data) but not quantity or notional, so followers can
    see what someone traded and where without learning the size of their book.
    """

    id: str  # "t<id>" for stock trades, "o<id>" for option trades — unique across both
    kind: str  # "stock" | "option"
    username: str
    display_name: str | None = None
    symbol: str  # ticker / option underlying
    label: str  # "AAPL", or "AAPL $210 call 2026-09-18"
    side: str  # "buy" | "sell"
    price: float  # per share, or premium per share for options
    executed_at: datetime


# ---------------------------------------------------------------------------
# Competitions
# ---------------------------------------------------------------------------


class CompetitionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    starting_cash: float = Field(default=100_000.0, gt=0)
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def _check_window(self) -> "CompetitionCreate":
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at.")
        return self


class CompetitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    # Derived from the clock, never stored — see services/competitions.competition_status.
    status: str
    # The contest's rules, identical for every entrant and public by design — not anyone's balance.
    starting_cash: float
    starts_at: datetime
    ends_at: datetime
    created_at: datetime
    creator_username: str
    entrants: int = 0
    # Requester-specific.
    joined: bool = False
    entry_portfolio_id: int | None = None
    is_creator: bool = False


class StandingRow(BaseModel):
    rank: int
    username: str
    display_name: str | None = None
    return_percent: float
    is_me: bool = False
    # True once the competition has ended and this entry's result is frozen.
    final: bool = False
