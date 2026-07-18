from webapp import email as email_module
from webapp import main, notifications
from webapp.notifications import _send_email_job, _send_push_notification_job


class TestPostNotification:
    def test_skipped_in_debug_mode(self, app):
        # The `app` fixture runs with DEBUG=True.
        main.post_notification("alice", "hi", "Title", 1)
        assert len(main.notification_queue) == 0

    def test_enqueues_when_not_debug(self, app):
        app.debug = False
        try:
            main.post_notification("alice", "hi", "Title", 1)
            assert len(main.notification_queue) == 1
        finally:
            app.debug = True


class TestSendEmail:
    def test_skipped_when_mail_server_unset(self, app):
        # The `app` fixture runs with MAIL_SERVER="".
        with app.app_context():
            assert email_module.send_email("a@example.com", "Subj", "Body") is False
        assert len(email_module.notification_queue) == 0

    def test_enqueues_when_mail_server_set(self, app):
        app.config["MAIL_SERVER"] = "smtp.example.com"
        try:
            with app.app_context():
                result = email_module.send_email("a@example.com", "Subj", "Body")
            assert result is True
            assert len(email_module.notification_queue) == 1
        finally:
            app.config["MAIL_SERVER"] = ""


class TestSendPushNotificationJob:
    def test_posts_to_ntfy_with_expected_shape(self, monkeypatch):
        calls = []

        def fake_post(url, data, headers, timeout):
            calls.append((url, data, headers, timeout))

        monkeypatch.setattr(notifications.requests, "post", fake_post)
        _send_push_notification_job("alice", "It's your turn", "Your turn", 42)

        assert len(calls) == 1
        url, data, headers, timeout = calls[0]
        assert url == "https://ntfy.mykuna.eu/trichess_alice"
        assert data == b"It's your turn"
        assert headers["Title"] == "Your turn"
        assert headers["Click"] == "https://trichess.mykuna.eu/play/42"
        assert timeout == (3, 5)

    def test_swallows_connection_errors(self, monkeypatch):
        import requests

        def raise_connection_error(*args, **kwargs):
            raise requests.exceptions.ConnectionError("unreachable")

        monkeypatch.setattr(notifications.requests, "post", raise_connection_error)
        # Must not raise.
        _send_push_notification_job("alice", "hi", "Title", 1)

    def test_swallows_unexpected_errors(self, monkeypatch):
        def raise_value_error(*args, **kwargs):
            raise ValueError("boom")

        monkeypatch.setattr(notifications.requests, "post", raise_value_error)
        # Must not raise.
        _send_push_notification_job("alice", "hi", "Title", 1)


class TestSendEmailJob:
    def test_noop_when_mail_server_unset(self, monkeypatch):
        monkeypatch.setattr(notifications, "smtplib", None)  # would blow up if used
        monkeypatch.setenv("MAIL_SERVER", "")
        _send_email_job("a@example.com", "Subj", "Body")

    def test_sends_via_smtp_with_expected_shape(self, monkeypatch):
        sent = {}

        class FakeSMTP:
            def __init__(self, server, port, timeout):
                sent["server"] = server
                sent["port"] = port
                sent["timeout"] = timeout

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def starttls(self):
                sent["starttls"] = True

            def login(self, username, password):
                sent["login"] = (username, password)

            def send_message(self, msg):
                sent["msg"] = msg

        monkeypatch.setenv("MAIL_SERVER", "smtp.example.com")
        monkeypatch.setenv("MAIL_PORT", "587")
        monkeypatch.setenv("MAIL_USERNAME", "bot")
        monkeypatch.setenv("MAIL_PASSWORD", "secret")
        monkeypatch.setenv("MAIL_USE_TLS", "true")
        monkeypatch.setenv("MAIL_DEFAULT_SENDER", "trichess@example.com")
        monkeypatch.setattr(notifications.smtplib, "SMTP", FakeSMTP)

        _send_email_job("a@example.com", "Subj", "Body")

        assert sent["server"] == "smtp.example.com"
        assert sent["port"] == 587
        assert sent["starttls"] is True
        assert sent["login"] == ("bot", "secret")
        assert sent["msg"]["To"] == "a@example.com"
        assert sent["msg"]["From"] == "trichess@example.com"
        assert sent["msg"]["Subject"] == "Subj"

    def test_swallows_smtp_errors(self, monkeypatch):
        class FailingSMTP:
            def __init__(self, *args, **kwargs):
                raise OSError("connection refused")

        monkeypatch.setenv("MAIL_SERVER", "smtp.example.com")
        monkeypatch.setattr(notifications.smtplib, "SMTP", FailingSMTP)
        # Must not raise.
        _send_email_job("a@example.com", "Subj", "Body")
