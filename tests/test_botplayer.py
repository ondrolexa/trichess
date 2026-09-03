from flask_jwt_extended import create_access_token
from sqlalchemy import text
from werkzeug.security import generate_password_hash

from engine import GameAPI, get_game
from webapp import api, botplayer
from webapp.main import db
from webapp.models import Log, Score, TriBoard, User


def _create_user(username, active=True):
    user = User(username=username, password=generate_password_hash("pw"), active=active)
    db.session.add(user)
    db.session.commit()
    return user


def _bots():
    return (
        User.query.filter_by(username="Bot 1").first(),
        User.query.filter_by(username="Bot 2").first(),
    )


def _repetition_slog():
    """Slog reaching threefold repetition (on_move == 0 afterward): each
    player shuffles a knight out and back, twice around — mirrors
    tests/test_gameapi.py's TestEndgame.test_repetition_via_move_sequence.
    """
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
    return ga.slog


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


class TestBotAccountsSeeded:
    def test_two_bot_accounts_exist(self, app):
        bots = User.query.filter_by(is_bot=True).all()
        assert len(bots) == 2
        assert {b.username for b in bots} == {"Bot 1", "Bot 2"}
        assert all(not b.active for b in bots)


class TestMaybeTriggerBot:
    def test_enqueues_when_bot_on_move(self, app):
        bot1, bot2 = _bots()
        alice = _create_user("alice")
        tb = _make_board(alice, {0: bot1, 1: alice, 2: bot2})
        botplayer.maybe_trigger_bot(tb.id)
        assert len(botplayer.bot_queue) == 1

    def test_does_not_enqueue_when_human_on_move(self, app):
        bot1, bot2 = _bots()
        alice = _create_user("alice")
        tb = _make_board(alice, {0: alice, 1: bot1, 2: bot2})
        botplayer.maybe_trigger_bot(tb.id)
        assert len(botplayer.bot_queue) == 0

    def test_does_not_enqueue_for_waiting_game(self, app):
        bot1, bot2 = _bots()
        alice = _create_user("alice")
        tb = _make_board(alice, {0: bot1, 1: alice, 2: bot2}, status=0)
        botplayer.maybe_trigger_bot(tb.id)
        assert len(botplayer.bot_queue) == 0

    def test_does_not_enqueue_for_missing_board(self, app):
        botplayer.maybe_trigger_bot(999999)
        assert len(botplayer.bot_queue) == 0

    def test_finalizes_instead_of_enqueuing_when_already_finished(self, app):
        bot1, bot2 = _bots()
        alice = _create_user("alice")
        # on_move is 0 after this slog and the position is already a
        # threefold repetition — a bot sits at seat 0.
        tb = _make_board(alice, {0: bot1, 1: bot2, 2: alice}, slog=_repetition_slog())

        botplayer.maybe_trigger_bot(tb.id)

        assert len(botplayer.bot_queue) == 0
        db.session.refresh(tb)
        assert tb.status == 2


class TestSweepFinalize:
    def test_finalizes_bot_seat_game_with_no_score_rows(self, app):
        bot1, bot2 = _bots()
        alice = _create_user("alice")
        tb = _make_board(alice, {0: alice, 1: bot1, 2: bot2}, slog=_repetition_slog())

        assert api.sweep_finalize(tb.id) is True

        db.session.refresh(tb)
        assert tb.status == 2
        assert Score.query.filter_by(board_id=tb.id).count() == 0

    def test_finalizes_all_human_game_with_score_rows(self, app):
        alice = _create_user("alice")
        bob = _create_user("bob")
        carol = _create_user("carol")
        tb = _make_board(alice, {0: alice, 1: bob, 2: carol}, slog=_repetition_slog())

        assert api.sweep_finalize(tb.id) is True

        db.session.refresh(tb)
        assert tb.status == 2
        assert Score.query.filter_by(board_id=tb.id).count() == 3

    def test_returns_false_for_ongoing_game(self, app):
        bot1, bot2 = _bots()
        alice = _create_user("alice")
        tb = _make_board(alice, {0: alice, 1: bot1, 2: bot2}, slog="")

        assert api.sweep_finalize(tb.id) is False

        db.session.refresh(tb)
        assert tb.status == 1

    def test_returns_false_for_already_finished_board(self, app):
        bot1, bot2 = _bots()
        alice = _create_user("alice")
        tb = _make_board(alice, {0: alice, 1: bot1, 2: bot2}, status=2)

        assert api.sweep_finalize(tb.id) is False

    def test_returns_false_for_missing_board(self, app):
        assert api.sweep_finalize(999999) is False


class TestRunBotMove:
    def test_persists_a_move_for_bot_on_move(self, app):
        bot1, bot2 = _bots()
        alice = _create_user("alice")
        tb = _make_board(alice, {0: bot1, 1: alice, 2: bot2}, slog="")
        botplayer.run_bot_move(tb.id)
        db.session.refresh(tb)
        assert tb.slog != ""
        ga = get_game(0, tb.slog)
        assert ga.on_move == 1

    def test_responds_to_a_pending_vote(self, app):
        bot1, _ = _bots()
        alice = _create_user("alice")
        bob = _create_user("bob")

        ga = GameAPI(view_pid=0)
        for hex in ga.board:
            if hex.has_piece and hex.piece.player.pid == 0:
                gid = ga.pos2gid[hex.pos]
                targets = ga.valid_moves(gid)
                if targets:
                    ga.make_move(gid, targets[0]["tgid"])
                    break
        # seat 1 (bob, now on move) proposes a draw -> seat 2 must respond next.
        vote_slog = ga.draw_vote(True)
        ga2 = get_game(0, vote_slog)
        assert ga2.voting.needed()
        assert ga2.on_move == 2

        tb = _make_board(alice, {0: alice, 1: bob, 2: bot1}, slog=vote_slog)
        botplayer.run_bot_move(tb.id)
        db.session.refresh(tb)
        assert tb.slog != vote_slog

    def test_noop_for_missing_or_inactive_board(self, app):
        botplayer.run_bot_move(999999)  # must not raise

        bot1, bot2 = _bots()
        alice = _create_user("alice")
        tb = _make_board(alice, {0: bot1, 1: alice, 2: bot2}, status=0)
        botplayer.run_bot_move(tb.id)
        db.session.refresh(tb)
        assert tb.status == 0

    def test_noop_when_on_move_is_not_actually_a_bot(self, app):
        bot1, bot2 = _bots()
        alice = _create_user("alice")
        tb = _make_board(alice, {0: alice, 1: bot1, 2: bot2}, slog="")
        botplayer.run_bot_move(tb.id)
        db.session.refresh(tb)
        assert tb.slog == ""


class TestFillBotSeat:
    def _login(self, client, user):
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True

    def test_owner_can_fill_two_distinct_bot_seats(self, client, app):
        alice = _create_user("alice")
        self._login(client, alice)
        client.post("/join", data={"seat": "Seat 1"})
        tb = TriBoard.query.first()

        client.post("/join", data={"board": tb.id, "fill_bot": "1"})
        client.post("/join", data={"board": tb.id, "fill_bot": "2"})

        db.session.refresh(tb)
        assert tb.status == 1
        assert tb.player_1_id != tb.player_2_id
        assert db.session.get(User, tb.player_1_id).is_bot
        assert db.session.get(User, tb.player_2_id).is_bot

    def test_non_owner_cannot_fill_bot_seat(self, client, app):
        # A single login per test: g/current_user are cached on Flask's `g`,
        # which the `app` fixture keeps alive for the whole test (one long-
        # lived app context) — logging in as a 2nd user mid-test would just
        # read back the 1st user's cached identity, not really switch it.
        alice = _create_user("alice")
        bob = _create_user("bob")
        tb = TriBoard(
            owner_id=alice.id, player_0_id=alice.id, player_0_accepted=True, status=0
        )
        db.session.add(tb)
        db.session.commit()

        self._login(client, bob)
        client.post("/join", data={"board": tb.id, "fill_bot": "1"})

        db.session.refresh(tb)
        assert tb.player_1_id is None

    def test_bot_in_first_seat_triggers_immediately_on_game_start(self, client, app):
        alice = _create_user("alice")
        self._login(client, alice)
        client.post("/join", data={"seat": "Seat 2"})  # alice takes seat 1
        tb = TriBoard.query.first()

        client.post("/join", data={"board": tb.id, "fill_bot": "0"})
        assert len(botplayer.bot_queue) == 0  # game not full yet

        client.post("/join", data={"board": tb.id, "fill_bot": "2"})
        assert len(botplayer.bot_queue) == 1  # seat 0 (a bot) is on move first


class TestRatingExcludesBots:
    def test_bot_board_excluded_from_rating_history(self, app):
        from webapp.api import get_rating_history

        bot1, _ = _bots()
        alice = _create_user("alice")
        bob = _create_user("bob")
        _make_board(alice, {0: alice, 1: bob, 2: bot1}, status=2)

        history = get_rating_history()
        assert alice.id not in history
        assert bob.id not in history
        assert bot1.id not in history

    def test_bot_never_appears_on_rating_page(self, client, app):
        # A finished board still sets status=2 for a bot game (only Score
        # creation is skipped) — TriBoard.for_player() alone would give the
        # bot played_games > 0, so the view's is_bot filter is load-bearing,
        # not redundant with the played_games>0 check.
        bot1, _ = _bots()
        alice = _create_user("alice")
        bob = _create_user("bob")
        _make_board(alice, {0: alice, 1: bob, 2: bot1}, status=2)

        with client.session_transaction() as sess:
            sess["_user_id"] = str(alice.id)
            sess["_fresh"] = True
        resp = client.get("/rating")
        assert b"Bot 1" not in resp.data


class TestBotGamesAreCasual:
    def test_finished_bot_game_creates_no_score_rows(self, app, client):
        bot1, _ = _bots()
        alice = _create_user("alice")
        bob = _create_user("bob")

        ga = GameAPI(view_pid=0)
        s1 = ga.draw_vote(True)  # seat 0 (alice) accepts
        s2 = get_game(0, s1).draw_vote(True)  # seat 1 (bob) accepts
        ga2 = get_game(0, s2)
        assert ga2.on_move == 2  # seat 2 (the bot) must cast the deciding vote

        tb = _make_board(alice, {0: alice, 1: bob, 2: bot1}, slog=s2)
        s3 = get_game(0, s2).draw_vote(True)  # simulate the bot accepting too
        with app.test_request_context():
            token = create_access_token(identity=bot1.username)

        resp = client.post(
            "/api/v1/manager/board",
            json={"id": tb.id, "slog": s3},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

        db.session.refresh(tb)
        assert tb.status == 2
        assert Score.query.filter_by(board_id=tb.id).count() == 0


def _move_for_pid(ga, pid):
    for hex in ga.board:
        if hex.has_piece and hex.piece.player.pid == pid:
            gid = ga.pos2gid[hex.pos]
            targets = ga.valid_moves(gid)
            if targets:
                ga.make_move(gid, targets[0]["tgid"])
                return
    raise AssertionError(f"no legal move found for pid {pid}")


class TestSinglePlayerNotifications:
    def test_no_turn_notification_by_default_for_1_human_2_bots(
        self, monkeypatch, app, client
    ):
        from webapp import api

        calls = []
        monkeypatch.setattr(api, "post_notification", lambda *a, **k: calls.append(a))

        bot1, bot2 = _bots()
        alice = _create_user("alice")
        tb = _make_board(alice, {0: alice, 1: bot1, 2: bot2}, slog="")

        # Advance 2 plies locally (alice, then bot1) so bot2 ends up on
        # move — mirrors how a real game reaches this rotation.
        ga = get_game(0, "")
        _move_for_pid(ga, 0)
        _move_for_pid(ga, 1)
        tb.slog = ga.slog
        db.session.commit()
        assert ga.on_move == 2

        # bot2's move rotates on_move back to alice (the human) — this is
        # exactly the transition that would normally trigger "it's your
        # turn" for alice.
        _move_for_pid(ga, 2)
        assert ga.on_move == 0

        with app.test_request_context():
            token = create_access_token(identity=bot2.username)
        resp = client.post(
            "/api/v1/manager/board",
            json={"id": tb.id, "slog": ga.slog},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert calls == []

    def test_turn_notification_when_opted_in(self, monkeypatch, app, client):
        from webapp import api

        monkeypatch.setattr(api, "SINGLE_PLAYER_NOTIFICATIONS", True)
        calls = []
        monkeypatch.setattr(api, "post_notification", lambda *a, **k: calls.append(a))

        bot1, bot2 = _bots()
        alice = _create_user("alice")
        tb = _make_board(alice, {0: alice, 1: bot1, 2: bot2}, slog="")

        ga = get_game(0, "")
        _move_for_pid(ga, 0)
        _move_for_pid(ga, 1)
        tb.slog = ga.slog
        db.session.commit()
        _move_for_pid(ga, 2)

        with app.test_request_context():
            token = create_access_token(identity=bot2.username)
        resp = client.post(
            "/api/v1/manager/board",
            json={"id": tb.id, "slog": ga.slog},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert calls and calls[0][0] == "alice"

    def test_gate_does_not_apply_to_2_humans_1_bot(self, monkeypatch, app, client):
        # Only 1 bot seat here, not 2 — this is a real multiplayer game and
        # must keep notifying both humans regardless of the gate's default.
        from webapp import api

        calls = []
        monkeypatch.setattr(api, "post_notification", lambda *a, **k: calls.append(a))

        bot1, _ = _bots()
        alice = _create_user("alice")
        bob = _create_user("bob")
        tb = _make_board(alice, {0: alice, 1: bob, 2: bot1}, slog="")

        ga = get_game(0, "")
        _move_for_pid(ga, 0)

        with app.test_request_context():
            token = create_access_token(identity=alice.username)
        resp = client.post(
            "/api/v1/manager/board",
            json={"id": tb.id, "slog": ga.slog},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert calls and calls[0][0] == "bob"

    def test_resend_notification_ignores_the_gate(self, monkeypatch, app):
        from webapp import main

        calls = []
        monkeypatch.setattr(
            main,
            "post_notification",
            lambda username, text, title, gameid: calls.append(username),
        )

        bot1, bot2 = _bots()
        alice = _create_user("alice")
        tb = _make_board(alice, {0: alice, 1: bot1, 2: bot2})

        db.session.execute(
            text(
                "UPDATE triboard SET modified_at = datetime('now', '-2 day') "
                "WHERE id = :id"
            ),
            {"id": tb.id},
        )
        db.session.commit()

        app.debug = False
        try:
            main.resend_notification()
        finally:
            app.debug = True

        assert calls == ["alice"]


class TestResendNotificationNeverTargetsBots:
    def test_skips_a_bot_on_move(self, monkeypatch, app):
        from webapp import main

        calls = []
        monkeypatch.setattr(
            main,
            "post_notification",
            lambda username, text, title, gameid: calls.append(username),
        )

        bot1, bot2 = _bots()
        alice = _create_user("alice")
        # bot1 (seat 0) is on move on a stale board — simulates a queued
        # bot-move job that got lost (e.g. a Redis restart).
        tb = _make_board(alice, {0: bot1, 1: alice, 2: bot2})

        db.session.execute(
            text(
                "UPDATE triboard SET modified_at = datetime('now', '-2 day') "
                "WHERE id = :id"
            ),
            {"id": tb.id},
        )
        db.session.commit()

        app.debug = False
        try:
            main.resend_notification()
        finally:
            app.debug = True

        assert calls == []


def _backdate_board(tb, minutes):
    db.session.execute(
        text(
            "UPDATE triboard SET modified_at = datetime('now', :offset) "
            "WHERE id = :id"
        ),
        {"offset": f"-{minutes} minute", "id": tb.id},
    )
    db.session.commit()


class TestRemoveBotGames:
    def test_default_is_15_minutes_enabled(self):
        from webapp import main

        assert main.BOT_GAMES_REMOVAL == 15

    def test_zero_minutes_disables_removal(self, app):
        from webapp import main

        bot1, bot2 = _bots()
        alice = _create_user("alice")
        tb = _make_board(alice, {0: alice, 1: bot1, 2: bot2}, status=2)
        _backdate_board(tb, 200)

        removed = main.remove_bot_games(0)

        assert removed == 0
        assert db.session.get(TriBoard, tb.id) is not None

    def test_removes_finished_bot_game_past_cutoff(self, app):
        from webapp import main

        bot1, bot2 = _bots()
        alice = _create_user("alice")
        tb = _make_board(alice, {0: alice, 1: bot1, 2: bot2}, status=2)
        _backdate_board(tb, 200)

        removed = main.remove_bot_games(120)

        assert removed == 1
        assert db.session.get(TriBoard, tb.id) is None

    def test_leaves_recent_bot_game(self, app):
        from webapp import main

        bot1, bot2 = _bots()
        alice = _create_user("alice")
        tb = _make_board(alice, {0: alice, 1: bot1, 2: bot2}, status=2)
        _backdate_board(tb, 10)

        removed = main.remove_bot_games(120)

        assert removed == 0
        assert db.session.get(TriBoard, tb.id) is not None

    def test_leaves_all_human_game_regardless_of_age(self, app):
        from webapp import main

        alice = _create_user("alice")
        bob = _create_user("bob")
        carol = _create_user("carol")
        tb = _make_board(alice, {0: alice, 1: bob, 2: carol}, status=2)
        _backdate_board(tb, 200)

        removed = main.remove_bot_games(120)

        assert removed == 0
        assert db.session.get(TriBoard, tb.id) is not None

    def test_leaves_active_bot_game_regardless_of_age(self, app):
        from webapp import main

        bot1, bot2 = _bots()
        alice = _create_user("alice")
        tb = _make_board(alice, {0: alice, 1: bot1, 2: bot2}, status=1)
        _backdate_board(tb, 200)

        removed = main.remove_bot_games(120)

        assert removed == 0
        assert db.session.get(TriBoard, tb.id) is not None

    def test_deletes_logs_attached_to_removed_board(self, app):
        from webapp import main

        bot1, bot2 = _bots()
        alice = _create_user("alice")
        tb = _make_board(alice, {0: alice, 1: bot1, 2: bot2}, status=2)
        _backdate_board(tb, 200)
        log = Log(level="GAME", message="Game finished", board_id=tb.id)
        db.session.add(log)
        db.session.commit()
        log_id = log.id

        removed = main.remove_bot_games(120)

        assert removed == 1
        assert db.session.get(Log, log_id) is None

    def test_clears_stray_score_row_without_raising(self, app):
        from webapp import main

        bot1, bot2 = _bots()
        alice = _create_user("alice")
        tb = _make_board(alice, {0: alice, 1: bot1, 2: bot2}, status=2)
        _backdate_board(tb, 200)
        # Bot games shouldn't normally have Score rows (see
        # GameBoard.post()'s board_has_bot guard) — inserted directly here
        # to prove the defensive clear actually prevents an FK violation.
        score = Score(player_id=alice.id, board_id=tb.id, score=2.0, tag="N")
        db.session.add(score)
        db.session.commit()

        removed = main.remove_bot_games(120)

        assert removed == 1
        assert db.session.get(TriBoard, tb.id) is None
