from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # --- Public profile ----------------------------------------------------
    display_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bio: Mapped[str | None] = mapped_column(String(280), nullable=True)
    # Which portfolio this user shows on their public profile; NULL ⇒ profile shows no holdings.
    # Deliberately NOT a ForeignKey: portfolios.user_id already points here, so a real constraint
    # would make users ↔ portfolios circular, which SQLite can't satisfy (it has no
    # ALTER TABLE ADD CONSTRAINT). Ownership is validated on write (routes/users.py), the id is
    # cleared when that portfolio is deleted (routes/portfolios.py), and reads treat an id that no
    # longer resolves to one of the user's own portfolios as "no public portfolio".
    public_portfolio_id: Mapped[int | None] = mapped_column(nullable=True)
    # Whether this user's competition win record is shown to anyone else. Opt-out, not opt-in:
    # standings are public already, so the record only aggregates what a visitor could tally by
    # hand. When False the API omits the counts entirely rather than sending zeros — see
    # `services.social.build_public_profile`.
    show_competition_stats: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Whether this user's trading stats (windowed P&L%, win rate — blended across their personal
    # portfolios) are shown to anyone else. Same opt-out-not-opt-in shape as the win record above.
    show_trading_stats: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    portfolios: Mapped[list["Portfolio"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    posts: Mapped[list["Post"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    # Likes this user left on *other people's* posts. Their likes on their own posts cascade via
    # `posts` above; this edge is what stops a deleted account leaving likes behind on posts that
    # outlive it.
    post_likes: Mapped[list["PostLike"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    watchlist: Mapped[list["WatchlistItem"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    # Follow edges. `following` = rows where I'm the follower; `followers` = rows where I'm followed.
    following: Mapped[list["Follow"]] = relationship(  # noqa: F821
        foreign_keys="Follow.follower_id", back_populates="follower", cascade="all, delete-orphan"
    )
    followers: Mapped[list["Follow"]] = relationship(  # noqa: F821
        foreign_keys="Follow.followee_id", back_populates="followee", cascade="all, delete-orphan"
    )
