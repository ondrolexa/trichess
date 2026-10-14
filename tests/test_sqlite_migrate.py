"""`flask sqlite-to-postgres` (webapp/sqlite_migrate.py) and the SSE seat
check against a real PostgreSQL — only runs with TEST_DATABASE_URL set to
a postgres database (CI does; see tests/conftest.py)."""

from datetime import datetime

import click
import pytest
from sqlalchemy import create_engine, inspect, text

from sse import app as sse
from webapp.main import db
from webapp.models import Log, Score, TriBoard, User
from webapp.sqlite_migrate import _alembic_head, sqlite_to_postgres


@pytest.fixture
def pg(app):
    if db.engine.url.get_backend_name() != "postgresql":
        pytest.skip("needs TEST_DATABASE_URL pointing at PostgreSQL")
    # The app fixture's create_all() seeded admin/bots; the command needs an
    # empty target, like a fresh production database.
    db.session.remove()
    db.drop_all()
    yield app
    db.session.remove()
    with db.engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


@pytest.fixture
def source(app, tmp_path):
    """Legacy-style SQLite file: 0/1 booleans, both datetime spellings."""
    path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{path}")
    db.metadata.create_all(engine)  # seeds admin (1) + Bot 1/Bot 2 (2, 3)
    with engine.begin() as conn:
        conn.execute(
            text(
                'INSERT INTO "user" (id, username, password, active, is_bot, '
                "email_verified, rating, created_at) VALUES "
                "(7, 'alice', 'x', 1, 0, NULL, 512.5, '2025-04-10T10:00:00'), "
                "(9, 'bob', 'x', 0, 0, 1, 480.0, '2025-04-12 16:00:00.123456')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO triboard (id, owner_id, player_0_id, player_1_id, "
                "player_2_id, player_0_accepted, player_1_accepted, "
                "player_2_accepted, status, slog, modified_at) VALUES "
                "(40, 7, 7, 9, 2, 1, 1, 0, 2, 'DNEMFOEM', '2026-01-22 21:56:56')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO score (id, player_id, board_id, score, tag, onmove) "
                "VALUES (5, 7, 40, 2.0, 'N', 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO log (id, level, message, user_id, board_id) "
                "VALUES (100, 'GAME', 'Move made', 7, 40)"
            )
        )
        conn.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        )
        conn.execute(
            text("INSERT INTO alembic_version VALUES (:v)"), {"v": _alembic_head(app)}
        )
    engine.dispose()
    return path


def _quiet(*args):
    pass


def test_copies_rows_values_and_sequences(pg, source):
    report = sqlite_to_postgres(pg, db, str(source), echo=_quiet)
    assert report["user"][0] == 5
    assert report["triboard"] == (1, 40, 8)

    alice = db.session.get(User, 7)
    bob = db.session.get(User, 9)
    assert alice.active is True and alice.is_bot is False
    assert alice.email_verified is None
    assert bob.active is False and bob.email_verified is True
    assert alice.created_at == datetime(2025, 4, 10, 10, 0)
    assert bob.created_at == datetime(2025, 4, 12, 16, 0, 0, 123456)
    tb = db.session.get(TriBoard, 40)
    assert tb.slog == "DNEMFOEM" and tb.player_2_accepted is False
    assert db.session.get(Score, 5).onmove is True
    assert db.session.get(Log, 100).board_id == 40
    assert db.session.get(User, 1).username == "admin"

    # Sequences continue after the copied ids instead of colliding.
    carol = User(username="carol", password="x")
    db.session.add(carol)
    db.session.commit()
    assert carol.id == 10

    with db.engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert version == _alembic_head(pg)


def test_refuses_a_target_with_users(pg, source):
    sqlite_to_postgres(pg, db, str(source), echo=_quiet)
    with pytest.raises(click.ClickException, match="refusing to overwrite"):
        sqlite_to_postgres(pg, db, str(source), echo=_quiet)


def test_bad_source_leaves_target_untouched(pg, source):
    engine = create_engine(f"sqlite:///{source}")
    with engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = 'old'"))
    engine.dispose()
    with pytest.raises(click.ClickException, match="Pre-flight"):
        sqlite_to_postgres(pg, db, str(source), echo=_quiet)
    assert not inspect(db.engine).has_table("user")


def test_failure_mid_copy_rolls_everything_back(pg, source):
    engine = create_engine(f"sqlite:///{source}")
    with engine.begin() as conn:
        conn.execute(text("UPDATE triboard SET player_0_accepted = 'maybe'"))
    engine.dispose()
    with pytest.raises(click.ClickException, match="boolean"):
        sqlite_to_postgres(pg, db, str(source), echo=_quiet)
    assert not inspect(db.engine).has_table("user")


def test_sse_seat_check_on_postgres(pg, source):
    sqlite_to_postgres(pg, db, str(source), echo=_quiet)
    assert sse.user_exists(db.engine, "alice")
    assert not sse.user_exists(db.engine, "nobody")
    assert sse.seated(db.engine, "bob", 40)
    assert not sse.seated(db.engine, "carol", 40)
