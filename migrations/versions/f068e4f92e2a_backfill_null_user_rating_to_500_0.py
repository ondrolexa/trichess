"""Backfill NULL user rating to 500.0

Revision ID: f068e4f92e2a
Revises: f37a56b81847
Create Date: 2026-07-16 23:46:19.453994

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "f068e4f92e2a"
down_revision = "f37a56b81847"
branch_labels = None
depends_on = None


def upgrade():
    # User.rating's default=500.0 is Python/ORM-side only, not a DB
    # server_default — both _seed_admin_user and _seed_bot_users (raw SQL
    # INSERTs, bypassing the ORM) left rating NULL, which crashes any
    # template doing `rating|round` (e.g. available.html's seat list) the
    # first time a bot or admin is shown seated in a game.
    op.execute("UPDATE user SET rating = 500.0 WHERE rating IS NULL")


def downgrade():
    # Data-only fix; not reversible (and not worth reversing).
    pass
