from datetime import datetime, timedelta

from webapp.main import db


class User(db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True)
    password = db.Column(db.String(500))
    email = db.Column(db.String(120))
    theme = db.Column(db.String(16), default="default")
    board = db.Column(db.String(16), default="ondro")
    pieces = db.Column(db.String(16), default="default")
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


class Score(db.Model):
    __tablename__ = "score"
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    board_id = db.Column(db.Integer, db.ForeignKey("triboard.id"))
    score = db.Column(db.Float)
    tag = db.Column(db.String(1), default="N")
    onmove = db.Column(db.Boolean, default=False)


db.event.listen(
    User.__table__,
    "after_create",
    db.DDL(
        """ INSERT INTO user (id, username, password, theme, board, pieces) VALUES (1, 'admin', "scrypt:32768:8:1$5bsiJQZ4NcNXFiex$afc2dda97bb8cb9b609a9381ae044cabbcbc605d5e0e8618b259dde5fd2d568003fec3d3b19e86eb0cbd3f9c0fc5a62e7d94cbeb416cff89fea993ebcd41149e", "night", "ondro", "default") """
    ),
)
