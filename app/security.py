import hashlib
import secrets


# Twelve choices from a 128-word list provide 84 bits of entropy while keeping
# the credential easy to read, copy, and enter on the sensor setup page.
DOOR_TOKEN_WORDS = tuple(
    """
    acorn amber anchor apple arch arrow atlas autumn bamboo beacon berry birch
    bloom breeze brook button cabin candle canyon cedar cherry circle cloud coral
    dawn delta drift dune eagle earth ember fern field flame forest frost garden
    glass grove harbor hazel hill honey island ivory jasmine juniper lake lantern
    leaf lemon lilac lotus maple meadow mint moon moss mountain oak ocean olive
    orchid pebble pine planet plum pond poppy quartz rain reed river robin rose
    ruby sage sand shadow shore silver sky snow solar sparrow spring star stone
    storm summit sun sunset tide timber tulip valley velvet violet wave willow wind
    winter wood zephyr almond badger basket blue bronze comet copper cosmos cricket
    daisy echo falcon feather fig galaxy ginger heron kite lagoon marble merlot
    opal peach pearl
    """.split()
)


def normalize_email(email):
    return email.strip().lower()


def hash_door_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_secure_token():
    return secrets.token_urlsafe(32)


def generate_door_token():
    return "-".join(secrets.choice(DOOR_TOKEN_WORDS) for _ in range(12))


def hash_reset_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
