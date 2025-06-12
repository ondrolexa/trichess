from datetime import timedelta

from flask import Flask
from flask_bootstrap import Bootstrap5
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
CORS(app)

# Configuration of application, see configuration.py, choose one and uncomment.
# app.config.from_object('webapp.configuration.ProductionConfig')
app.config.from_object("webapp.configuration.DevelopmentConfig")
# app.config.from_object('webapp.configuration.TestingConfig')

app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=30)

bs = Bootstrap5(app)  # bootstrap-flask
db = SQLAlchemy(app)  # flask-sqlalchemy
jwt = JWTManager(app)  # JWT

lm = LoginManager()
lm.setup_app(app)
lm.login_view = "login"

from webapp.api import blueprint as api

app.register_blueprint(api, url_prefix="/api/v1")

from webapp import models, views
