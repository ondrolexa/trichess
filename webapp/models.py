import os
import secrets
from datetime import datetime, timedelta

from dotenv import load_dotenv
from sqlalchemy import text
from werkzeug.security import generate_password_hash

from webapp.main import db

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, "..", ".env"))


class User(db.Model):  # ty: ignore
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64))
    password = db.Column(db.String(500))
    email = db.Column(db.String(120), unique=True)
    email_verified = db.Column(db.Boolean, default=False)
    theme = db.Column(db.String(16), default="default")
    board = db.Column(db.String(16), default="ondro")
    pieces = db.Column(db.String(16), default="default")
    active = db.Column(db.Boolean, default=True)
    is_bot = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.text("0")
    )
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    last_login = db.Column(db.DateTime)
    rating = db.Column(db.Float, default=500.0)

    # Relationships
    scores = db.relationship("Score", backref="player", lazy="select")

    def score(self):
        return sum(score.score for score in self.scores) if self.scores else 0

    def recent_score(self):
        thirty_days_ago = datetime.today() - timedelta(days=30)
        return sum(
            score.score
            for score in self.scores
            if score.board and score.board.modified_at > thirty_days_ago
        )

    def stats(self):
        stats = {"win": 0, "coop": 0, "pass": 0, "loss": 0}
        for score in self.scores:
            if score.score == 2:
                stats["win"] += 1
            elif score.score > 0:
                stats["coop"] += 1
            else:
                if score.onmove or score.tag == "R":
                    stats["loss"] += 1
                else:
                    stats["pass"] += 1
        return stats

    @property
    def is_admin(self):
        return self.id == 1

    def is_authenticated(self):
        return True

    def is_active(self):
        return self.active

    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    def __repr__(self):
        return f"<User {self.username!r}>"


class TriBoard(db.Model):  # ty: ignore
    __tablename__ = "triboard"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    player_0_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    player_1_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    player_2_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    player_0_accepted = db.Column(db.Boolean, default=False)
    player_1_accepted = db.Column(db.Boolean, default=False)
    player_2_accepted = db.Column(db.Boolean, default=False)

    status = db.Column(db.Integer, nullable=False, default=0)
    slog = db.Column(db.Text, default="")

    created_at = db.Column(db.DateTime, server_default=db.func.now())
    started_at = db.Column(db.DateTime, server_default=db.func.now())
    modified_at = db.Column(
        db.DateTime, server_default=db.func.now(), onupdate=db.func.now()
    )

    # Explicit foreign key mapping for relationships
    owner = db.relationship(User, foreign_keys=[owner_id])
    player_0 = db.relationship(User, foreign_keys=[player_0_id])
    player_1 = db.relationship(User, foreign_keys=[player_1_id])
    player_2 = db.relationship(User, foreign_keys=[player_2_id])

    scores = db.relationship("Score", backref="board")

    @classmethod
    def for_player(cls, user_id):
        """Filter expression matching boards where user_id occupies any of the 3 seats."""
        return db.or_(
            cls.player_0_id == user_id,
            cls.player_1_id == user_id,
            cls.player_2_id == user_id,
        )


class Score(db.Model):  # ty: ignore
    __tablename__ = "score"
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    board_id = db.Column(db.Integer, db.ForeignKey("triboard.id"))
    score = db.Column(db.Float)
    tag = db.Column(db.String(1), default="N")
    onmove = db.Column(db.Boolean, default=False)


class Log(db.Model):
    __tablename__ = "log"
    __table_args__ = (db.Index("ix_log_level_created", "level", "created_at"),)

    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.String(16), nullable=False)
    message = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    board_id = db.Column(db.Integer, db.ForeignKey("triboard.id"), nullable=True)
    module = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    user = db.relationship("User", backref="logs", lazy="select")
    board = db.relationship("TriBoard", backref="logs", lazy="select")


def _seed_admin_user(target, connection, **kwargs):
    # Bound parameter, not string interpolation — the hash (e.g. "scrypt:32768:8:1$...")
    # contains ":"/"$" characters that break a raw-DDL string (SQLite reads ":32768"
    # as a bind-parameter marker).
    # rating is set explicitly: User.rating's default=500.0 is a Python/ORM-side
    # default, not a DB server_default, so a raw INSERT like this one leaves it
    # NULL otherwise — breaks anywhere the template does `rating|round`.
    connection.execute(
        text(
            "INSERT INTO user (id, username, password, theme, board, pieces, rating) "
            "VALUES (1, 'admin', :password, 'night', 'ondro', 'default', 500.0)"
        ),
        {"password": generate_password_hash(os.environ.get("ADMIN_PASSWORD", ""))},
    )


def _seed_bot_users(target, connection, **kwargs):
    # Two fixed bot accounts (not the admin user) so a game can have up to 2
    # bot seats without 2 seats sharing one username — webapp/api.py's
    # _seat_map() keys on username, so 2 seats with the same identity would
    # be ambiguous. Random, unrecorded password + active=False: nobody can
    # log in as these accounts even if the hash were somehow brute-forced.
    for username in ("Bot 1", "Bot 2"):
        connection.execute(
            text(
                "INSERT INTO user (username, password, active, is_bot, rating) "
                "VALUES (:username, :password, 0, 1, 500.0)"
            ),
            {
                "username": username,
                "password": generate_password_hash(secrets.token_hex(32)),
            },
        )


db.event.listen(User.__table__, "after_create", _seed_admin_user)
db.event.listen(User.__table__, "after_create", _seed_bot_users)
