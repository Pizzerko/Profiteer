"""merge the two option migration heads

`6e3f9b4a1d52` (option_orders) and `6e3f9b4a2d52` (options) were both written against
`5d2e8a3f0c41`, leaving the history forked with two heads. This is an empty merge point so
`alembic upgrade head` resolves to a single revision again.

Revision ID: 7a0f1e2d3c44
Revises: 6e3f9b4a1d52, 6e3f9b4a2d52
Create Date: 2026-08-04 00:00:00.000000

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = '7a0f1e2d3c44'
down_revision: Union[str, Sequence[str], None] = ('6e3f9b4a1d52', '6e3f9b4a2d52')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
