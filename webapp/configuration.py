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
    SQLALCHEMY_DATABASE_URI = "sqlite:///trichess.db"
    BOOTSTRAP_FONTAWESOME = True
    SECRET_KEY = os.environ.get(
        "FLASK_SECRET_KEY", "dev-fallback-change-me-in-production"
    )
    JWT_SECRET_KEY = os.environ.get(
        "JWT_SECRET_KEY", "dev-fallback-change-me-in-production"
    )
    CSRF_ENABLED = True
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PROPAGATE_EXCEPTIONS = True
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "")
