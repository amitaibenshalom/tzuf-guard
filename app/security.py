import hashlib
import secrets


def normalize_email(email):
    return email.strip().lower()


def hash_door_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_secure_token():
    return secrets.token_urlsafe(32)


def hash_reset_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
