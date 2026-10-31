import hashlib
import secrets

from diceware.wordlist import WordList, get_wordlist_path

# Six choices from EFF's 7,776-word list provide about 77.5 bits of entropy while
# keeping the credential short enough to copy into the sensor setup page.
DOOR_TOKEN_WORDS = tuple(WordList(get_wordlist_path("en_eff")))


def normalize_email(email):
    return email.strip().lower()


def hash_door_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_secure_token():
    return secrets.token_urlsafe(32)


def generate_door_token():
    return "-".join(secrets.choice(DOOR_TOKEN_WORDS) for _ in range(6))


def hash_reset_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
