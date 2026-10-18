import os

from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, "..", ".env"))


def _secret(name):
    """Signing key from env. Outside debug mode a missing key is fatal: a
    shared fallback string would let anyone forge session cookies (admin is
    user id 1), JWTs and password-reset tokens."""
    value = os.environ.get(name)
    if value:
        return value
    debug = os.environ.get("DEBUG", "false").lower() == "true" or os.environ.get(
        "FLASK_DEBUG", ""
    ).lower() in ("1", "true")
    if not debug:
        raise RuntimeError(
            f"{name} must be set (see Help → For developers → Configuration) unless DEBUG=true"
        )
    return "dev-only-insecure-key"


def _required(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} must be set (see Help → For developers → Configuration)"
        )
    return value


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
    # Required, no fallback: a missing URL used to silently create an empty
    # SQLite trichess.db (with a freshly seeded admin) and serve that instead
    # of the real PostgreSQL database (postgresql+psycopg://...).
    SQLALCHEMY_DATABASE_URI = _required("SQLALCHEMY_DATABASE_URI")
    # Drop pooled connections the server closed (e.g. a postgres restart)
    # instead of failing the next request on them.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    BOOTSTRAP_FONTAWESOME = True
    SECRET_KEY = _secret("FLASK_SECRET_KEY")
    JWT_SECRET_KEY = _secret("JWT_SECRET_KEY")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PROPAGATE_EXCEPTIONS = True
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    BOT_DEPTH = int(os.environ.get("BOT_DEPTH", 3))
    SINGLE_PLAYER_NOTIFICATIONS = (
        os.environ.get("SINGLE_PLAYER_NOTIFICATIONS", "false").lower() == "true"
    )
    BOT_GAMES_REMOVAL = int(os.environ.get("BOT_GAMES_REMOVAL", 15))
    # Comma-separated allowlist of usernames that may mint an API bearer
    # token via /token (Swagger UI's "Authorize" dialog included). Normal
    # browser gameplay never calls /token — the board page mints its own
    # token server-side for whoever is logged in (see views.py's /play/<id>)
    # — so this only limits direct API access, not who can play. No
    # hardcoded default — unset means nobody can mint a token until this is
    # configured in .env.
    API_TOKEN_USERS = os.environ.get("API_TOKEN_USERS", "")
    # Base URL of the board live-update SSE service (sse/app.py). Empty means
    # same origin — production, where Traefik routes the events path to it.
    # Local dev runs it on its own port, e.g. http://localhost:8090 (that
    # origin's page must then be listed in CORS_ORIGINS for the service).
    SSE_URL = os.environ.get("SSE_URL", "").rstrip("/")
    # Google Analytics 4 measurement ID (e.g. "G-XXXXXXXXXX"). Empty disables
    # the tag entirely; it is also never rendered in debug mode or for admin.
    GA_MEASUREMENT_ID = os.environ.get("GA_MEASUREMENT_ID", "")
    # Reverse proxies in front of the app (Traefik: 1). Their X-Forwarded-For/
    # -Proto/-Host headers are trusted only with this set, so behind TLS the
    # app sees https (email links, cookies) and the client's real IP (rate
    # limits). Keep 0 where clients reach gunicorn directly, or anyone could
    # spoof their address.
    TRUSTED_PROXY_HOPS = int(os.environ.get("TRUSTED_PROXY_HOPS", 0))
    # Scheme for links built outside a request (CLI, worker).
    PREFERRED_URL_SCHEME = "http" if DEBUG else "https"
    # Login/sign-up rate limits (Flask-Limiter) live in Redis, shared by all
    # gunicorn workers. If Redis is unreachable, limits fall back to
    # per-process memory instead of failing the request.
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", REDIS_URL)
    RATELIMIT_KEY_PREFIX = "trichess"
    RATELIMIT_SWALLOW_ERRORS = True
    RATELIMIT_IN_MEMORY_FALLBACK_ENABLED = True
    RATELIMIT_ENABLED = os.environ.get("RATELIMIT_ENABLED", "true").lower() == "true"
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "")
