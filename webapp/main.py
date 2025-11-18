from datetime import timedelta

import requests
from flask import Flask
from flask_apscheduler import APScheduler
from flask_bootstrap import Bootstrap5
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

app = Flask(__name__)
CORS(app)

# Configuration of application, see configuration.py, choose one and uncomment.
app.config.from_object("webapp.configuration.Config")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=0.01)
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=30)

bs = Bootstrap5(app)  # bootstrap-flask
db = SQLAlchemy(app)  # flask-sqlalchemy
migrate = Migrate(app, db)
jwt = JWTManager(app)  # JWT

lm = LoginManager()
lm.setup_app(app)
lm.login_view = "login"


# notifications
def post_notification(username, text, title, gameid, board):
    if not app.debug:
        if board == "ondro":
            click = f"https://trichess.mykuna.eu/playlx/{gameid}"
        else:
            click = f"https://trichess.mykuna.eu/play/{gameid}"
        try:
            requests.post(
                f"https://ntfy.mykuna.eu/trichess_{username}",
                data=text.encode("utf-8"),
                headers={
                    "Title": title,
                    "Click": click,
                },
            )
        except requests.exceptions.ConnectionError:
            pass

        except Exception as err:
            print(f"Unexpected post notification {err=}, {type(err)=}")


# Background jobs
def resend_notification():
    """Send notification each 24 hours when on move"""
    with scheduler.app.app_context():
        with db.engine.connect() as connection:
            result = connection.execute(
                text(
                    "SELECT * FROM triboard WHERE status=1 AND datetime(modified_at) <=datetime('now', '-24 Hour');"
                )
            )
            for r in result.mappings().all():
                slog = r["slog"]
                moves = [
                    slog[i : i + 4]
                    for i in range(0, len(slog), 4)
                    if slog[i] not in ["S", "R"]
                ]
                onmove = f"player_{len(moves) % 3}_id"
                user = (
                    connection.execute(
                        text(f"SELECT * FROM user WHERE id={r[onmove]};")
                    )
                    .mappings()
                    .first()
                )
                # notify next player
                post_notification(
                    user["username"],
                    f"It's still your turn in game {r['id']}",
                    "Your turn reminder",
                    r["id"],
                    user["board"],
                )


class SchedulerConfig:
    SCHEDULER_API_ENABLED = True
    JOBS = [
        {
            "id": "resend",
            "func": resend_notification,
            "trigger": "interval",
            "seconds": 86400,
        }
    ]


app.config.from_object(SchedulerConfig())
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()
