"""unique username; rating_history table (backfilled)

Revision ID: 3e5f7a9b1c2d
Revises: 9c1d2e3f4a5b
Create Date: 2026-10-18 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "3e5f7a9b1c2d"
down_revision = "9c1d2e3f4a5b"
branch_labels = None
depends_on = None

# Frozen copy of the Elo rules (webapp/api.py) as of this revision, so the
# backfill keeps meaning the same thing if the app's code changes later.
K = 9.0
L = 400.0
STARTING_RATING = 500.0


def _dedupe_usernames(bind):
    """Before the unique constraint: of several accounts sharing a username,
    keep the active one (else the oldest) and drop the others, which can only
    be never-verified sign-ups. Anything referenced is left for a human."""
    groups = bind.execute(
        sa.text('SELECT username FROM "user" GROUP BY username HAVING COUNT(*) > 1')
    ).scalars()
    for username in list(groups):
        rows = bind.execute(
            sa.text(
                'SELECT id, active FROM "user" WHERE username = :u ORDER BY id'
            ),
            {"u": username},
        ).all()
        active = [r.id for r in rows if r.active]
        if len(active) > 1:
            raise RuntimeError(f"several active users named {username!r}: {active}")
        keep = active[0] if active else rows[0].id
        for row in rows:
            if row.id == keep:
                continue
            referenced = bind.execute(
                sa.text(
                    "SELECT (SELECT COUNT(*) FROM triboard WHERE :i IN "
                    "(owner_id, player_0_id, player_1_id, player_2_id))"
                    " + (SELECT COUNT(*) FROM score WHERE player_id = :i)"
                ),
                {"i": row.id},
            ).scalar()
            if referenced:
                raise RuntimeError(
                    f"duplicate user {username!r} id {row.id} has games; "
                    "rename or merge it by hand, then rerun the upgrade"
                )
            bind.execute(sa.text("DELETE FROM log WHERE user_id = :i"), {"i": row.id})
            bind.execute(sa.text('DELETE FROM "user" WHERE id = :i'), {"i": row.id})


def _backfill_rating_history(bind):
    """Replay every rated game (no bot seat) in order, as Trichess always has,
    recording each player's rating after each game."""
    rows = bind.execute(
        sa.text("""
        SELECT b.id, b.modified_at,
               b.player_0_id, COALESCE(s0.score, 0),
               b.player_1_id, COALESCE(s1.score, 0),
               b.player_2_id, COALESCE(s2.score, 0)
        FROM triboard b
        LEFT JOIN score s0 ON s0.board_id = b.id AND s0.player_id = b.player_0_id
        LEFT JOIN score s1 ON s1.board_id = b.id AND s1.player_id = b.player_1_id
        LEFT JOIN score s2 ON s2.board_id = b.id AND s2.player_id = b.player_2_id
        WHERE b.status = 2
          AND NOT EXISTS (
              SELECT 1 FROM "user" u
              WHERE u.is_bot AND u.id IN (b.player_0_id, b.player_1_id, b.player_2_id)
          )
        ORDER BY b.modified_at, b.id
        """)
    ).all()
    ratings = {}
    history = []
    for board_id, ts, p0, s0, p1, s1, p2, s2 in rows:
        ids, scores = (p0, p1, p2), (s0, s1, s2)
        current = [ratings.get(i, STARTING_RATING) for i in ids]
        q = [10 ** (r / L) for r in current]
        total = sum(q)
        for i, r, s, qi in zip(ids, current, scores, q):
            ratings[i] = r + K * (s - qi / total)
            history.append(
                {"user_id": i, "board_id": board_id, "rating": ratings[i], "ts": ts}
            )
    if history:
        bind.execute(
            sa.text(
                "INSERT INTO rating_history (user_id, board_id, rating, created_at)"
                " VALUES (:user_id, :board_id, :rating, :ts)"
            ),
            history,
        )
    for user_id, rating in ratings.items():
        bind.execute(
            sa.text('UPDATE "user" SET rating = :r WHERE id = :i'),
            {"r": rating, "i": user_id},
        )


def upgrade():
    bind = op.get_bind()
    _dedupe_usernames(bind)
    with op.batch_alter_table("user") as batch:
        batch.create_unique_constraint("user_username_key", ["username"])
    op.create_table(
        "rating_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("board_id", sa.Integer(), nullable=True),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["board_id"], ["triboard.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rating_history_user", "rating_history", ["user_id", "created_at"]
    )
    _backfill_rating_history(bind)


def downgrade():
    op.drop_index("ix_rating_history_user", table_name="rating_history")
    op.drop_table("rating_history")
    with op.batch_alter_table("user") as batch:
        batch.drop_constraint("user_username_key", type_="unique")
