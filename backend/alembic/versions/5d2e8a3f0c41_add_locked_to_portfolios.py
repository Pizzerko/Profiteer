"""add locked to portfolios

Revision ID: 5d2e8a3f0c41
Revises: 4c1a7f2e9b30
Create Date: 2026-07-29 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d2e8a3f0c41'
down_revision: Union[str, None] = '4c1a7f2e9b30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = [c['name'] for c in insp.get_columns('portfolios')]
    if 'locked' in cols:
        return
    # server_default so existing rows get a concrete value; the model default handles new rows.
    with op.batch_alter_table('portfolios', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('locked', sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table('portfolios', schema=None) as batch_op:
        batch_op.drop_column('locked')
