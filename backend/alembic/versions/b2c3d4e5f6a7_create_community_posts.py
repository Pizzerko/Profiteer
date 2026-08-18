"""community posts, their cashtags, and attached trade snapshots

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guarded like the other migrations: a dev DB may already have these from
    # Base.metadata.create_all() on app startup.
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())

    if 'posts' not in tables:
        op.create_table(
            'posts',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('body', sa.String(length=1000), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_posts_user_id'), 'posts', ['user_id'])

    if 'post_symbols' not in tables:
        op.create_table(
            'post_symbols',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('post_id', sa.Integer(), nullable=False),
            sa.Column('symbol', sa.String(length=20), nullable=False),
            sa.ForeignKeyConstraint(['post_id'], ['posts.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('post_id', 'symbol', name='uq_post_symbol'),
        )
        op.create_index(op.f('ix_post_symbols_post_id'), 'post_symbols', ['post_id'])
        op.create_index(op.f('ix_post_symbols_symbol'), 'post_symbols', ['symbol'])

    if 'post_trades' not in tables:
        op.create_table(
            'post_trades',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('post_id', sa.Integer(), nullable=False),
            sa.Column('kind', sa.String(length=8), nullable=False),
            sa.Column('symbol', sa.String(length=20), nullable=False),
            sa.Column('label', sa.String(length=60), nullable=False),
            sa.Column('side', sa.String(length=4), nullable=False),
            sa.Column('quantity', sa.Float(), nullable=False),
            sa.Column('price', sa.Float(), nullable=False),
            sa.Column('executed_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['post_id'], ['posts.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_post_trades_post_id'), 'post_trades', ['post_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_post_trades_post_id'), table_name='post_trades')
    op.drop_table('post_trades')

    op.drop_index(op.f('ix_post_symbols_symbol'), table_name='post_symbols')
    op.drop_index(op.f('ix_post_symbols_post_id'), table_name='post_symbols')
    op.drop_table('post_symbols')

    op.drop_index(op.f('ix_posts_user_id'), table_name='posts')
    op.drop_table('posts')
