import hashlib


def normalize_email(email):
    return email.strip().lower()


def hash_door_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
