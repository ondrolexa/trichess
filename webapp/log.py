"""Logging for the webapp: the custom GAME level and DBHandler, which persists
records into the Log table.

Only the `webapp` package logger is configured (every module logs through
`logging.getLogger(__name__)`), never the root logger: entry points and
pytest own that.
"""

import logging

# Custom GAME log level (between INFO and WARNING)
GAME = 25
logging.addLevelName(GAME, "GAME")


class DBHandler(logging.Handler):
    """Write log records to the Log table via SQLAlchemy."""

    def emit(self, record):
        try:
            # Imported here: webapp.models needs webapp.main's db, and main
            # sets up logging before it creates db.
            from flask import current_app

            from webapp.models import Log, db

            _ = current_app._get_current_object()
        except RuntimeError, AttributeError:
            return
        # Own connection and transaction, never db.session: committing the
        # request's session here would commit a half-done move (and defeat
        # its rollback) whenever something logs mid-request.
        try:
            with db.engine.begin() as conn:
                if conn.dialect.name == "postgresql":
                    # Never let a log write hang its own request on a row
                    # lock that request holds (its FK check on board/user).
                    conn.exec_driver_sql("SET LOCAL lock_timeout = '2s'")
                conn.execute(
                    Log.__table__.insert().values(
                        level=record.levelname,
                        message=self.format(record),
                        module=record.module,
                        user_id=getattr(record, "user_id", None),
                        board_id=getattr(record, "board_id", None),
                    )
                )
        except Exception:
            # A logging failure must never mask/replace the exception that
            # triggered this log record in the first place.
            self.handleError(record)


def configure_logging():
    """Set the `webapp` logger to INFO, with a stderr handler (the format
    logging.basicConfig used) and DBHandler for GAME and above. Idempotent.

    The logger's own level, not the root's, decides what is emitted, so GAME
    records reach DBHandler under pytest too."""
    logger = logging.getLogger("webapp")
    logger.setLevel(logging.INFO)
    if any(isinstance(h, DBHandler) for h in logger.handlers):
        return
    stream = logging.StreamHandler()
    stream.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
    logger.addHandler(stream)
    db_handler = DBHandler()
    db_handler.setLevel(GAME)
    logger.addHandler(db_handler)
