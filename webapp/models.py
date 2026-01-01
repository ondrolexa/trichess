from datetime import datetime, timedelta

from webapp.main import db


class User(db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True)
    password = db.Column(db.String(500))
    email = db.Column(db.String(120))
    theme = db.Column(db.String(), default="default")
    board = db.Column(db.String(), default="ondro")
    pieces = db.Column(db.String(), default="default")
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    last_login = db.Column(db.DateTime)
    rating = db.Column(db.Float, default=500.0)
    scores = db.relationship("Score", backref="player")

    def score(self):
        return sum([score.score for score in self.scores])

    def recent_score(self):
        return sum(
            [
                score.score
                for score in self.scores
                if score.board.modified_at > (datetime.today() - timedelta(days=30))
            ]
        )

    def stats(self):
        win = 0
        part = 0
        for score in self.scores:
            if score.score == 2:
                win += 1
            else:
                part += 1
        return win, part

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    def __repr__(self):
        return "<User %r>" % (self.username)


class TriBoard(db.Model):
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
    owner = db.relationship(User, foreign_keys=[owner_id])
    player_0 = db.relationship(User, foreign_keys=[player_0_id])
    player_1 = db.relationship(User, foreign_keys=[player_1_id])
    player_2 = db.relationship(User, foreign_keys=[player_2_id])
    scores = db.relationship("Score", backref="board")


class Ratings(db.Model):
    __tablename__ = "v_ratings"
    uid = db.Column(db.Integer, primary_key=True)
    position = db.Column(db.Integer)
    username = db.Column(db.Text)
    rating = db.Column(db.Integer)
    score = db.Column(db.Float)
    game_count = db.Column(db.Integer)
    game_last = db.Column(db.DateTime, server_default=db.func.now())


class Score(db.Model):
    __tablename__ = "score"
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    board_id = db.Column(db.Integer, db.ForeignKey("triboard.id"))
    score = db.Column(db.Float)


db.event.listen(
    User.__table__,
    "after_create",
    db.DDL(
        """ INSERT INTO user (id, username, password) VALUES (1, 'admin', "scrypt:32768:8:1$5bsiJQZ4NcNXFiex$afc2dda97bb8cb9b609a9381ae044cabbcbc605d5e0e8618b259dde5fd2d568003fec3d3b19e86eb0cbd3f9c0fc5a62e7d94cbeb416cff89fea993ebcd41149e") """
    ),
)
