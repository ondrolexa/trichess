class Config(object):
    """
    Configuration base, for all environments.
    """

    DEBUG = False
    TESTING = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///trichess.db"
    BOOTSTRAP_FONTAWESOME = True
    SECRET_KEY = "GHJSu2ysdbJS82R0DKQBNHw23wjJGsw2aNSa"
    JWT_SECRET_KEY = "i2uhs18w9dHGSjw83dHSUiekqS3ush2GSSDDF"
    CSRF_ENABLED = True
    SQLALCHEMY_TRACK_MODIFICATIONS = True


class Scheduler:
    SCHEDULER_API_ENABLED = True
