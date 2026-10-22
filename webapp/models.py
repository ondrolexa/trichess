import enum
import os
import secrets
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

from webapp.main import db
from webapp.token import password_fingerprint

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, "..", ".env"))


def utcnow_naive():
    """Now as naive UTC: how every DateTime column stores time (their
    server_default now() runs on a server pinned to timezone=UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class GameStatus(enum.IntEnum):
    """TriBoard.status."""

    WAITING = 0  # in the lobby, seats still open
    ACTIVE = 1
    FINISHED = 2


def score_outcome(score, onmove, tag):
    """Classify one Score row as "win", "coop", "pass" or "loss"."""
    if score == 2:
        return "win"
    if score > 0:
        return "coop"
    if onmove or tag == "R":
        return "loss"
    return "pass"


class User(db.Model):  # ty: ignore
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    # Unique: JWTs carry the id, but seats, the lobby and logins name users.
    username = db.Column(db.String(64), unique=True)
    password = db.Column(db.String(500))
    email = db.Column(db.String(120), unique=True)
    email_verified = db.Column(db.Boolean, default=False)
    theme = db.Column(db.String(16), default="default")
    board = db.Column(db.String(16), default="ondro")
    pieces = db.Column(db.String(16), default="default")
    active = db.Column(db.Boolean, default=True)
    is_bot = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.false()
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
            stats[score_outcome(score.score, score.onmove, score.tag)] += 1
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
        """The session's user id, bound to the password: changing it ends
        every other session (views.load_user rejects the old id)."""
        return f"{self.id}:{password_fingerprint(self)}"

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

    status = db.Column(db.Integer, nullable=False, default=GameStatus.WAITING)
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

    SEATS = (0, 1, 2)

    @property
    def players(self):
        """{seat: User or None}."""
        return {seat: getattr(self, f"player_{seat}") for seat in self.SEATS}

    @property
    def player_ids(self):
        """[user id or None] per seat."""
        return [getattr(self, f"player_{seat}_id") for seat in self.SEATS]

    def seat_of(self, user_id):
        """The seat *user_id* sits in, or None."""
        return next((s for s, i in enumerate(self.player_ids) if i == user_id), None)

    def assign_seat(self, seat, user):
        setattr(self, f"player_{seat}_id", user.id)
        setattr(self, f"player_{seat}_accepted", True)

    def clear_seat(self, seat):
        setattr(self, f"player_{seat}_id", None)
        setattr(self, f"player_{seat}_accepted", False)

    @property
    def is_full(self):
        return None not in self.player_ids

    @property
    def bot_count(self):
        return sum(1 for p in self.players.values() if p is not None and p.is_bot)

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


class RatingHistory(db.Model):  # ty: ignore
    """A player's rating right after each rated game, for the profile chart.

    Written incrementally when a game finishes (ratings.record_game_rating);
    `flask rebuild-ratings` recomputes it, and User.rating, from all games.
    """

    __tablename__ = "rating_history"
    __table_args__ = (db.Index("ix_rating_history_user", "user_id", "created_at"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    board_id = db.Column(db.Integer, db.ForeignKey("triboard.id"), nullable=True)
    rating = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)


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


class Setting(db.Model):  # ty: ignore
    """Small key/value store for app-wide switches (e.g. maintenance mode).

    In the database rather than in memory so every gunicorn worker, the RQ
    worker and cron jobs see the same value.
    """

    __tablename__ = "setting"

    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.Text, nullable=False)


def delete_board(tb):
    """Delete a game with every row that references it (Score, Log,
    RatingHistory). Returns whether it was rated, i.e. had Score rows, in
    which case the caller must rebuild ratings. The caller commits."""
    rated = Score.query.filter_by(board_id=tb.id).delete() > 0
    Log.query.filter_by(board_id=tb.id).delete()
    RatingHistory.query.filter_by(board_id=tb.id).delete()
    db.session.delete(tb)
    return rated


def _seed_admin_user(target, connection, **kwargs):
    # No explicit id: as the first row of a fresh table it gets id 1 (the
    # hardcoded admin check) on every backend, and PostgreSQL's id sequence
    # stays in step. Core insert, not raw SQL: "user" is a reserved word in
    # PostgreSQL and needs quoting, which the dialect handles.
    # rating is set explicitly: User.rating's default=500.0 is a Python/ORM-side
    # default, not a DB server_default, so a Core insert like this one leaves it
    # NULL otherwise — breaks anywhere the template does `rating|round`.
    connection.execute(
        target.insert().values(
            username="admin",
            password=generate_password_hash(os.environ.get("ADMIN_PASSWORD", "")),
            theme="night",
            board="ondro",
            pieces="default",
            rating=500.0,
        )
    )


def _seed_bot_users(target, connection, **kwargs):
    # Two fixed bot accounts (not the admin user) so a game can have up to 2
    # bot seats without 2 seats sharing one account — TriBoard.seat_of()
    # looks a user up by id, so 2 seats with the same identity would be
    # ambiguous. Random, unrecorded password + active=False: nobody can
    # log in as these accounts even if the hash were somehow brute-forced.
    for username in ("Bot 1", "Bot 2"):
        connection.execute(
            target.insert().values(
                username=username,
                password=generate_password_hash(secrets.token_hex(32)),
                active=False,
                is_bot=True,
                rating=500.0,
            )
        )


db.event.listen(User.__table__, "after_create", _seed_admin_user)
db.event.listen(User.__table__, "after_create", _seed_bot_users)
