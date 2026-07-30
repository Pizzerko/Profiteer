"""create option_orders table

Revision ID: 6e3f9b4a1d52
Revises: 5d2e8a3f0c41
Create Date: 2026-07-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6e3f9b4a1d52'
down_revision: Union[str, None] = '5d2e8a3f0c41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guarded: the dev DB may already have this table via Base.metadata.create_all.
    insp = sa.inspect(op.get_bind())
    if 'option_orders' in insp.get_table_names():
        return
    op.create_table(
        'option_orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('portfolio_id', sa.Integer(), nullable=False),
        sa.Column('underlying', sa.String(length=20), nullable=False),
        sa.Column('occ_symbol', sa.String(length=40), nullable=False),
        sa.Column('option_type', sa.String(length=4), nullable=False),
        sa.Column('strike', sa.Float(), nullable=False),
        sa.Column('expiration', sa.Date(), nullable=False),
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
        sa.Column('filled_option_trade_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id']),
        sa.ForeignKeyConstraint(['filled_option_trade_id'], ['option_trades.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_option_orders_portfolio_id'), 'option_orders', ['portfolio_id'])
    op.create_index(op.f('ix_option_orders_underlying'), 'option_orders', ['underlying'])
    op.create_index(op.f('ix_option_orders_occ_symbol'), 'option_orders', ['occ_symbol'])
    op.create_index(op.f('ix_option_orders_status'), 'option_orders', ['status'])


def downgrade() -> None:
    op.drop_index(op.f('ix_option_orders_status'), table_name='option_orders')
    op.drop_index(op.f('ix_option_orders_occ_symbol'), table_name='option_orders')
    op.drop_index(op.f('ix_option_orders_underlying'), table_name='option_orders')
    op.drop_index(op.f('ix_option_orders_portfolio_id'), table_name='option_orders')
    op.drop_table('option_orders')
