"""competition visibility/timeframe/ranked, invites, notifications, win-stat privacy

Revision ID: 9c2d3e4f5a66
Revises: 8b1c2d3e4f55
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c2d3e4f5a66'
down_revision: Union[str, None] = '8b1c2d3e4f55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Every step is guarded: a dev DB may already have these objects from
    # Base.metadata.create_all() on app startup.
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())

    # --- competitions: visibility, timeframe, ranked -----------------------
    #
    # Each NOT NULL column is added with a server_default so existing rows have a value, and the
    # default is then *left in place*: SQLite has no ALTER COLUMN, and dropping it would mean
    # rebuilding the whole table through batch mode for no gain. It's inert either way — the ORM
    # always supplies these fields on insert, so the DDL default never actually fires.
    comp_cols = {c['name'] for c in insp.get_columns('competitions')}
    if 'visibility' not in comp_cols:
        op.add_column(
            'competitions',
            sa.Column('visibility', sa.String(length=10), nullable=False, server_default='public'),
        )
    if 'timeframe' not in comp_cols:
        # 'week' for anything predating timeframes: contests were free-form then, and a week is the
        # closest of the three buckets to what the create form used to default to.
        op.add_column(
            'competitions',
            sa.Column('timeframe', sa.String(length=10), nullable=False, server_default='week'),
        )
    if 'ranked' not in comp_cols:
        # Existing contests were run before wins counted for anything. Marking them unranked keeps
        # records honest — nobody gains a win retroactively from a contest they entered casually.
        op.add_column(
            'competitions',
            sa.Column('ranked', sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    # --- users: win-stat privacy ------------------------------------------
    user_cols = {c['name'] for c in insp.get_columns('users')}
    if 'show_competition_stats' not in user_cols:
        op.add_column(
            'users',
            sa.Column(
                'show_competition_stats', sa.Boolean(), nullable=False, server_default=sa.true()
            ),
        )

    # --- competition_invites ----------------------------------------------
    if 'competition_invites' not in tables:
        op.create_table(
            'competition_invites',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('competition_id', sa.Integer(), nullable=False),
            sa.Column('inviter_id', sa.Integer(), nullable=False),
            sa.Column('invitee_id', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(length=10), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['competition_id'], ['competitions.id']),
            sa.ForeignKeyConstraint(['inviter_id'], ['users.id']),
            sa.ForeignKeyConstraint(['invitee_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('competition_id', 'invitee_id', name='uq_competition_invitee'),
        )
        op.create_index(
            op.f('ix_competition_invites_competition_id'), 'competition_invites',
            ['competition_id'],
        )
        op.create_index(
            op.f('ix_competition_invites_invitee_id'), 'competition_invites', ['invitee_id'],
        )

    # --- notifications ------------------------------------------------------
    if 'notifications' not in tables:
        op.create_table(
            'notifications',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('kind', sa.String(length=32), nullable=False),
            sa.Column('title', sa.String(length=120), nullable=False),
            sa.Column('body', sa.String(length=300), nullable=True),
            sa.Column('competition_id', sa.Integer(), nullable=True),
            sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.ForeignKeyConstraint(['competition_id'], ['competitions.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'])
        op.create_index(
            op.f('ix_notifications_competition_id'), 'notifications', ['competition_id'],
        )


def downgrade() -> None:
    op.drop_index(op.f('ix_notifications_competition_id'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_user_id'), table_name='notifications')
    op.drop_table('notifications')

    op.drop_index(
        op.f('ix_competition_invites_invitee_id'), table_name='competition_invites',
    )
    op.drop_index(
        op.f('ix_competition_invites_competition_id'), table_name='competition_invites',
    )
    op.drop_table('competition_invites')

    op.drop_column('users', 'show_competition_stats')

    op.drop_column('competitions', 'ranked')
    op.drop_column('competitions', 'timeframe')
    op.drop_column('competitions', 'visibility')
