import logging
import re

from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash

from webapp.main import db
from webapp.models import Log, TriBoard, User


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
        _create_user()
        resp = client.post(
            "/token", json={"username": "alice", "password": "password123"}
        )
        assert resp.status_code == 200
        assert "access_token" in resp.get_json()


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
