import logging

from flask import current_app, url_for

from webapp.notifications import _send_email_job, notification_queue
from webapp.token import generate_password_reset_token, generate_verification_token

logger = logging.getLogger(__name__)


def send_email(to, subject, body):
    """Queue an email — never blocks the caller on the SMTP connection.

    Returns whether it was queued, not whether it was actually delivered
    (that now happens asynchronously in the worker; failures are logged
    there, not surfaced back to the caller). The MAIL_SERVER-configured
    check stays synchronous so callers like register() can still tell
    "email isn't set up at all" apart from "queued, should arrive soon".
    """
    server = current_app.config["MAIL_SERVER"]
    if not server:
        logger.warning(
            "MAIL_SERVER not configured — skipping email to %s: %s", to, subject
        )
        return False
    notification_queue.enqueue(_send_email_job, to, subject, body)
    return True


def send_verification_email(user):
    token = generate_verification_token(user.id)
    verify_url = url_for("verify", token=token, _external=True)
    subject = "Verify your Trichess account"
    body = (
        f"Hi {user.username},\n\n"
        f"Thank you for registering at https://trichess.mykuna.eu/.\n\n"
        f"Please verify your email address by clicking the link below:\n"
        f"{verify_url}\n\n"
        f"This link expires in 24 hours.\n\n"
        f"If you did not register, please ignore this email.\n\n"
        f"Best,\nTrichess Team"
    )
    return send_email(user.email, subject, body)


def send_password_reset_email(user):
    token = generate_password_reset_token(user.id)
    reset_url = url_for("reset", token=token, _external=True)
    subject = "Trichess password reset"
    body = (
        f"Hi {user.username},\n\n"
        f"Click the link below to reset your password:\n"
        f"{reset_url}\n\n"
        f"This link expires in 1 hour.\n\n"
        f"If you did not request a password reset, please ignore this email.\n\n"
        f"Best,\nTrichess Team"
    )
    return send_email(user.email, subject, body)
