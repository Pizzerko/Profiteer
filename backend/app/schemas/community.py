"""Schemas for the community feed: posts, their cashtags, and the trades authors attach.

This module is the one documented exception to the "never publish position sizes" rule stated in
`schemas/social.py`. `PostTradeOut` carries a share/contract count, because attaching a trade is an
explicit act by its owner — they pick specific fills and publish them. Nothing here is derived from
a portfolio automatically, and a post can only ever carry trades belonging to its own author.

Note the direction of trust on the way in: `PostCreate` takes trade *references* ("t42"), never
trade data. The server resolves each reference against the author's own rows and snapshots the real
numbers, so a client cannot publish a fill it didn't make, at a size or price it didn't get.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Which ordering the feed is asked for. "popular" ranks by likes decayed by age, "following"
# restricts to people the reader follows (plus themselves), "latest" is everyone, newest first.
FeedMode = Literal["popular", "following", "latest"]


class PostTradeOut(BaseModel):
    """A trade published alongside a post. Frozen at post time — see `models.post.PostTrade`."""

    kind: str  # "stock" | "option"
    symbol: str  # ticker, or the option's underlying
    label: str  # "AAPL", or "AAPL $210 call 2026-09-18"
    side: str  # "buy" | "sell"
    # Shares for a stock, contracts for an option.
    quantity: float
    # Per share, or premium per share for an option.
    price: float
    executed_at: datetime


class AttachableTrade(PostTradeOut):
    """One of your own recent fills, offered in the composer. Owner-facing only.

    `ref` is the opaque handle the composer sends back in `PostCreate.trade_refs` — "t<id>" for a
    stock trade and "o<id>" for an option trade, the same scheme `FeedItem.id` uses to keep the two
    ledgers distinct in one list.

    `portfolio_name` exists so you can see *which* book a fill came from before publishing it (a
    competition entry, say). It is shown while choosing and then dropped: it never reaches
    `PostTradeOut`, so the published post doesn't disclose how many portfolios you run or what
    they're called.
    """

    ref: str
    portfolio_name: str


class PostCreate(BaseModel):
    """A new post. Cashtags are parsed out of `body` server-side, not sent separately."""

    body: str = Field(min_length=1, max_length=1000)
    # Capped so one post can't become a full trade-log dump.
    trade_refs: list[str] = Field(default_factory=list, max_length=5)


class PostOut(BaseModel):
    """A post as anyone reading the community feed sees it."""

    id: int
    username: str
    display_name: str | None = None
    body: str
    # Distinct tickers mentioned, uppercased. The body keeps the text as typed; this is the index.
    symbols: list[str] = []
    trades: list[PostTradeOut] = []
    created_at: datetime
    # Whether the reader wrote this — the frontend uses it to offer Delete.
    is_mine: bool = False
    # How many distinct people have liked this, and whether the reader is one of them. Both are
    # computed per request against the viewer, never stored on the post.
    like_count: int = 0
    liked_by_me: bool = False


class PostLikeOut(BaseModel):
    """The like state of one post after liking or unliking it.

    Returned instead of the whole post so the client can settle an optimistic toggle against the
    server's count without re-rendering (or re-fetching) the post body and its trades.
    """

    post_id: int
    like_count: int
    liked_by_me: bool
