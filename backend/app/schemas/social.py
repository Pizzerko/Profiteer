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

One deliberate exception lives in `schemas/community.py`: a trade someone attaches to a community
post carries its share/contract count. That is a disclosure the author performs by hand, on fills
they choose, about their own book — not something any projection here derives for them. The rule
above still holds for everything the API publishes on a user's behalf.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
    show_competition_stats: bool | None = None
    show_trading_stats: bool | None = None


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
    timeframe: str  # "day" | "week" | "month"
    ranked: bool = True
    return_percent: float | None = None
    rank: int | None = None
    entrants: int = 0
    won: bool = False


class WinRecord(BaseModel):
    """First-place finishes in ranked competitions, split by contest length.

    Keyed by the same strings as `services.competitions.TIMEFRAMES`, which is what lets
    `services.social` tally a win with `setattr(wins, comp.timeframe, ...)`.
    """

    day: int = 0
    week: int = 0
    month: int = 0


class TradingStats(BaseModel):
    """Blended trading performance across a user's personal (non-competition) portfolios.

    Every figure is a percentage, never a dollar amount: windowed P&L is a dollar-weighted blend
    of `(current value - value at window start) / value at window start` summed across accounts,
    and win rate is the share of closed trades (stock sells + option closes/settlements) with
    positive realized P&L. A `None` field means there wasn't enough history to compute it (e.g. no
    trades yet), not that performance was zero.
    """

    pnl_1d_percent: float | None = None
    pnl_3mo_percent: float | None = None
    pnl_1y_percent: float | None = None
    win_rate_percent: float | None = None


class PublicProfile(PublicUser):
    """A full public profile: identity, the portfolio they chose to publish, and their record.

    `wins` is `None` — not a zeroed record — when the user has hidden their stats, so the UI can
    tell "chose not to show" apart from "has never won". The competition *history* below it is
    unaffected: standings are public, and hiding the aggregate isn't meant to erase the contests.
    """

    portfolio_name: str | None = None
    total_return_percent: float | None = None
    holdings: list[PublicHolding] = []
    competitions: list[CompetitionRecord] = []
    wins: WinRecord | None = None
    # Whether this profile publishes its win record. Only meaningful to the owner, who needs it to
    # render the toggle's current state; for anyone else it's implied by `wins`.
    show_competition_stats: bool = True
    # Same "None means hidden" convention as `wins`, for the trading-stats card.
    trading_stats: TradingStats | None = None
    show_trading_stats: bool = True


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
    """The host's choices. Note what is *absent*: `ends_at`.

    The end is derived from `starts_at` + `timeframe` server-side, so a contest can only ever be one
    of the three comparable lengths — a client can't smuggle in a 3-hour "week".
    """

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    starting_cash: float = Field(default=100_000.0, gt=0)
    starts_at: datetime
    timeframe: Literal["day", "week", "month"] = "week"
    visibility: Literal["public", "private"] = "public"
    # Whether a win here lands on the winner's public record.
    ranked: bool = True


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
    visibility: str = "public"
    timeframe: str = "week"
    ranked: bool = True
    # Requester-specific.
    joined: bool = False
    entry_portfolio_id: int | None = None
    is_creator: bool = False
    # For a private lobby: this viewer's invite state — "pending" | "accepted" | "declined", or None
    # if they were never invited (which, for a private contest, is why `can_join` is False).
    invite_status: str | None = None
    can_join: bool = False


class InviteCreate(BaseModel):
    """Who to invite. By username — the handle a host actually knows someone by."""

    username: str = Field(min_length=1, max_length=50)


class CompetitionInviteOut(BaseModel):
    """One row of a host's invite list."""

    id: int
    username: str
    display_name: str | None = None
    status: str  # "pending" | "accepted" | "declined"
    created_at: datetime


class StandingRow(BaseModel):
    rank: int
    username: str
    display_name: str | None = None
    return_percent: float
    is_me: bool = False
    # True once the competition has ended and this entry's result is frozen.
    final: bool = False


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


class NotificationOut(BaseModel):
    """A notification as the owner sees it. Never sent to anyone else."""

    id: int
    kind: str  # "competition_invite" | "competition_result" | "invite_accepted"
    title: str
    body: str | None = None
    competition_id: int | None = None
    read: bool = False
    created_at: datetime
    # Set only for a "competition_invite" the recipient hasn't answered yet — the frontend uses it
    # to decide whether to render Accept / Decline or just a link.
    actionable: bool = False
