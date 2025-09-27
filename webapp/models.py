from datetime import datetime, timedelta

from webapp.main import db


class User(db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True)
    password = db.Column(db.String(500))
    email = db.Column(db.String(120))
    theme = db.Column(db.String())
    board = db.Column(db.String())
    scores = db.relationship("Score", backref="player")

    def score(self):
        return sum([score.score for score in self.scores])

    def recent_score(self):
        return sum(
            [
                score.score
                for score in self.scores
                if score.created_at > (datetime.today() - timedelta(days=30))
            ]
        )

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
    modified_at = db.Column(
        db.DateTime, server_default=db.func.now(), onupdate=db.func.now()
    )
    owner = db.relationship(User, foreign_keys=[owner_id])
    player_0 = db.relationship(User, foreign_keys=[player_0_id])
    player_1 = db.relationship(User, foreign_keys=[player_1_id])
    player_2 = db.relationship(User, foreign_keys=[player_2_id])


class Score(db.Model):
    __tablename__ = "score"
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    score = db.Column(db.Float)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


db.event.listen(
    User.__table__,
    "after_create",
    db.DDL(
        """ INSERT INTO user (id, username, password) VALUES (1, 'admin', "scrypt:32768:8:1$5bsiJQZ4NcNXFiex$afc2dda97bb8cb9b609a9381ae044cabbcbc605d5e0e8618b259dde5fd2d568003fec3d3b19e86eb0cbd3f9c0fc5a62e7d94cbeb416cff89fea993ebcd41149e") """
    ),
)
