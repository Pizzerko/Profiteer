from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


# Import models so that Alembic's autogenerate and Base.metadata.create_all see them.
# (Imported at the bottom to avoid circular imports.)
from app.models import holding, portfolio, trade, user  # noqa: E402,F401
