import os

from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, "..", ".env"))


class Config(object):
    """
    Configuration base, for all environments.
    """

    DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
    TESTING = False
    # Overridable via env var so tests/conftest.py can force sqlite:///:memory:
    # *before* webapp.main's module-level `db = SQLAlchemy(app)` runs. That
    # call reads this value once at import time and permanently caches the
    # resulting engine on the app object — flask-sqlalchemy's own docs say
    # "changes to application config after this call will not be reflected" —
    # so mutating app.config["SQLALCHEMY_DATABASE_URI"] afterwards (e.g. in a
    # pytest fixture) is a silent no-op that leaves the engine pointed at the
    # real db. That exact gap made every pytest run drop/recreate tables
    # against the real instance/trichess.db, which is what was previously
    # being investigated as recurring/unexplained data loss.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "SQLALCHEMY_DATABASE_URI", "sqlite:///trichess.db"
    )
    BOOTSTRAP_FONTAWESOME = True
    SECRET_KEY = os.environ.get(
        "FLASK_SECRET_KEY", "dev-fallback-change-me-in-production"
    )
    JWT_SECRET_KEY = os.environ.get(
        "JWT_SECRET_KEY", "dev-fallback-change-me-in-production"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PROPAGATE_EXCEPTIONS = True
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    BOT_DEPTH = int(os.environ.get("BOT_DEPTH", 3))
    SINGLE_PLAYER_NOTIFICATIONS = (
        os.environ.get("SINGLE_PLAYER_NOTIFICATIONS", "false").lower() == "true"
    )
    BOT_GAMES_REMOVAL = int(os.environ.get("BOT_GAMES_REMOVAL", 15))
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "")
