import logging
import re
import shutil
from pathlib import Path

import pytest
from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash

import webapp
from webapp.forms import ProfileForm
from webapp.main import db, dump_db
from webapp.models import Log, Score, TriBoard, User


def _create_user(username="alice", password="password123", active=True, id=None):
    user = User(
        id=id,
        username=username,
        password=generate_password_hash(password),
        email=f"{username}@example.com",
        active=active,
    )
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username="alice", password="password123"):
    # /login is itself a FlaskForm — when WTF_CSRF_ENABLED is on for a test, it
    # needs a real token too, not just the routes under test.
    login_page = client.get("/login")
    data = {"username": username, "password": password}
    match = re.search(
        r'<input[^>]*name="csrf_token"[^>]*value="([^"]+)"',
        login_page.get_data(as_text=True),
    )
    if match:
        data["csrf_token"] = match.group(1)
    return client.post("/login", data=data)


def _login_as_admin(client, password="adminpass123"):
    # db.create_all() already seeds a user with id=1/username="admin" via the
    # after_create DDL in webapp/models.py — reuse it rather than colliding with it.
    admin = db.session.get(User, 1)
    admin.password = generate_password_hash(password)
    admin.active = True
    db.session.commit()
    _login(client, username=admin.username, password=password)
    return admin


def _extract_csrf_token(html):
    match = re.search(r'<input[^>]*name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match, "no csrf_token hidden field found in response HTML"
    return match.group(1)


class Test_CSRF_Protection:
    """Covers the raw request.form.get() actions (available_games/admin_games/
    admin_users) that had no CSRF check at all before CSRFProtect(app) was wired up."""

    def test_join_post_without_csrf_token_is_rejected(self, app, client):
        app.config["WTF_CSRF_ENABLED"] = True
        _create_user()
        _login(client)
        resp = client.post("/join", data={"seat": "Seat 1"})
        assert resp.status_code == 400

    def test_navbar_login_button_post_with_csrf_token_is_accepted(self, app, client):
        # Regression test: base.html's navbar login/logout/register form posts
        # to index() on every page and was initially missed when CSRF hidden
        # fields were added, breaking the "Login" button in the browser.
        app.config["WTF_CSRF_ENABLED"] = True
        page = client.get("/")
        token = _extract_csrf_token(page.get_data(as_text=True))
        resp = client.post("/", data={"action": "login", "csrf_token": token})
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/login")

    def test_navbar_login_button_post_without_csrf_token_is_rejected(self, app, client):
        app.config["WTF_CSRF_ENABLED"] = True
        resp = client.post("/", data={"action": "login"})
        assert resp.status_code == 400

    def test_join_post_with_valid_csrf_token_is_accepted(self, app, client):
        app.config["WTF_CSRF_ENABLED"] = True
        joiner = _create_user(username="bob")
        owner = _create_user(username="carol", id=99)
        board = TriBoard(
            owner_id=owner.id, player_0_id=owner.id, player_0_accepted=True
        )
        db.session.add(board)
        db.session.commit()

        _login(client, username="bob")
        page = client.get("/join")
        token = _extract_csrf_token(page.get_data(as_text=True))

        resp = client.post(
            "/join",
            data={"board": str(board.id), "seat": "1", "csrf_token": token},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        db.session.refresh(board)
        assert board.player_1_id == joiner.id

    def test_admin_games_post_without_csrf_token_is_rejected(self, app, client):
        app.config["WTF_CSRF_ENABLED"] = True
        _login_as_admin(client)
        resp = client.post("/admin-games", data={"delete": "1"})
        assert resp.status_code == 400

    def test_admin_users_post_without_csrf_token_is_rejected(self, app, client):
        app.config["WTF_CSRF_ENABLED"] = True
        _login_as_admin(client)
        resp = client.post("/admin-users", data={"approve": "1"})
        assert resp.status_code == 400

    def test_api_endpoints_exempt_from_csrf(self, app, client):
        """JWT-bearer API routes must keep working with no csrf token at all."""
        app.config["WTF_CSRF_ENABLED"] = True
        user = _create_user()
        with app.test_request_context():
            token = create_access_token(identity=user.username)
        resp = client.post(
            "/api/v1/game/info",
            json={"slog": "", "view_pid": 0},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code != 400

    def test_token_endpoint_exempt_from_csrf(self, app, client):
        app.config["WTF_CSRF_ENABLED"] = True
        app.config["API_TOKEN_USERS"] = "alice"
        _create_user()
        resp = client.post(
            "/token", json={"username": "alice", "password": "password123"}
        )
        assert resp.status_code == 200
        assert "access_token" in resp.get_json()


class Test_Token_Endpoint_Allowlist:
    def test_oauth2_password_grant_form_body_succeeds(self, app, client):
        """Swagger UI's Authorize dialog POSTs an OAuth2 password-grant form
        body (not JSON) — the endpoint must accept that shape too."""
        app.config["API_TOKEN_USERS"] = "alice"
        _create_user()
        resp = client.post(
            "/token",
            data={
                "grant_type": "password",
                "username": "alice",
                "password": "password123",
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_username_not_on_allowlist_is_rejected(self, app, client):
        """Correct credentials for a user outside API_TOKEN_USERS still 404."""
        app.config["API_TOKEN_USERS"] = "alice"
        _create_user(username="bob")
        resp = client.post(
            "/token", json={"username": "bob", "password": "password123"}
        )
        assert resp.status_code == 404

    def test_empty_allowlist_rejects_everyone(self, app, client):
        """Default/unset API_TOKEN_USERS denies token issuance entirely."""
        app.config["API_TOKEN_USERS"] = ""
        _create_user()
        resp = client.post(
            "/token", json={"username": "alice", "password": "password123"}
        )
        assert resp.status_code == 404


class Test_GameInfo_InChessNext:
    def test_response_includes_in_chess_next(self, app, client):
        user = _create_user()
        with app.test_request_context():
            token = create_access_token(identity=user.username)
        resp = client.post(
            "/api/v1/game/info",
            json={
                "slog": "DNDLIAICNELIBOEIEDFENCLEEIHLCGCHOBGF",
                "view_pid": 0,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["in_chess_next"] == {
            "king_pos": 40,
            "chess_by": {"0": [], "1": [], "2": [{"gid": 54, "piece": "B"}]},
        }


class Test_Admin_Route_None_Checks:
    """H4a-adjacent: a stale/forged id must not crash the admin routes."""

    def test_admin_games_delete_unknown_id_does_not_crash(self, app, client):
        _login_as_admin(client)
        resp = client.post("/admin-games", data={"delete": "999"})
        assert resp.status_code in (302, 303)

    def test_admin_users_approve_unknown_id_does_not_crash(self, app, client):
        _login_as_admin(client)
        resp = client.post("/admin-users", data={"approve": "999"})
        assert resp.status_code in (302, 303)


class Test_Help_Route_Is_Public:
    def test_anonymous_can_view_help(self, client):
        resp = client.get("/help")
        assert resp.status_code == 200

    def test_logged_in_user_can_view_help(self, app, client):
        _create_user()
        _login(client)
        resp = client.get("/help")
        assert resp.status_code == 200


class Test_Index_Route_Redirects_By_Login_State:
    def test_anonymous_sees_landing_page(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Register" in resp.data
        for name in ("filio_light", "filio_dark", "ondro_light", "ondro_dark"):
            assert f"img/demo_{name}.mp4".encode() in resp.data

    def test_logged_in_non_admin_redirects_to_active_games(self, app, client):
        _create_user()
        _login(client)
        resp = client.get("/")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/games")

    def test_logged_in_admin_still_sees_landing_page(self, app, client):
        _login_as_admin(client)
        resp = client.get("/")
        assert resp.status_code == 200


class Test_Profile_Preview:
    def test_preview_shows_saved_settings(self, app, client):
        user = _create_user()
        user.board, user.theme, user.pieces = "filio", "night", "chubby"
        db.session.commit()
        _login(client)
        page = client.get("/profile").get_data(as_text=True)
        assert "previews/filio_night_chubby.jpg" in page
        assert "Statistics" in page

    def test_every_settings_combination_has_a_preview(self):
        # The preview card builds {board}_{theme}_{pieces}.jpg from the selects.
        previews = Path(webapp.__file__).parent / "static" / "previews"
        missing = [
            name
            for board in ProfileForm.board.kwargs["choices"]
            for theme in ProfileForm.theme.kwargs["choices"]
            for pieces in ProfileForm.pieces.kwargs["choices"]
            if not (previews / (name := f"{board}_{theme}_{pieces}.jpg")).is_file()
        ]
        assert not missing


class Test_Anonymous_Theme_Follows_System:
    def test_anonymous_page_follows_prefers_color_scheme(self, client):
        resp = client.get("/")
        assert b"matchMedia(" in resp.data

    def test_logged_in_user_keeps_own_theme(self, app, client):
        _create_user()
        _login(client)
        resp = client.get("/help")
        assert b"matchMedia(" not in resp.data


class Test_DBHandler_Commits_Log_Rows:
    def test_logger_error_persists_across_a_later_rollback(self, app):
        logger = logging.getLogger("webapp.some_module")
        logger.error("test error message for DBHandler")
        # Simulate the real-world case this bug hit: an unrelated exception
        # handler rolling back the session sometime after the log call.
        db.session.rollback()
        entry = Log.query.filter_by(message="test error message for DBHandler").first()
        assert entry is not None
        assert entry.level == "ERROR"


class Test_Registration_Username_Validation:
    def test_rejects_html_in_username(self, client):
        client.post(
            "/register",
            data={
                "username": "<script>alert(1)</script>",
                "password": "password123",
                "email": "attacker@example.com",
            },
            follow_redirects=True,
        )
        assert User.query.filter_by(email="attacker@example.com").first() is None

    def test_accepts_valid_username(self, client):
        client.post(
            "/register",
            data={
                "username": "good_user-1",
                "password": "password123",
                "email": "good@example.com",
            },
            follow_redirects=True,
        )
        user = User.query.filter_by(email="good@example.com").first()
        assert user is not None
        assert user.username == "good_user-1"


class Test_Google_Analytics:
    GA_ID = "G-TEST123"

    def _enable(self, app, monkeypatch):
        monkeypatch.setitem(app.config, "GA_MEASUREMENT_ID", self.GA_ID)
        monkeypatch.setitem(app.config, "DEBUG", False)

    def test_tag_absent_when_unconfigured(self, app, client, monkeypatch):
        monkeypatch.setitem(app.config, "GA_MEASUREMENT_ID", "")
        monkeypatch.setitem(app.config, "DEBUG", False)
        html = client.get("/help").get_data(as_text=True)
        assert "TRICHESS_GA" not in html
        assert "cookieSettings" not in html

    def test_tag_absent_in_debug_mode(self, app, client, monkeypatch):
        monkeypatch.setitem(app.config, "GA_MEASUREMENT_ID", self.GA_ID)
        html = client.get("/help").get_data(as_text=True)
        assert "TRICHESS_GA" not in html

    def test_tag_rendered_when_configured(self, app, client, monkeypatch):
        self._enable(app, monkeypatch)
        html = client.get("/help").get_data(as_text=True)
        assert self.GA_ID in html
        assert '"content_group": "help"' in html
        assert "analytics.js" in html
        assert "cookieSettings" in html

    def test_tag_absent_for_admin(self, app, client, monkeypatch):
        self._enable(app, monkeypatch)
        _login_as_admin(client)
        html = client.get("/help").get_data(as_text=True)
        assert "TRICHESS_GA" not in html

    def test_user_id_is_hashed_not_identifying(self, app, client, monkeypatch):
        self._enable(app, monkeypatch)
        user = _create_user()
        _login(client)
        html = client.get("/help").get_data(as_text=True)
        match = re.search(r'"user_id": "([0-9a-f]{32})"', html)
        assert match is not None
        assert user.username not in match.group(1)
        assert user.email not in html

    def test_login_event_emitted_once_on_next_page(self, app, client, monkeypatch):
        self._enable(app, monkeypatch)
        _create_user()
        _login(client)
        first = client.get("/help").get_data(as_text=True)
        assert '"name": "login"' in first
        second = client.get("/help").get_data(as_text=True)
        assert '"name": "login"' not in second

    def test_game_create_event_queued(self, app, client, monkeypatch):
        self._enable(app, monkeypatch)
        _create_user()
        _login(client)
        client.get("/help")  # drain the login event
        client.post("/join", data={"seat": "Seat 1"})
        html = client.get("/help").get_data(as_text=True)
        assert '"name": "game_create"' in html

    def _ga_game(self, html):
        import json

        match = re.search(r"window\.TRICHESS_GA = (\{.*?\});\n", html)
        assert match is not None
        return json.loads(match.group(1))["game"]

    @pytest.mark.parametrize("renderer", ["ondro", "filio"])
    def test_play_page_carries_game_context(self, app, client, monkeypatch, renderer):
        self._enable(app, monkeypatch)
        alice = _create_user()
        alice.board = renderer
        bot1 = User.query.filter_by(username="Bot 1").first()
        bot2 = User.query.filter_by(username="Bot 2").first()
        # alice in seat 1: one move made (seat 0), so she hasn't moved yet.
        tb = _seated_board([bot1, alice, bot2], 1, "BNDL")
        _login(client)

        game = self._ga_game(client.get(f"/play/{tb.id}").get_data(as_text=True))

        assert game == {"opponents": "bots", "renderer": renderer, "has_moved": False}

        tb.slog = "BNDLHBIB"  # seat 1 has moved now
        db.session.commit()
        game = self._ga_game(client.get(f"/play/{tb.id}").get_data(as_text=True))
        assert game["has_moved"] is True

    def test_play_page_opponents_mixed_and_humans(self, app, client, monkeypatch):
        self._enable(app, monkeypatch)
        alice = _create_user()
        bob = _create_user("bob")
        carol = _create_user("carol")
        bot1 = User.query.filter_by(username="Bot 1").first()
        mixed = _seated_board([alice, bob, bot1], 1)
        humans = _seated_board([alice, bob, carol], 1)
        _login(client)

        html = client.get(f"/play/{mixed.id}").get_data(as_text=True)
        assert self._ga_game(html)["opponents"] == "mixed"
        html = client.get(f"/play/{humans.id}").get_data(as_text=True)
        assert self._ga_game(html)["opponents"] == "humans"

    def test_game_start_event_when_last_seat_filled(self, app, client, monkeypatch):
        self._enable(app, monkeypatch)
        _create_user()
        _login(client)
        client.get("/help")  # drain the login event
        client.post("/join", data={"seat": "Seat 1"})
        board = TriBoard.query.one()
        client.post("/join", data={"board": board.id, "fill_bot": "1"})
        html = client.get("/help").get_data(as_text=True)
        assert '"name": "game_start"' not in html

        client.post("/join", data={"board": board.id, "fill_bot": "2"})
        html = client.get("/help").get_data(as_text=True)
        assert db.session.get(TriBoard, board.id).status == 1
        assert '"name": "game_start"' in html
        assert '"opponents": "bots"' in html

    def test_no_events_queued_when_unconfigured(self, app, client, monkeypatch):
        monkeypatch.setitem(app.config, "GA_MEASUREMENT_ID", "")
        _create_user()
        _login(client)
        with client.session_transaction() as sess:
            assert "ga_events" not in sess


class Test_Password_Reset_Token_Single_Use:
    def test_token_stops_working_after_password_change(self, app, client):
        from webapp.token import generate_password_reset_token

        user = _create_user("alice")
        with app.test_request_context():
            token = generate_password_reset_token(user)
        assert client.get(f"/reset/{token}").status_code == 200

        resp = client.post(
            f"/reset/{token}",
            data={"password": "newpassword123", "confirm": "newpassword123"},
        )
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

        resp = client.get(f"/reset/{token}")
        assert resp.status_code == 302
        assert "/forgot" in resp.headers["Location"]


class Test_Secret_Keys_Fail_Closed:
    def test_missing_secret_raises_outside_debug(self, monkeypatch):
        import pytest

        from webapp.configuration import _secret

        monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
        monkeypatch.delenv("DEBUG", raising=False)
        monkeypatch.delenv("FLASK_DEBUG", raising=False)
        with pytest.raises(RuntimeError):
            _secret("FLASK_SECRET_KEY")
        monkeypatch.setenv("DEBUG", "true")
        assert _secret("FLASK_SECRET_KEY")


def _needs_pg_dump():
    if db.engine.url.get_backend_name() == "postgresql" and not shutil.which("pg_dump"):
        pytest.skip("pg_dump not installed")


class Test_Dump_DB:
    def test_writes_schema_and_rows(self, app, tmp_path):
        _needs_pg_dump()
        _create_user()
        path = dump_db(tmp_path / "out.sql")
        sql = path.read_text()
        assert "CREATE TABLE" in sql and '"user"' in sql
        assert "alice" in sql

    def test_default_path_is_instance_folder(self, app, tmp_path, monkeypatch):
        _needs_pg_dump()
        monkeypatch.setattr(app, "instance_path", str(tmp_path))
        assert dump_db() == tmp_path / "trichess.sql"

    def test_replaces_old_dump_without_leftovers(self, app, tmp_path):
        _needs_pg_dump()
        out = tmp_path / "trichess.sql"
        out.write_text("stale")
        dump_db(out)
        assert out.read_text() != "stale"
        assert [p.name for p in tmp_path.iterdir()] == ["trichess.sql"]

    def test_cli_file_option(self, app, tmp_path):
        _needs_pg_dump()
        out = tmp_path / "cli.sql"
        result = app.test_cli_runner().invoke(args=["dump-db", "--file", str(out)])
        assert result.exit_code == 0, result.output
        assert out.exists()
        assert str(out) in result.output


# Two plain opening moves (seats 0 and 1), so seat 2 is on move.
_TWO_MOVES = "BNDLHBIB"


def _seated_board(players, status, slog=""):
    tb = TriBoard(
        owner_id=players[0].id,
        status=status,
        slog=slog,
        **{f"player_{i}_id": p.id for i, p in enumerate(players)},
        **{f"player_{i}_accepted": True for i in range(3)},
    )
    db.session.add(tb)
    db.session.commit()
    return tb


def _rows(html):
    return re.findall(r'<th scope="row">(\d+)</th>', html)


class TestGameLists:
    def _players(self):
        return [_create_user(name) for name in ("alice", "bob", "carol")]

    def test_games_shows_on_move_seat_and_vote_button(self, app, client):
        players = self._players()
        _seated_board(players, 1, _TWO_MOVES)
        voting = _seated_board(players, 1, _TWO_MOVES + "rXXA")
        _login(client)

        html = client.get("/games").get_data(as_text=True)

        assert html.count("<strong") == 2
        assert re.search(r"<strong[^>]*>carol", html)  # seat 2 on move
        assert re.search(r"<strong[^>]*>alice", html)  # vote shifts it to 0
        assert html.count(">Vote</a>") == 1
        assert f"/play/{voting.id}" in html or f"id={voting.id}" in html

    def test_archive_shows_scores_and_moves(self, app, client):
        alice, bob, carol = self._players()
        tb = _seated_board([alice, bob, carol], 2, _TWO_MOVES)
        for player, score in ((alice, 2.0), (bob, 0.0)):
            db.session.add(Score(player_id=player.id, board_id=tb.id, score=score))
        db.session.commit()
        _login(client)

        html = client.get("/archive").get_data(as_text=True)

        assert re.search(r"<strong[^>]*>alice \(2\)</strong>", html)
        assert "<span>bob (0)</span>" in html
        assert "<span>carol (0)</span>" in html  # no Score row
        assert "<td>2</td>" in html  # moves

    def test_archive_is_paginated(self, app, client):
        players = self._players()
        for _ in range(51):
            _seated_board(players, 2)
        _login(client)

        first = client.get("/archive").get_data(as_text=True)
        second = client.get("/archive?page=2").get_data(as_text=True)

        assert len(_rows(first)) == 50
        assert len(_rows(second)) == 1
        assert "Page 1 of 2" in first
        assert "page=2" in first

    def test_rating_matches_per_user_values(self, app, client):
        alice, bob, carol = self._players()
        outcomes = [
            {alice: (2.0, False, "N"), bob: (0.0, True, "N"), carol: (0.0, False, "N")},
            {
                alice: (2 / 3, False, "D"),
                bob: (2 / 3, False, "D"),
                carol: (2 / 3, False, "D"),
            },
            {
                alice: (0.0, False, "R"),
                bob: (2.0, False, "R"),
                carol: (0.0, False, "N"),
            },
        ]
        for result in outcomes:
            tb = _seated_board([alice, bob, carol], 2)
            for player, (score, onmove, tag) in result.items():
                db.session.add(
                    Score(
                        player_id=player.id,
                        board_id=tb.id,
                        score=score,
                        onmove=onmove,
                        tag=tag,
                    )
                )
        _seated_board([alice, bob, carol], 1)  # active: not counted
        db.session.commit()
        _login(client)

        expected = {
            "alice": ("2.6666666666666665", "1/1/0/1"),
            "bob": ("2.6666666666666665", "1/1/0/1"),
            "carol": ("0.6666666666666666", "0/1/2/0"),
        }

        html = client.get("/rating").get_data(as_text=True)

        # One chunk per ranking row (the template doesn't close its <tr>s).
        for chunk in html.split('<th scope="row">')[1:]:
            name = re.search(r">(\w+)</(?:strong|span)>", chunk).group(1)
            cells = re.findall(r"<td><span>(.*?)</span></td>", chunk)
            score, counts = expected.pop(name)
            assert cells[1:4] == [score, "3", counts], name
        assert expected == {}

    def test_admin_games_paginates_each_list(self, app, client):
        players = self._players()
        for _ in range(51):
            _seated_board(players, 1, _TWO_MOVES)
            _seated_board(players, 2)
        _login_as_admin(client)

        html = client.get("/admin-games?active_page=2&archive_page=1").get_data(
            as_text=True
        )

        assert html.count("Page 2 of 2") == 1
        assert html.count("Page 1 of 2") == 1
        assert "archive_page=1" in html
        assert "active_page=2" in html
