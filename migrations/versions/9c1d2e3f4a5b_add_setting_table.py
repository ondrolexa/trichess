"""add setting table (maintenance mode)

Revision ID: 9c1d2e3f4a5b
Revises: f068e4f92e2a
Create Date: 2026-10-14 15:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "9c1d2e3f4a5b"
down_revision = "f068e4f92e2a"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "setting",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade():
    op.drop_table("setting")
