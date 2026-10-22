from webapp import cli  # noqa: F401  (registers the flask CLI commands)
from webapp.views import app, db

__all__ = ["app", "db"]
__author__ = "Ondrej Lexa"
