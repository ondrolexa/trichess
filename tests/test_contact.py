"""The Contact form (/contact): mails the admins (CONTACT_EMAILS) with the
player as Reply-To, plus a copy to the player — the admin addresses never
appear in a page."""

import io

import pytest

from webapp import email as email_module
from webapp import notifications
from webapp.models import Log
from webapp.notifications import _send_email_job

from .test_webapp import _create_user, _extract_csrf_token, _login, _login_as_admin

ADMINS = ["first-admin@example.org", "second-admin@example.org"]


@pytest.fixture
def enabled(app, monkeypatch):
    monkeypatch.setitem(app.config, "CONTACT_EMAILS", ADMINS)
    monkeypatch.setitem(app.config, "MAIL_SERVER", "smtp.example.com")
    return app


def _post(client, **data):
    data.setdefault("subject", "Board bug")
    data.setdefault("message", "The board froze after my move.")
    return client.post("/contact", data=data, content_type="multipart/form-data")


def _jobs():
    return email_module.notification_queue.jobs


class TestAccess:
    def test_anonymous_is_sent_to_login(self, enabled, client):
        resp = client.get("/contact")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_menu_link_for_players_only(self, enabled, client):
        assert 'href="/contact"' not in client.get("/").get_data(as_text=True)
        _create_user()
        _login(client)
        assert 'href="/contact"' in client.get("/games").get_data(as_text=True)

    def test_admin_has_no_menu_link_and_is_redirected(self, enabled, client):
        _login_as_admin(client)
        assert 'href="/contact"' not in client.get("/").get_data(as_text=True)
        assert client.get("/contact").status_code == 302

    @pytest.mark.parametrize("setting", ["CONTACT_EMAILS", "MAIL_SERVER"])
    def test_disabled_without_recipients_or_mail(
        self, enabled, client, monkeypatch, setting
    ):
        monkeypatch.setitem(
            enabled.config, setting, [] if setting == "CONTACT_EMAILS" else ""
        )
        _create_user()
        _login(client)
        assert 'href="/contact"' not in client.get("/games").get_data(as_text=True)
        assert client.get("/contact").status_code == 404


class TestSending:
    def test_message_goes_to_admins_and_copy_to_sender(self, enabled, client):
        user = _create_user()
        _login(client)
        resp = _post(client)

        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/games")
        admins, copy = _jobs()
        assert admins.args[0] == ADMINS
        assert admins.args[1] == "[Trichess contact] Board bug"
        assert f"user id {user.id}" in admins.args[2]
        assert "The board froze" in admins.args[2]
        assert admins.kwargs == {"reply_to": "alice@example.com", "attachment": None}
        assert copy.args[0] == "alice@example.com"
        assert "The board froze" in copy.args[2]
        assert copy.kwargs["attachment"] is None
        page = client.get("/games").get_data(as_text=True)
        assert "Your message was sent to the admins." in page

    def test_logged_to_log_table(self, enabled, client):
        user = _create_user()
        _login(client)
        _post(client)
        row = Log.query.filter(Log.message.like("Contact message%")).one()
        assert row.user_id == user.id
        assert "Board bug" in row.message

    def test_admin_addresses_never_rendered(self, enabled, client):
        _create_user()
        _login(client)
        pages = [client.get(p).get_data(as_text=True) for p in ("/contact", "/games")]
        _post(client)
        pages.append(client.get("/games").get_data(as_text=True))
        for html in pages:
            for address in ADMINS:
                assert address not in html

    def test_missing_subject_rerenders_form(self, enabled, client):
        _create_user()
        _login(client)
        resp = _post(client, subject="")
        assert resp.status_code == 200
        assert len(_jobs()) == 0

    def test_rate_limited_per_player(self, enabled, client, monkeypatch):
        monkeypatch.setitem(enabled.config, "RATELIMIT_ENABLED", True)
        _create_user()
        _login(client)
        for _ in range(3):
            assert _post(client).status_code == 302
        assert _post(client).status_code == 429


class TestAttachment:
    def test_allowed_file_is_attached_to_admin_mail_only(self, enabled, client):
        _create_user()
        _login(client)
        png = b"\x89PNG\r\n" + b"x" * 200_000  # well over the app-wide 64 KB
        _post(client, attachment=(io.BytesIO(png), "my screen shot.png"))

        admins, copy = _jobs()
        assert admins.kwargs["attachment"] == ("my_screen_shot.png", "image/png", png)
        assert copy.kwargs["attachment"] is None
        assert "my_screen_shot.png" in copy.args[2]

    def test_disallowed_extension_rejected(self, enabled, client):
        _create_user()
        _login(client)
        resp = _post(client, attachment=(io.BytesIO(b"MZ..."), "tool.exe"))
        assert resp.status_code == 200
        assert "Images, PDF or text files only." in resp.get_data(as_text=True)
        assert len(_jobs()) == 0

    def test_file_over_1mb_rejected(self, enabled, client):
        _create_user()
        _login(client)
        big = b"x" * (1024 * 1024 + 1)
        resp = _post(client, attachment=(io.BytesIO(big), "log.txt"))
        assert len(_jobs()) == 0
        # Within the raised body limit, so FileSize rejects it on the form.
        assert resp.status_code == 200
        assert "Attachment too large (max 1 MB)." in resp.get_data(as_text=True)

    def test_body_far_over_limit_redirects_back_to_form(self, enabled, client):
        _create_user()
        _login(client)
        huge = b"x" * (2 * 1024 * 1024)
        resp = _post(client, attachment=(io.BytesIO(huge), "log.txt"))
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/contact")
        assert len(_jobs()) == 0

    def test_other_routes_keep_the_64kb_limit(self, enabled, client):
        resp = client.post("/login", data={"username": "x" * (70 * 1024)})
        assert resp.status_code == 413

    def test_upload_with_csrf_enabled(self, enabled, client):
        enabled.config["WTF_CSRF_ENABLED"] = True
        _create_user()
        _login(client)
        token = _extract_csrf_token(client.get("/contact").get_data(as_text=True))
        resp = _post(
            client,
            csrf_token=token,
            attachment=(io.BytesIO(b"y" * 300_000), "notes.txt"),
        )
        assert resp.status_code == 302
        assert len(_jobs()) == 2


def test_send_email_job_with_reply_to_and_attachment(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, server, port, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            pass

        def send_message(self, msg):
            sent["msg"] = msg

    monkeypatch.setenv("MAIL_SERVER", "smtp.example.com")
    monkeypatch.setenv("MAIL_DEFAULT_SENDER", "trichess@example.com")
    monkeypatch.setattr(notifications.smtplib, "SMTP", FakeSMTP)

    _send_email_job(
        ADMINS,
        "Subj",
        "Body",
        reply_to="player@example.com",
        attachment=("shot.png", "image/png", b"\x89PNG"),
    )

    msg = sent["msg"]
    assert msg["To"] == ", ".join(ADMINS)
    assert msg["Reply-To"] == "player@example.com"
    (part,) = list(msg.iter_attachments())
    assert part.get_filename() == "shot.png"
    assert part.get_content_type() == "image/png"
    assert part.get_content() == b"\x89PNG"
