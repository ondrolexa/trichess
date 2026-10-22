import hashlib

from flask import current_app
from itsdangerous import URLSafeTimedSerializer


def generate_verification_token(user):
    """Names the address it verifies, so after an email change an older,
    still-valid link can't mark the new address verified."""
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    return serializer.dumps([user.id, user.email], salt="email-verify")


def verify_verification_token(token, max_age=86400):
    """Return (user_id, email), or None if invalid/expired. Tokens issued
    before they named an email (a bare user id) give email None."""
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    try:
        payload = serializer.loads(token, salt="email-verify", max_age=max_age)
    except Exception:
        return None
    if isinstance(payload, int):
        return payload, None
    try:
        user_id, email = payload
    except TypeError, ValueError:
        return None
    return user_id, email


def password_fingerprint(user):
    """Short digest of the user's current password hash. Embedded in reset
    tokens so a token stops working once the password has changed."""
    return hashlib.sha256((user.password or "").encode()).hexdigest()[:16]


def generate_password_reset_token(user):
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    return serializer.dumps(
        [user.id, password_fingerprint(user)], salt="password-reset"
    )


def verify_password_reset_token(token, max_age=3600):
    """Return (user_id, password_fingerprint), or None if invalid/expired."""
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    try:
        user_id, fingerprint = serializer.loads(
            token, salt="password-reset", max_age=max_age
        )
    except Exception:
        return None
    return user_id, fingerprint
