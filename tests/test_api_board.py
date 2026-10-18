import logging

import pytest
from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash

from engine import GameAPI, get_game
from webapp.api import MAX_SLOG_ENTRIES
from webapp.main import db
from webapp.models import Log, Score, TriBoard, User


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
    user = User.query.filter_by(username=username).one()
    with app.test_request_context():
        return create_access_token(identity=str(user.id))


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
        poster = players[prior.on_move]

        with app.test_request_context():
            token = create_access_token(identity=str(poster.id))
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
        poster = players[ga.on_move]
        for gid in range(169):
            targets = ga.valid_moves(gid)
            if targets:
                ga.make_move(gid, targets[0]["tgid"])
                break

        with app.test_request_context():
            token = create_access_token(identity=str(poster.id))
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


class TestGameBoardPostValidation:
    """POST /manager/board must accept only one legal step past the stored
    slog — replaying a slog applies moves without any legality check."""

    def _setup(self, app, slog=""):
        alice = _create_user("alice")
        bob = _create_user("bob")
        carol = _create_user("carol")
        tb = _make_board(alice, {0: alice, 1: bob, 2: carol}, slog=slog)
        return tb

    def _post(self, app, client, tb, username, slog):
        token = _login(app, username)
        return client.post(
            "/api/v1/manager/board",
            json={"id": tb.id, "slog": slog},
            headers={"Authorization": f"Bearer {token}"},
        )

    def _stored(self, tb):
        db.session.refresh(tb)
        return tb.slog

    def test_legal_move_is_accepted(self, app, client):
        tb = self._setup(app)
        ga = GameAPI(view_pid=0)
        ga.make_move(166, ga.valid_moves(166)[0]["tgid"])
        assert self._post(app, client, tb, "alice", ga.slog).status_code == 200
        assert self._stored(tb) == ga.slog

    def test_illegal_target_is_rejected(self, app, client):
        tb = self._setup(app)
        ga = GameAPI(view_pid=0)
        legal = {m["tgid"] for m in ga.valid_moves(166)}
        target = next(
            gid for gid, hex in ga.gid2hex.items() if gid not in legal and gid != 166
        )
        slog = ga.move2slog(ga.gid2hex[166].pos, ga.gid2hex[target].pos, "")
        assert self._post(app, client, tb, "alice", slog).status_code != 200
        assert self._stored(tb) == ""

    def test_moving_an_opponents_piece_is_rejected(self, app, client):
        tb = self._setup(app)
        ga = GameAPI(view_pid=0)
        # gid 17 is player 1's knight; move it as if player 1 were on move.
        other = GameAPI(view_pid=0)
        other.move_number = 1
        tgid = other.valid_moves(17)[0]["tgid"]
        slog = ga.move2slog(ga.gid2hex[17].pos, ga.gid2hex[tgid].pos, "")
        assert self._post(app, client, tb, "alice", slog).status_code != 200
        assert self._stored(tb) == ""

    def test_fabricated_history_with_vote_is_rejected(self, app, client):
        tb = self._setup(app)
        ga = GameAPI(view_pid=0)
        ga.make_move(166, ga.valid_moves(166)[0]["tgid"])
        ga.make_move(17, ga.valid_moves(17)[0]["tgid"])
        ga.make_move(26, ga.valid_moves(26)[0]["tgid"])
        # Three moves nobody played, followed by alice's resign vote.
        forged = ga.resignation_vote(True)
        assert self._post(app, client, tb, "alice", forged).status_code != 200
        assert self._stored(tb) == ""

    def test_votes_round_trip(self, app, client):
        tb = self._setup(app)
        for username in ("alice", "bob", "carol"):
            slog = get_game(0, self._stored(tb)).draw_vote(False)
            assert self._post(app, client, tb, username, slog).status_code == 200
        ga = get_game(0, self._stored(tb))
        assert ga.voting.finished() and not ga.draw()

    def test_out_of_turn_post_is_rejected(self, app, client):
        tb = self._setup(app)
        ga = GameAPI(view_pid=0)
        ga.make_move(166, ga.valid_moves(166)[0]["tgid"])
        assert self._post(app, client, tb, "bob", ga.slog).status_code != 200


class TestSlogLimits:
    """Client slogs are replayed in full, so their size is capped."""

    @pytest.fixture
    def post(self, app, client):
        _create_user("alice")
        headers = {"Authorization": f"Bearer {_login(app, 'alice')}"}

        def post(path, slog):
            body = {"slog": slog, "view_pid": 0, "gid": 166}
            return client.post(path, json=body, headers=headers)

        return post

    def test_overlong_slog_rejected_by_engine_endpoints(self, post):
        slog = "BNDL" * (MAX_SLOG_ENTRIES + 1)
        for path in ("/api/v1/game/info", "/api/v1/move/valid"):
            assert post(path, slog).status_code == 400, path

    def test_partial_entry_rejected(self, post):
        assert post("/api/v1/game/info", "BNDLH").status_code == 400

    def test_normal_slog_accepted(self, post):
        resp = post("/api/v1/game/info", "BNDLHBIB")
        assert resp.status_code == 200
        assert resp.get_json()["move_number"] == 2

    def test_oversized_body_rejected(self, post):
        assert post("/api/v1/game/info", "B" * (64 * 1024)).status_code == 413


class TestGameBoardPostIsAtomic:
    """Log rows are written on their own connection, so a failing POST rolls
    back the whole move while its log lines survive. Needs real transactions:
    SQLite's in-memory test database shares one connection between both."""

    @pytest.fixture(autouse=True)
    def _postgres_only(self, app):
        if db.engine.dialect.name == "sqlite":
            pytest.skip("needs separate connections (TEST_DATABASE_URL=postgresql...)")

    def _setup(self):
        alice, bob, carol = (_create_user(n) for n in ("alice", "bob", "carol"))
        return _make_board(alice, {0: alice, 1: bob, 2: carol})

    def _move(self, app, client, tb):
        ga = GameAPI(view_pid=0)
        ga.make_move(166, ga.valid_moves(166)[0]["tgid"])
        return client.post(
            "/api/v1/manager/board",
            json={"id": tb.id, "slog": ga.slog},
            headers={"Authorization": f"Bearer {_login(app, 'alice')}"},
        )

    def test_move_logs_while_board_is_locked(self, app, client, caplog):
        # Under pytest the root logger stays at WARNING, which would drop the
        # GAME (25) records this test is about before they reach DBHandler.
        caplog.set_level(logging.INFO)
        tb = self._setup()

        assert self._move(app, client, tb).status_code == 200

        # Written while the request held the board's row lock: the lock must
        # not block the log row's foreign-key check (no lock timeout).
        messages = {
            m for (m,) in db.session.query(Log.message).filter_by(board_id=tb.id)
        }
        assert "Move.str 000" in messages and "Move end 000" in messages

    def test_failure_mid_post_rolls_back_the_move(self, app, client, monkeypatch):
        from webapp import api

        def boom(*args, **kwargs):
            raise RuntimeError("scoring failed")

        monkeypatch.setattr(api, "finalize_if_finished", boom)
        tb = self._setup()

        assert self._move(app, client, tb).status_code == 417

        db.session.expire_all()
        assert db.session.get(TriBoard, tb.id).slog == ""
        errors = db.session.query(Log).filter_by(level="ERROR").all()
        assert any("scoring failed" in e.message for e in errors)

    def test_game_end_logs_while_players_are_locked(self, app, client, caplog):
        # Finishing a rated game locks the three users' rows (ratings) while
        # "Game finished" is logged with a user id on DBHandler's connection.
        caplog.set_level(logging.INFO)
        tb = self._setup()
        players = {0: tb.player_0, 1: tb.player_1, 2: tb.player_2}
        for _ in range(3):
            db.session.refresh(tb)
            ga = get_game(0, tb.slog)
            slog = ga.resignation_vote(ga.on_move != 0)
            with app.test_request_context():
                token = create_access_token(identity=str(players[ga.on_move].id))
            resp = client.post(
                "/api/v1/manager/board",
                json={"id": tb.id, "slog": slog},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
        db.session.expire_all()
        assert db.session.get(TriBoard, tb.id).status == 2
        finished = Log.query.filter(Log.message.like("Game finished%")).count()
        assert finished == 1
