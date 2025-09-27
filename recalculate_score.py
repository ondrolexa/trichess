"""
Deactivate onupdate for modified_at of Triboard in models.py
"""

from engine import GameAPI
from webapp import app, db
from webapp.models import Score, TriBoard

with app.app_context():
    Score.query.delete()
    # fix started time on active
    for t in (
        TriBoard.query.filter_by(status=1).order_by(TriBoard.modified_at.asc()).all()
    ):
        if t.started_at > t.modified_at:
            t.started_at = t.created_at
    db.session.commit()
    r = TriBoard.query.filter_by(status=2).order_by(TriBoard.modified_at.asc()).all()
    for t in r:
        print(f"Parsing game {t.id} finished at {t.modified_at}")
        ga = GameAPI(0)
        ga.replay_from_slog(t.slog)
        players = {
            0: t.player_0,
            1: t.player_1,
            2: t.player_2,
        }
        if t.started_at > t.modified_at:
            t.started_at = t.created_at
        if not ga.move_possible():
            in_chess, gid, who = ga.in_chess
            if in_chess:
                tot = [len(p) for p in who.values()]
                for uid, v in enumerate(tot):
                    score = v * 2 / sum(tot)
                    if score > 0:
                        new_score = Score(
                            player_id=players[uid].id,
                            board_id=t.id,
                            score=score,
                        )
                        db.session.add(new_score)
            else:
                print(f"  ERROR: Game {t.id} ended with no chess")
        else:
            print(f"  ERROR: Moves still possible in game {t.id}")

    db.session.commit()

print("Done")
