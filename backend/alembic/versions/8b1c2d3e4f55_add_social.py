"""add social layer: follows, competitions, public profile fields, competition entries

Revision ID: 8b1c2d3e4f55
Revises: 7a0f1e2d3c44
Create Date: 2026-08-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b1c2d3e4f55'
down_revision: Union[str, None] = '7a0f1e2d3c44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Every step is guarded: a dev DB may already have these objects from
    # Base.metadata.create_all() on app startup.
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())

    if 'follows' not in tables:
        op.create_table(
            'follows',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('follower_id', sa.Integer(), nullable=False),
            sa.Column('followee_id', sa.Integer(), nullable=False),
            # NOT NULL to match the model (older tables in this repo drifted here; new ones don't).
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['follower_id'], ['users.id']),
            sa.ForeignKeyConstraint(['followee_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('follower_id', 'followee_id', name='uq_follow_pair'),
        )
        op.create_index(op.f('ix_follows_follower_id'), 'follows', ['follower_id'])
        op.create_index(op.f('ix_follows_followee_id'), 'follows', ['followee_id'])

    if 'competitions' not in tables:
        op.create_table(
            'competitions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('description', sa.String(length=500), nullable=True),
            sa.Column('creator_id', sa.Integer(), nullable=False),
            sa.Column('starting_cash', sa.Float(), nullable=False),
            sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['creator_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_competitions_creator_id'), 'competitions', ['creator_id'])

    # --- users: public profile fields -------------------------------------
    user_cols = {c['name'] for c in insp.get_columns('users')}
    if 'display_name' not in user_cols:
        op.add_column('users', sa.Column('display_name', sa.String(length=50), nullable=True))
    if 'bio' not in user_cols:
        op.add_column('users', sa.Column('bio', sa.String(length=280), nullable=True))
    if 'public_portfolio_id' not in user_cols:
        # Intentionally no ForeignKey: portfolios.user_id already references users, and a constraint
        # back the other way would make the pair circular — which SQLite can't express (no
        # ALTER TABLE ADD CONSTRAINT). Integrity is maintained in the app layer.
        op.add_column('users', sa.Column('public_portfolio_id', sa.Integer(), nullable=True))

    # --- portfolios: competition entries ----------------------------------
    portfolio_cols = {c['name'] for c in insp.get_columns('portfolios')}
    if 'competition_id' not in portfolio_cols:
        # batch mode: SQLite can't ALTER in a FK or a UNIQUE constraint, so the table is rebuilt.
        with op.batch_alter_table('portfolios') as batch:
            batch.add_column(sa.Column('competition_id', sa.Integer(), nullable=True))
            batch.add_column(sa.Column('final_value', sa.Float(), nullable=True))
            batch.create_foreign_key(
                'fk_portfolios_competition_id', 'competitions', ['competition_id'], ['id']
            )
            batch.create_unique_constraint(
                'uq_portfolio_competition_entry', ['user_id', 'competition_id']
            )
        op.create_index(op.f('ix_portfolios_competition_id'), 'portfolios', ['competition_id'])

    # Backfill: publish each existing user's first own portfolio, matching the signup default.
    # Public profiles only expose symbols, weights and return percentages — never cash, dollar
    # values or position sizes.
    op.execute(
        """
        UPDATE users SET public_portfolio_id = (
            SELECT MIN(p.id) FROM portfolios p
            WHERE p.user_id = users.id AND p.competition_id IS NULL
        )
        WHERE public_portfolio_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_portfolios_competition_id'), table_name='portfolios')
    with op.batch_alter_table('portfolios') as batch:
        batch.drop_constraint('uq_portfolio_competition_entry', type_='unique')
        batch.drop_constraint('fk_portfolios_competition_id', type_='foreignkey')
        batch.drop_column('final_value')
        batch.drop_column('competition_id')

    op.drop_column('users', 'public_portfolio_id')
    op.drop_column('users', 'bio')
    op.drop_column('users', 'display_name')

    op.drop_index(op.f('ix_competitions_creator_id'), table_name='competitions')
    op.drop_table('competitions')

    op.drop_index(op.f('ix_follows_followee_id'), table_name='follows')
    op.drop_index(op.f('ix_follows_follower_id'), table_name='follows')
    op.drop_table('follows')
