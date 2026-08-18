"""likes on community posts

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guarded like the other migrations: a dev DB may already have this from
    # Base.metadata.create_all() on app startup.
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())

    if 'post_likes' not in tables:
        op.create_table(
            'post_likes',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('post_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['post_id'], ['posts.id']),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
            # One like per person per post: liking twice is a no-op, so a like count counts
            # people rather than clicks.
            sa.UniqueConstraint('post_id', 'user_id', name='uq_post_like'),
        )
        op.create_index(op.f('ix_post_likes_post_id'), 'post_likes', ['post_id'])
        op.create_index(op.f('ix_post_likes_user_id'), 'post_likes', ['user_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_post_likes_user_id'), table_name='post_likes')
    op.drop_index(op.f('ix_post_likes_post_id'), table_name='post_likes')
    op.drop_table('post_likes')
