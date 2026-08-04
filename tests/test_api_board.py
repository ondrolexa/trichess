from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash

from engine import GameAPI, get_game
from webapp.main import db
from webapp.models import Score, TriBoard, User


def _create_user(username, active=True):
    user = User(username=username, password=generate_password_hash("pw"), active=active)
    db.session.add(user)
    db.session.commit()
    return user


def _make_board(owner, seats, slog="", status=1):
    tb = TriBoard(
        owner_id=owner.id,
        player_0_id=seats[0].id,
        player_0_accepted=True,
        player_1_id=seats[1].id,
        player_1_accepted=True,
        player_2_id=seats[2].id,
        player_2_accepted=True,
        status=status,
        slog=slog,
    )
    db.session.add(tb)
    db.session.commit()
    return tb


def _login(app, username):
    with app.test_request_context():
        return create_access_token(identity=username)


class TestGameBoardGetViewPidOverride:
    def _setup(self, app):
        alice = _create_user("alice")
        bob = _create_user("bob")
        carol = _create_user("carol")
        tb = _make_board(alice, {0: alice, 1: bob, 2: carol})
        return tb

    def test_no_override_matches_callers_own_seat(self, app, client):
        tb = self._setup(app)
        token = _login(app, "bob")

        resp = client.get(
            f"/api/v1/manager/board?id={tb.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["view_pid"] == 1
        expected = get_game(1, "").gid2hex
        assert data["gid2code"] == [
            expected[gid].pos.code for gid in range(len(expected))
        ]

    def test_view_pid_override_changes_gid2code_only(self, app, client):
        tb = self._setup(app)
        token = _login(app, "bob")

        resp = client.get(
            f"/api/v1/manager/board?id={tb.id}&view_pid=2",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        # view_pid field still reflects the caller's own seat, not the override
        assert data["view_pid"] == 1

        expected = get_game(2, "").gid2hex
        assert data["gid2code"] == [
            expected[gid].pos.code for gid in range(len(expected))
        ]

        default_resp = client.get(
            f"/api/v1/manager/board?id={tb.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert data["gid2code"] != default_resp.get_json()["gid2code"]

    def test_out_of_range_view_pid_rejected(self, app, client):
        tb = self._setup(app)
        token = _login(app, "bob")

        resp = client.get(
            f"/api/v1/manager/board?id={tb.id}&view_pid=7",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400


class TestGameBoardEndgamePersistence:
    """Covers GameBoard.post()'s endgame() dispatch for the two newly-added
    outcomes (repetition, stalemate) — draw/resignation/checkmate dispatch
    is unchanged and already exercised elsewhere (e.g. test_botplayer.py)."""

    def _setup(self, app):
        alice = _create_user("alice")
        bob = _create_user("bob")
        carol = _create_user("carol")
        tb = _make_board(alice, {0: alice, 1: bob, 2: carol})
        return tb, {0: alice, 1: bob, 2: carol}

    def test_repetition_ending_persists_tag_t_and_notifies(
        self, monkeypatch, app, client
    ):
        from webapp import api

        calls = []
        monkeypatch.setattr(api, "post_notification", lambda *a, **k: calls.append(a))

        tb, players = self._setup(app)

        # Each player shuffles a knight out and back, twice around — the
        # same real move sequence proven in test_gameapi.py's
        # TestEndgame.test_repetition_via_move_sequence to reach threefold
        # repetition after the 12th move.
        ga = GameAPI(view_pid=0)
        knights = {0: 166, 1: 17, 2: 26}
        current = dict(knights)
        for _ in range(2):
            for pid in range(3):
                frm = current[pid]
                to = next(m["tgid"] for m in ga.valid_moves(frm) if m["kind"] == "safe")
                ga.make_move(frm, to)
                current[pid] = to
            for pid in range(3):
                frm = current[pid]
                to = knights[pid]
                ga.make_move(frm, to)
                current[pid] = to
        # position_counts is only maintained while replaying a slog (see
        # engine/gameapi.py) — make_move() alone won't reflect it, so
        # verify via a fresh replay of the accumulated slog, same as
        # GameBoard.post() itself does via get_game().
        assert get_game(0, ga.slog).endgame() == "repetition"

        # Persist all but the final (12th) move, then POST that last move
        # as the on-move player — mirrors how the client only ever submits
        # one new move at a time.
        tb.slog = ga.slog[:-4]
        db.session.commit()
        prior = get_game(0, tb.slog)
        poster_username = players[prior.on_move].username

        with app.test_request_context():
            token = create_access_token(identity=poster_username)
        resp = client.post(
            "/api/v1/manager/board",
            json={"id": tb.id, "slog": ga.slog},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        db.session.refresh(tb)
        assert tb.status == 2
        scores = Score.query.filter_by(board_id=tb.id).all()
        assert len(scores) == 3
        assert all(s.tag == "T" for s in scores)
        assert all(s.score == 2.0 / 3 for s in scores)
        assert any("threefold repetition" in c[1] for c in calls)

    def test_stalemate_ending_persists_tag_s_and_notifies(
        self, monkeypatch, app, client
    ):
        from webapp import api

        calls = []
        monkeypatch.setattr(api, "post_notification", lambda *a, **k: calls.append(a))
        # A from-scratch, POST-reachable stalemate position would require a
        # full legal game reaching that exact state — see the board-surgery
        # approach used for the engine-level unit test instead
        # (test_gameapi.py::TestEndgame.test_stalemate_detected). Here we
        # only need to verify GameBoard.post()'s dispatch/persistence for
        # the "stalemate" outcome, so force the classification directly.
        monkeypatch.setattr(GameAPI, "endgame", lambda self: "stalemate")

        tb, players = self._setup(app)
        ga = get_game(0, "")
        poster_username = players[ga.on_move].username
        for gid in range(169):
            targets = ga.valid_moves(gid)
            if targets:
                ga.make_move(gid, targets[0]["tgid"])
                break

        with app.test_request_context():
            token = create_access_token(identity=poster_username)
        resp = client.post(
            "/api/v1/manager/board",
            json={"id": tb.id, "slog": ga.slog},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        db.session.refresh(tb)
        assert tb.status == 2
        scores = Score.query.filter_by(board_id=tb.id).all()
        assert len(scores) == 3
        assert all(s.tag == "S" for s in scores)
        assert all(s.score == 2.0 / 3 for s in scores)
        assert any("ended in a stalemate" in c[1] for c in calls)
