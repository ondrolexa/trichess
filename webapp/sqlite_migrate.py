"""One-time copy of the legacy SQLite database into PostgreSQL.

`flask --app=webapp sqlite-to-postgres --sqlite instance/trichess.db` (see
README's cut-over runbook). The source is opened read-only and never
modified. Everything on the target (schema, rows, sequences, alembic_version
and the verification) runs in a single transaction, so any failure leaves
the target database exactly as empty as it started.
"""

from datetime import datetime

import click
from alembic.script import ScriptDirectory
from flask_migrate import Migrate
from sqlalchemy import Boolean, DateTime, String, create_engine, func, inspect, text
from sqlalchemy import select as sa_select

BATCH = 1000


class MigrationError(click.ClickException):
    pass


def _to_bool(value):
    # SQLite has no boolean type; rows hold 0/1 (or '0'/'1' from a quoted
    # DEFAULT). bool('0') would be True, so compare explicitly.
    if value is None or isinstance(value, bool):
        return value
    if str(value).strip().lower() in ("1", "t", "true"):
        return True
    if str(value).strip().lower() in ("0", "f", "false"):
        return False
    raise MigrationError(f"Unrecognized boolean value {value!r}")


def _to_datetime(value):
    if value is None or isinstance(value, datetime):
        return value
    try:
        # Accepts both "YYYY-MM-DD HH:MM:SS[.ffffff]" and the "T" form.
        return datetime.fromisoformat(str(value))
    except ValueError as err:
        raise MigrationError(f"Unrecognized datetime value {value!r}") from err


def _converters(table):
    conv = {}
    for col in table.columns:
        if isinstance(col.type, Boolean):
            conv[col.name] = _to_bool
        elif isinstance(col.type, DateTime):
            conv[col.name] = _to_datetime
    return conv


def _alembic_head(app):
    migrate: Migrate = app.extensions["migrate"].migrate
    with app.app_context():
        config = migrate.get_config()
    return ScriptDirectory.from_config(config).get_current_head()


def _preflight(source, tables, head):
    """Refuse anything that wouldn't copy 1:1: unfinished migrations, a
    schema drifted from the models, orphaned foreign keys, or strings longer
    than PostgreSQL will accept (SQLite never enforces VARCHAR lengths)."""
    problems = []
    with source.connect() as conn:
        insp = inspect(conn)
        names = set(insp.get_table_names())
        if "alembic_version" not in names:
            problems.append("source has no alembic_version table")
        else:
            versions = [
                r[0]
                for r in conn.execute(text("SELECT version_num FROM alembic_version"))
            ]
            if versions != [head]:
                problems.append(
                    f"source alembic_version {versions} != head {head!r}; run `flask db upgrade` on it first"
                )
        for table in tables:
            if table.name not in names:
                problems.append(f"source is missing table {table.name!r}")
                continue
            src_cols = {c["name"] for c in insp.get_columns(table.name)}
            model_cols = {c.name for c in table.columns}
            if src_cols != model_cols:
                problems.append(
                    f"{table.name}: columns differ from the models "
                    f"(only in source: {sorted(src_cols - model_cols)}, "
                    f"only in models: {sorted(model_cols - src_cols)})"
                )
                continue
            for col in table.columns:
                if isinstance(col.type, String) and col.type.length:
                    longest = conn.execute(
                        text(f'SELECT MAX(LENGTH("{col.name}")) FROM "{table.name}"')
                    ).scalar()
                    if longest and longest > col.type.length:
                        problems.append(
                            f"{table.name}.{col.name}: value of length {longest} "
                            f"exceeds VARCHAR({col.type.length})"
                        )
        orphans = conn.execute(text("PRAGMA foreign_key_check")).fetchall()
        if orphans:
            problems.append(f"foreign key violations in source: {orphans[:10]}")
    if problems:
        raise MigrationError("Pre-flight failed:\n  - " + "\n  - ".join(problems))


def _fingerprint(conn, table):
    """Per-table numbers compared between source and target after the copy."""
    cols = [func.count(), func.max(table.c.id)]
    if "slog" in table.c:
        cols.append(func.coalesce(func.sum(func.length(table.c.slog)), 0))
    return tuple(conn.execute(sa_select(*cols).select_from(table)).one())


def sqlite_to_postgres(app, db, sqlite_path, echo=click.echo):
    """Copy every model table from the SQLite file at `sqlite_path` into the
    app's (empty) PostgreSQL database. Returns {table: fingerprint}."""
    from webapp import models

    target = db.engine
    if target.url.get_backend_name() != "postgresql":
        raise MigrationError(
            f"Target database must be PostgreSQL, got {target.url.get_backend_name()!r}"
        )
    with target.connect() as conn:
        if inspect(conn).has_table("user"):
            if conn.execute(text('SELECT COUNT(*) FROM "user"')).scalar():
                raise MigrationError(
                    "Target already has users — refusing to overwrite it"
                )

    source = create_engine(f"sqlite:///file:{sqlite_path}?mode=ro&uri=true")
    tables = list(db.metadata.sorted_tables)  # parents before children
    head = _alembic_head(app)
    report = {}
    try:
        _preflight(source, tables, head)
        with source.connect() as src, target.begin() as dst:
            models.SEED_DEFAULT_USERS = False
            try:
                db.metadata.create_all(dst)
            finally:
                models.SEED_DEFAULT_USERS = True

            for table in tables:
                conv = _converters(table)
                result = src.execute(text(f'SELECT * FROM "{table.name}" ORDER BY id'))
                copied = 0
                while rows := result.mappings().fetchmany(BATCH):
                    batch = [
                        {k: conv.get(k, lambda v: v)(v) for k, v in row.items()}
                        for row in rows
                    ]
                    dst.execute(table.insert(), batch)
                    copied += len(batch)
                if "id" in table.c:
                    dst.execute(
                        text(
                            f"SELECT setval(pg_get_serial_sequence('\"{table.name}\"', 'id'), "
                            f'COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM "{table.name}"'
                        )
                    )
                src_fp, dst_fp = _fingerprint(src, table), _fingerprint(dst, table)
                if src_fp != dst_fp:
                    raise MigrationError(
                        f"{table.name}: verification mismatch source={src_fp} target={dst_fp}"
                    )
                report[table.name] = dst_fp
                echo(f"{table.name}: {copied} rows copied, verified {dst_fp}")

            dst.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                )
            )
            dst.execute(text("DELETE FROM alembic_version"))
            dst.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                {"v": head},
            )
    finally:
        source.dispose()
    echo(f"Done; alembic_version stamped {head}")
    return report
