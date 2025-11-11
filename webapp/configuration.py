class Config(object):
    """
    Configuration base, for all environments.
    """

    DEBUG = False
    TESTING = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///trichess.db"
    BOOTSTRAP_FONTAWESOME = True
    SECRET_KEY = "GHJSu2ysdbJS82R0DKQBNH"
    JWT_SECRET_KEY = "i2uhs18w9dHGSjw83dHSUiek"
    CSRF_ENABLED = True
    SQLALCHEMY_TRACK_MODIFICATIONS = True


class Scheduler:
    SCHEDULER_API_ENABLED = True
