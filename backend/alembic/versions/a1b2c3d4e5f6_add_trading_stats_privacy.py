"""add show_trading_stats privacy flag

Revision ID: a1b2c3d4e5f6
Revises: 9c2d3e4f5a66
Create Date: 2026-08-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '9c2d3e4f5a66'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    user_cols = {c['name'] for c in insp.get_columns('users')}
    if 'show_trading_stats' not in user_cols:
        op.add_column(
            'users',
            sa.Column(
                'show_trading_stats', sa.Boolean(), nullable=False, server_default=sa.true()
            ),
        )


def downgrade() -> None:
    op.drop_column('users', 'show_trading_stats')
