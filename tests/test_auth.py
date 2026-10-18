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
        client.get("/logout/")
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
            token = generate_verification_token(alice.id)
        _login_as_admin(client)
        client.post("/admin-users", data={"delete": alice.id})
        client.get("/logout/")

        client.get(f"/verify/{token}")

        db.session.expire_all()
        assert not db.session.get(User, alice.id).active
