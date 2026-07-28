"""add realized_pl to trades

Revision ID: 3b7e2f9c1a10
Revises: 2a4c112e1bd3
Create Date: 2026-07-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3b7e2f9c1a10'
down_revision: Union[str, None] = '2a4c112e1bd3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('trades', schema=None) as batch_op:
        batch_op.add_column(sa.Column('realized_pl', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('trades', schema=None) as batch_op:
        batch_op.drop_column('realized_pl')
