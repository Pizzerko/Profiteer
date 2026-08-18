from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Post(Base):
    """A community post: someone's written take, optionally tagged to tickers and backed by trades.

    The body is stored verbatim, exactly as typed. Cashtags (`$AAPL`) are *also* extracted into
    `post_symbols` at write time so "posts about AAPL" is an indexed lookup rather than a LIKE scan
    over every body — but the body remains the source of truth for rendering, and the frontend
    re-detects cashtags to linkify them. The extracted rows are a search index, not a display model.
    """

    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    body: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped["User"] = relationship(back_populates="posts")  # noqa: F821
    symbols: Mapped[list["PostSymbol"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )
    trades: Mapped[list["PostTrade"]] = relationship(
        back_populates="post", cascade="all, delete-orphan", order_by="PostTrade.executed_at"
    )
    likes: Mapped[list["PostLike"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )


class PostSymbol(Base):
    """One ticker mentioned by a post — the index behind `GET /community/posts?symbol=`.

    One row per distinct symbol per post: mentioning `$AAPL` three times in one body is still one
    row, so filtering can't return the same post repeatedly.
    """

    __tablename__ = "post_symbols"
    __table_args__ = (UniqueConstraint("post_id", "symbol", name="uq_post_symbol"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), index=True, nullable=False)

    post: Mapped["Post"] = relationship(back_populates="symbols")


class PostTrade(Base):
    """A trade the author chose to publish alongside their post — a *snapshot*, not a reference.

    Two reasons this copies the numbers instead of pointing at `trades.id`:

    * **It can't dangle.** Trades are owned by a portfolio and cascade away with it, so a real
      foreign key would either delete the attachment out from under a published post or leave it
      pointing at nothing. Deleting a portfolio should not rewrite what you already said.
    * **It's a record of a disclosure.** Like `Notification`, this freezes what was true at the
      moment it was published rather than re-deriving itself later.

    This is also the one place the API publishes a position *size*. That's deliberate and
    author-driven: quantities appear only for trades someone explicitly attached to a post of their
    own. Nothing here is derived from a portfolio automatically — see the module docstring of
    `schemas/social.py`, which carves out exactly this exception.

    `quantity` means shares for a stock and contracts for an option; `label` is the human-readable
    rendering ("AAPL", or "AAPL $210 call 2026-09-18") and `kind` says which to expect.
    """

    __tablename__ = "post_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)  # "stock" | "option"
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)  # ticker / underlying
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # "buy" | "sell"
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    post: Mapped["Post"] = relationship(back_populates="trades")


class PostLike(Base):
    """One reader's like on one post — the only engagement signal the app records.

    The pair is unique, so liking twice is a no-op rather than a second row, and a like count is
    therefore a count of *people* rather than of clicks. This is what the Popular feed ranks by
    (see `services.community.list_posts`).

    Unlike `PostTrade`, this is a live reference rather than a snapshot: a like is a standing
    opinion, not a record of something that happened at a moment, so it disappears when either the
    post or the person who left it does.
    """

    __tablename__ = "post_likes"
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_post_like"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    post: Mapped["Post"] = relationship(back_populates="likes")
    user: Mapped["User"] = relationship(back_populates="post_likes")  # noqa: F821
