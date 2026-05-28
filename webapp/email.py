import logging
import smtplib
from email.message import EmailMessage

from flask import current_app, url_for

from webapp.token import generate_verification_token

logger = logging.getLogger(__name__)


def send_email(to, subject, body):
    server = current_app.config["MAIL_SERVER"]
    if not server:
        logger.warning(
            "MAIL_SERVER not configured — skipping email to %s: %s", to, subject
        )
        return False

    port = current_app.config["MAIL_PORT"]
    username = current_app.config["MAIL_USERNAME"]
    password = current_app.config["MAIL_PASSWORD"]
    use_tls = current_app.config["MAIL_USE_TLS"]
    sender = current_app.config["MAIL_DEFAULT_SENDER"]

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(server, port, timeout=30) as smtp:
            if use_tls:
                smtp.starttls()
            if username and password:
                smtp.login(username, password)
            smtp.send_message(msg)
        logger.info("Verification email sent to %s", to)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to, e)
        return False


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
