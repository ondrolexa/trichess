import logging
import mimetypes

from flask import current_app, url_for
from werkzeug.utils import secure_filename

from webapp.notifications import _send_email_job, notification_queue
from webapp.token import generate_password_reset_token, generate_verification_token

logger = logging.getLogger(__name__)


def send_email(to, subject, body, reply_to=None, attachment=None):
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
    notification_queue.enqueue(
        _send_email_job, to, subject, body, reply_to=reply_to, attachment=attachment
    )
    return True


def send_verification_email(user):
    token = generate_verification_token(user)
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
    token = generate_password_reset_token(user)
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


def send_account_exists_email(user):
    """Sent instead of a second account when someone registers with an email
    that already has one (the form answers the same either way)."""
    forgot_url = url_for("forgot", _external=True)
    subject = "Trichess registration attempt"
    body = (
        f"Hi {user.username},\n\n"
        f"Someone tried to register a new Trichess account with this email "
        f"address, which already belongs to your account ({user.username}).\n\n"
        f"If it was you and you forgot your password, reset it here:\n"
        f"{forgot_url}\n\n"
        f"Otherwise you can ignore this email.\n\n"
        f"Best,\nTrichess Team"
    )
    return send_email(user.email, subject, body)


def send_contact_email(user, subject, message, file=None):
    """Mail a Contact form message to the admins (CONTACT_EMAILS), replying
    to the player, and a copy (without the attachment) to the player.

    *file* is the form's FileStorage, if any. Returns whether the admins'
    email was queued.
    """
    attachment = None
    if file:
        filename = secure_filename(file.filename) or "attachment"
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        attachment = (filename, content_type, file.read())
    body = (
        f"From: {user.username} (user id {user.id}, {user.email or 'no email'})\n"
        f"Subject: {subject}\n\n"
        f"{message}\n"
    )
    queued = send_email(
        current_app.config["CONTACT_EMAILS"],
        f"[Trichess contact] {subject}",
        body,
        reply_to=user.email,
        attachment=attachment,
    )
    if queued and user.email:
        copy = (
            f"Hi {user.username},\n\n"
            f"We received your message and will get back to you by email.\n\n"
            f"Subject: {subject}\n\n"
            f"{message}\n\n"
            + (f"(Attachment: {attachment[0]})\n\n" if attachment else "")
            + "Best,\nTrichess Team"
        )
        send_email(user.email, f"Your Trichess message: {subject}", copy)
    return queued
