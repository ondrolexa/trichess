from flask import current_app
from itsdangerous import URLSafeTimedSerializer


def generate_verification_token(user_id):
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    return serializer.dumps(user_id, salt="email-verify")


def verify_verification_token(token, max_age=86400):
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    try:
        user_id = serializer.loads(token, salt="email-verify", max_age=max_age)
    except Exception:
        return None
    return user_id


def generate_password_reset_token(user_id):
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    return serializer.dumps(user_id, salt="password-reset")


def verify_password_reset_token(token, max_age=3600):
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    try:
        user_id = serializer.loads(token, salt="password-reset", max_age=max_age)
    except Exception:
        return None
    return user_id
