"""create option_positions and option_trades tables

Revision ID: 6e3f9b4a2d52
Revises: 5d2e8a3f0c41
Create Date: 2026-07-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6e3f9b4a2d52'
down_revision: Union[str, None] = '5d2e8a3f0c41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guarded: the dev DB may already have these tables via Base.metadata.create_all.
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())

    if 'option_positions' not in tables:
        op.create_table(
            'option_positions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('portfolio_id', sa.Integer(), nullable=False),
            sa.Column('underlying', sa.String(length=20), nullable=False),
            sa.Column('occ_symbol', sa.String(length=40), nullable=False),
            sa.Column('option_type', sa.String(length=4), nullable=False),
            sa.Column('strike', sa.Float(), nullable=False),
            sa.Column('expiration', sa.Date(), nullable=False),
            sa.Column('quantity', sa.Float(), nullable=False),
            sa.Column('avg_price', sa.Float(), nullable=False),
            sa.Column('collateral_kind', sa.String(length=12), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('portfolio_id', 'occ_symbol', name='uq_option_portfolio_occ'),
        )
        op.create_index(op.f('ix_option_positions_portfolio_id'), 'option_positions', ['portfolio_id'])
        op.create_index(op.f('ix_option_positions_underlying'), 'option_positions', ['underlying'])
        op.create_index(op.f('ix_option_positions_occ_symbol'), 'option_positions', ['occ_symbol'])
        op.create_index(op.f('ix_option_positions_expiration'), 'option_positions', ['expiration'])

    if 'option_trades' not in tables:
        op.create_table(
            'option_trades',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('portfolio_id', sa.Integer(), nullable=False),
            sa.Column('underlying', sa.String(length=20), nullable=False),
            sa.Column('occ_symbol', sa.String(length=40), nullable=False),
            sa.Column('option_type', sa.String(length=4), nullable=False),
            sa.Column('strike', sa.Float(), nullable=False),
            sa.Column('expiration', sa.Date(), nullable=False),
            sa.Column('action', sa.String(length=16), nullable=False),
            sa.Column('quantity', sa.Float(), nullable=False),
            sa.Column('price', sa.Float(), nullable=False),
            sa.Column('realized_pl', sa.Float(), nullable=True),
            sa.Column('note', sa.String(length=255), nullable=True),
            sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_option_trades_portfolio_id'), 'option_trades', ['portfolio_id'])
        op.create_index(op.f('ix_option_trades_underlying'), 'option_trades', ['underlying'])


def downgrade() -> None:
    op.drop_index(op.f('ix_option_trades_underlying'), table_name='option_trades')
    op.drop_index(op.f('ix_option_trades_portfolio_id'), table_name='option_trades')
    op.drop_table('option_trades')
    op.drop_index(op.f('ix_option_positions_expiration'), table_name='option_positions')
    op.drop_index(op.f('ix_option_positions_occ_symbol'), table_name='option_positions')
    op.drop_index(op.f('ix_option_positions_underlying'), table_name='option_positions')
    op.drop_index(op.f('ix_option_positions_portfolio_id'), table_name='option_positions')
    op.drop_table('option_positions')
