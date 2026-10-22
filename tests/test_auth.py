"""Auth hardening: generic login/sign-up answers, rate limits, proxy-aware
email links, user-id JWTs and safe account removal."""

import re
from datetime import datetime, timedelta, timezone

from flask_jwt_extended import create_access_token
from werkzeug.middleware.proxy_fix import ProxyFix

from tests.test_webapp import _create_user, _login, _login_as_admin, _seated_board
from webapp import email as email_module
from webapp.main import db
from webapp.models import Log, TriBoard, User


def _flashes(client):
    with client.session_transaction() as sess:
        return [message for _, message in sess.get("_flashes", [])]


class TestLoginAnswers:
    def _attempt(self, client, username):
        html = client.post(
            "/login", data={"username": username, "password": "nope-nope"}
        ).get_data(as_text=True)
        return " ".join(re.findall(r"Invalid[^<]*<a[^>]*>[^<]*</a>", html)) or html

    def test_wrong_password_and_unknown_user_look_the_same(self, app, client):
        _create_user()
        wrong_password = self._attempt(client, "alice")
        unknown_user = self._attempt(client, "nobody")
        assert wrong_password == unknown_user
        assert "Invalid username or password" in wrong_password


class TestRegistration:
    def _register(self, client, username, email):
        return client.post(
            "/register",
            data={"username": username, "password": "password123", "email": email},
        )

    def test_known_email_answers_like_a_new_sign_up(self, app, client):
        _create_user("alice")  # alice@example.com
        self._register(client, "newbie", "fresh@example.com")
        new_signup = _flashes(client)
        client.get("/")

        self._register(client, "other", "alice@example.com")

        assert _flashes(client) == new_signup
        assert User.query.filter_by(username="other").first() is None

    def test_known_email_owner_is_told(self, app, client):
        app.config["MAIL_SERVER"] = "smtp.example.com"
        try:
            _create_user("alice")
            self._register(client, "other", "alice@example.com")
            to, subject, body = email_module.notification_queue.jobs[0].args
        finally:
            app.config["MAIL_SERVER"] = ""
        assert to == "alice@example.com"
        assert "already belongs to your account (alice)" in body

    def test_taken_username_refused(self, app, client):
        _create_user("alice")
        self._register(client, "alice", "second@example.com")
        assert any("already in use" in m for m in _flashes(client))
        assert User.query.filter_by(username="alice").count() == 1

    def test_abandoned_sign_up_frees_its_name(self, app, client):
        stale = _create_user("alice", active=False)
        stale.created_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            days=2
        )
        db.session.commit()

        self._register(client, "alice", "new@example.com")

        user = User.query.filter_by(username="alice").one()
        assert user.email == "new@example.com"

    def test_recent_pending_sign_up_keeps_its_name(self, app, client):
        _create_user("alice", active=False)
        self._register(client, "alice", "new@example.com")
        assert User.query.filter_by(username="alice").one().email == "alice@example.com"


class TestRateLimits:
    def test_login_attempts_limited(self, app, client):
        _create_user()
        codes = [
            client.post(
                "/login", data={"username": "alice", "password": "wrong-pass"}
            ).status_code
            for _ in range(11)
        ]
        assert codes[:10] == [200] * 10
        assert codes[10] == 429

    def test_one_account_limited_across_addresses(self, app, client):
        _create_user()
        codes = [
            client.post(
                "/login",
                data={"username": "Alice", "password": "wrong-pass"},
                environ_base={"REMOTE_ADDR": f"10.0.0.{i}"},
            ).status_code
            for i in range(21)
        ]
        assert codes[-1] == 429 and 429 not in codes[:20]

    def test_forgot_and_register_limited(self, app, client):
        for path, data, allowed in (
            ("/forgot", {"email": "x@example.com"}, 5),
            ("/register", {"username": "a", "password": "p", "email": "x"}, 5),
        ):
            codes = [
                client.post(path, data=data).status_code for _ in range(allowed + 1)
            ]
            assert 429 not in codes[:allowed] and codes[allowed] == 429, path

    def test_page_views_not_limited(self, app, client):
        assert all(client.get("/login").status_code == 200 for _ in range(15))


class TestBehindProxy:
    def test_reset_link_is_https_behind_tls_proxy(self, app, client, monkeypatch):
        # What TRUSTED_PROXY_HOPS=1 installs at import (webapp/main.py).
        monkeypatch.setattr(app, "wsgi_app", ProxyFix(app.wsgi_app, x_proto=1))
        app.config["MAIL_SERVER"] = "smtp.example.com"
        try:
            _create_user()
            client.post(
                "/forgot",
                data={"email": "alice@example.com"},
                headers={"X-Forwarded-Proto": "https"},
            )
            body = email_module.notification_queue.jobs[0].args[2]
        finally:
            app.config["MAIL_SERVER"] = ""
        assert "https://localhost/reset/" in body


class TestUserIdTokens:
    def _games(self, client, token):
        return client.get(
            "/api/v1/manager/games", headers={"Authorization": f"Bearer {token}"}
        )

    def test_id_token_works(self, app, client):
        alice = _create_user()
        with app.test_request_context():
            token = create_access_token(identity=str(alice.id))
        assert self._games(client, token).status_code == 200

    def test_username_token_from_before_rejected(self, app, client):
        _create_user()
        with app.test_request_context():
            token = create_access_token(identity="alice")
        assert self._games(client, token).status_code == 401

    def test_removed_user_token_rejected(self, app, client):
        alice, bob, carol = (_create_user(n) for n in ("alice", "bob", "carol"))
        _seated_board([alice, bob, carol], 2)
        with app.test_request_context():
            token = create_access_token(identity=str(alice.id))
        _login_as_admin(client)
        client.post("/admin-users", data={"delete": alice.id})
        assert self._games(client, token).status_code == 401


class TestRemoveUser:
    def test_user_with_games_is_anonymised(self, app, client):
        alice, bob, carol = (_create_user(n) for n in ("alice", "bob", "carol"))
        tb = _seated_board([alice, bob, carol], 2)
        _login_as_admin(client)

        resp = client.post("/admin-users", data={"delete": alice.id})

        assert resp.status_code == 302
        db.session.expire_all()
        user = db.session.get(User, alice.id)
        assert user.username == f"[deleted {alice.id}]"
        assert user.email is None and not user.active
        assert db.session.get(TriBoard, tb.id).player_0_id == alice.id
        client.post("/logout/")
        html = client.post(
            "/login", data={"username": "alice", "password": "password123"}
        ).get_data(as_text=True)
        assert "Invalid username or password" in html

    def test_user_without_games_is_deleted(self, app, client):
        dave = _create_user("dave")
        db.session.add(Log(level="GAME", message="x", user_id=dave.id))
        db.session.commit()
        _login_as_admin(client)

        client.post("/admin-users", data={"delete": dave.id})

        db.session.expire_all()
        assert db.session.get(User, dave.id) is None
        assert Log.query.filter_by(user_id=dave.id).count() == 0

    def test_waiting_games_are_left(self, app, client):
        alice, bob = _create_user("alice"), _create_user("bob")
        alone = TriBoard(owner_id=alice.id, player_0_id=alice.id)
        shared = TriBoard(owner_id=alice.id, player_0_id=alice.id, player_1_id=bob.id)
        db.session.add_all([alone, shared])
        db.session.commit()
        _login_as_admin(client)

        client.post("/admin-users", data={"delete": alice.id})

        db.session.expire_all()
        assert db.session.get(TriBoard, alone.id) is None
        shared = db.session.get(TriBoard, shared.id)
        assert shared.player_0_id is None and shared.owner_id == bob.id
        assert db.session.get(User, alice.id) is None  # no game left: deleted

    def test_admin_and_bots_cannot_be_removed(self, app, client):
        admin = _login_as_admin(client)
        bot = User.query.filter_by(username="Bot 1").one()
        for user in (admin, bot):
            client.post("/admin-users", data={"delete": user.id})
        db.session.expire_all()
        assert db.session.get(User, admin.id).username == "admin"
        assert db.session.get(User, bot.id).username == "Bot 1"

    def test_verification_link_cannot_reopen_removed_account(self, app, client):
        from webapp.token import generate_verification_token

        alice, bob, carol = (_create_user(n) for n in ("alice", "bob", "carol"))
        _seated_board([alice, bob, carol], 2)
        with app.test_request_context():
            token = generate_verification_token(alice)
        _login_as_admin(client)
        client.post("/admin-users", data={"delete": alice.id})
        client.post("/logout/")

        client.get(f"/verify/{token}")

        db.session.expire_all()
        assert not db.session.get(User, alice.id).active


class TestLogoutIsPost:
    def test_get_is_not_allowed(self, app, client):
        _create_user()
        _login(client)
        assert client.get("/logout/").status_code == 405
        assert client.get("/profile").status_code == 200

    def test_navbar_logout_needs_csrf_token(self, app, client):
        from tests.test_webapp import _extract_csrf_token

        _create_user()
        _login(client)
        app.config["WTF_CSRF_ENABLED"] = True
        try:
            assert client.post("/logout/").status_code == 400
            page = client.get("/profile").get_data(as_text=True)
            assert 'formaction="/logout/"' in page
            token = _extract_csrf_token(page)
            assert (
                client.post("/logout/", data={"csrf_token": token}).status_code == 302
            )
        finally:
            app.config["WTF_CSRF_ENABLED"] = False
        assert client.get("/profile").status_code == 302


class TestVerificationTokenNamesEmail:
    def _token(self, app, payload):
        from itsdangerous import URLSafeTimedSerializer

        with app.app_context():
            serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])
            return serializer.dumps(payload, salt="email-verify")

    def test_link_for_old_email_rejected_after_change(self, app, client):
        from webapp.token import generate_verification_token

        alice = _create_user()
        with app.test_request_context():
            token = generate_verification_token(alice)
        alice.email = "new@example.com"
        alice.email_verified = False
        db.session.commit()

        client.get(f"/verify/{token}")

        db.session.expire_all()
        assert not db.session.get(User, alice.id).email_verified

    def test_link_for_current_email_verifies(self, app, client):
        from webapp.token import generate_verification_token

        alice = _create_user(active=False)
        with app.test_request_context():
            token = generate_verification_token(alice)

        client.get(f"/verify/{token}")

        db.session.expire_all()
        user = db.session.get(User, alice.id)
        assert user.active and user.email_verified

    def test_legacy_link_activates_a_new_sign_up(self, app, client):
        alice = _create_user(active=False)
        client.get(f"/verify/{self._token(app, alice.id)}")
        db.session.expire_all()
        assert db.session.get(User, alice.id).active

    def test_legacy_link_does_not_verify_a_changed_email(self, app, client):
        alice = _create_user()
        alice.email_verified = False
        db.session.commit()
        client.get(f"/verify/{self._token(app, alice.id)}")
        db.session.expire_all()
        assert not db.session.get(User, alice.id).email_verified


class TestPasswordChangeEndsSessions:
    """The app fixture holds one app context for the whole test, so g (and
    Flask-Login's cached g._login_user) outlives a request; _forget() makes
    the next request load its user from the session again, as in production."""

    @staticmethod
    def _forget():
        from flask import g

        g.pop("_login_user", None)

    def test_other_session_ends_changer_stays(self, app):
        _create_user()
        mine, other = app.test_client(), app.test_client()
        _login(mine)
        _login(other)
        mine.post(
            "/profile_password",
            data={"password": "password123", "password_new": "newpass456"},
        )
        self._forget()
        assert mine.get("/profile").status_code == 200
        self._forget()
        assert other.get("/profile").status_code == 302

    def test_reset_ends_sessions(self, app, client):
        from webapp.token import generate_password_reset_token

        alice = _create_user()
        _login(client)
        with app.test_request_context():
            token = generate_password_reset_token(alice)
        app.test_client().post(
            f"/reset/{token}", data={"password": "newpass456", "confirm": "newpass456"}
        )
        self._forget()
        assert client.get("/profile").status_code == 302

    def test_plain_id_session_from_before_is_logged_out(self, app, client):
        alice = _create_user()
        with client.session_transaction() as sess:
            sess["_user_id"] = str(alice.id)
            sess["_fresh"] = True
        assert client.get("/profile").status_code == 302

    def test_refresh_token_rejected_after_password_change(self, app, client):
        from werkzeug.security import generate_password_hash

        alice = _create_user()
        app.config["API_TOKEN_USERS"] = "alice"
        try:
            refresh = client.post(
                "/token", json={"username": "alice", "password": "password123"}
            ).get_json()["refresh_token"]
        finally:
            app.config["API_TOKEN_USERS"] = ""
        headers = {"Authorization": f"Bearer {refresh}"}
        assert client.post("/refresh", headers=headers).status_code == 200

        alice.password = generate_password_hash("newpass456")
        db.session.commit()
        assert client.post("/refresh", headers=headers).status_code == 401


class TestProxyWarning:
    def test_forwarded_request_without_trusted_hops_warns_once(
        self, app, client, monkeypatch, caplog
    ):
        from webapp import main

        monkeypatch.setattr(main, "_proxy_warned", False)
        headers = {"X-Forwarded-For": "203.0.113.7"}
        client.get("/", headers=headers)
        client.get("/", headers=headers)
        warnings = [r for r in caplog.records if "TRUSTED_PROXY_HOPS" in r.message]
        assert len(warnings) == 1

    def test_no_warning_with_trusted_hops(self, app, client, monkeypatch, caplog):
        from webapp import main

        monkeypatch.setattr(main, "_proxy_warned", False)
        monkeypatch.setitem(app.config, "TRUSTED_PROXY_HOPS", 1)
        client.get("/", headers={"X-Forwarded-For": "203.0.113.7"})
        assert not [r for r in caplog.records if "TRUSTED_PROXY_HOPS" in r.message]


class TestCors:
    def test_no_credentials_allowed(self, app, client):
        origin = app.config["CORS_ORIGINS"][0]
        resp = client.get("/api/v1/manager/games", headers={"Origin": origin})
        assert resp.headers.get("Access-Control-Allow-Origin") == origin
        assert "Access-Control-Allow-Credentials" not in resp.headers
