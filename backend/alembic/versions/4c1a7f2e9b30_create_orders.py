"""create orders table

Revision ID: 4c1a7f2e9b30
Revises: 3b7e2f9c1a10
Create Date: 2026-07-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4c1a7f2e9b30'
down_revision: Union[str, None] = '3b7e2f9c1a10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guarded: the dev DB may already have this table via Base.metadata.create_all.
    insp = sa.inspect(op.get_bind())
    if 'orders' in insp.get_table_names():
        return
    op.create_table(
        'orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('portfolio_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('side', sa.String(length=4), nullable=False),
        sa.Column('order_type', sa.String(length=16), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('limit_price', sa.Float(), nullable=True),
        sa.Column('stop_price', sa.Float(), nullable=True),
        sa.Column('trail_percent', sa.Float(), nullable=True),
        sa.Column('peak_price', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('filled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('fill_price', sa.Float(), nullable=True),
        sa.Column('filled_trade_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id']),
        sa.ForeignKeyConstraint(['filled_trade_id'], ['trades.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_orders_portfolio_id'), 'orders', ['portfolio_id'])
    op.create_index(op.f('ix_orders_symbol'), 'orders', ['symbol'])
    op.create_index(op.f('ix_orders_status'), 'orders', ['status'])


def downgrade() -> None:
    op.drop_index(op.f('ix_orders_status'), table_name='orders')
    op.drop_index(op.f('ix_orders_symbol'), table_name='orders')
    op.drop_index(op.f('ix_orders_portfolio_id'), table_name='orders')
    op.drop_table('orders')
