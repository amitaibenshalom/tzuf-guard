import hashlib
import hmac
import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

DEFAULT_GOOGLE_OAUTH_CLIENT_IDS = ",".join(
    [
        "62060365746-5lrgdhjnr57qg7pbumo4p3durcf9nbl1.apps.googleusercontent.com",
        "62060365746-ht958df0nupek5s87uuthu274qin8s98.apps.googleusercontent.com",
    ]
)
DEFAULT_GOOGLE_WEB_CLIENT_ID = (
    "62060365746-ht958df0nupek5s87uuthu274qin8s98.apps.googleusercontent.com"
)
DEVICE_HEALTH_CRON_CONTEXT = b"tzufguard-device-health-cron-v1"


def derive_device_health_cron_secret(secret_key):
    return hmac.new(
        secret_key.encode("utf-8"),
        DEVICE_HEALTH_CRON_CONTEXT,
        hashlib.sha256,
    ).hexdigest()


def bool_from_env(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes"}


def turso_database_uri():
    turso_url = os.getenv("TURSO_DATABASE_URL", "").strip()
    if not turso_url:
        raise RuntimeError("TURSO_DATABASE_URL is required.")

    parsed = urlparse(turso_url)
    if parsed.scheme != "libsql":
        raise RuntimeError("TURSO_DATABASE_URL must start with libsql://")

    return f"sqlite+{turso_url}?secure=true"


def turso_engine_options():
    token = os.getenv("TURSO_AUTH_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TURSO_AUTH_TOKEN is required.")
    return {"connect_args": {"auth_token": token}}


class Config:
    SECRET_KEY = ""
    JWT_SECRET_KEY = ""
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(seconds=2592000)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    CORS_ENABLED = bool_from_env("CORS_ENABLED", default=True)
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "https://amitaibenshalom.com").strip()
    if CORS_ORIGINS == "*":
        CORS_ORIGINS = "*"
    else:
        CORS_ORIGINS = [
            origin.strip() for origin in CORS_ORIGINS.split(",") if origin.strip()
        ]

    NOTIFICATIONS_ENABLED = bool_from_env("NOTIFICATIONS_ENABLED", default=True)
    ABLY_API_KEY = os.getenv("ABLY_API_KEY", "").strip()
    ABLY_TOKEN_TTL_SECONDS = int(os.getenv("ABLY_TOKEN_TTL_SECONDS", "3600"))
    CRON_SECRET = os.getenv("CRON_SECRET", "").strip()
    DEVICE_HEARTBEAT_INTERVAL_SECONDS = 300
    DEVICE_OFFLINE_AFTER_SECONDS = 600
    FIRMWARE_DIRECTORY = str(BASE_DIR / "firmware")
    FIRMWARE_MODELS = {"esp32-c3"}
    PUBLIC_DEMO_DOOR_ID = os.getenv("PUBLIC_DEMO_DOOR_ID", "").strip()
    PUBLIC_DEMO_DOOR_LABEL = os.getenv(
        "PUBLIC_DEMO_DOOR_LABEL", "Amitai's door"
    ).strip()
    GOOGLE_OAUTH_CLIENT_IDS = [
        client_id.strip()
        for client_id in os.getenv(
            "GOOGLE_OAUTH_CLIENT_IDS", DEFAULT_GOOGLE_OAUTH_CLIENT_IDS
        ).split(",")
        if client_id.strip()
    ]
    GOOGLE_WEB_CLIENT_ID = os.getenv(
        "GOOGLE_WEB_CLIENT_ID", DEFAULT_GOOGLE_WEB_CLIENT_ID
    ).strip()
    PASSWORD_RESET_BASE_URL = os.getenv(
        "PASSWORD_RESET_BASE_URL", "https://amitaibenshalom.com/reset-password"
    ).strip()
    PASSWORD_RESET_EXPIRES_MINUTES = int(
        os.getenv("PASSWORD_RESET_EXPIRES_MINUTES", "60")
    )
    MAIL_FROM = os.getenv("MAIL_FROM", "no-reply@amitaibenshalom.com").strip()
    SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
    SMTP_USE_TLS = bool_from_env("SMTP_USE_TLS", default=True)

    @classmethod
    def configure_app(cls, app):
        secret_key = os.getenv("SECRET_KEY", "").strip()
        jwt_secret_key = os.getenv("JWT_SECRET_KEY", secret_key).strip()
        app.config["SECRET_KEY"] = secret_key
        app.config["JWT_SECRET_KEY"] = jwt_secret_key
        app.config["CRON_SECRET"] = (
            os.getenv("CRON_SECRET", "").strip()
            or derive_device_health_cron_secret(secret_key)
        )
        app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(
            seconds=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_SECONDS", "2592000"))
        )
        app.config["SQLALCHEMY_DATABASE_URI"] = turso_database_uri()
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = turso_engine_options()

    @classmethod
    def validate(cls, app):
        if len(app.config["SECRET_KEY"]) < 32:
            raise RuntimeError("SECRET_KEY must be at least 32 characters.")
        if len(app.config["JWT_SECRET_KEY"]) < 32:
            raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters.")
        ably_api_key = app.config.get("ABLY_API_KEY", "")
        if ably_api_key:
            key_name, separator, key_secret = ably_api_key.partition(":")
            if not separator or not key_name or not key_secret:
                raise RuntimeError("ABLY_API_KEY must use the name:secret format.")
        if not 60 <= app.config["ABLY_TOKEN_TTL_SECONDS"] <= 86400:
            raise RuntimeError(
                "ABLY_TOKEN_TTL_SECONDS must be between 60 and 86400."
            )


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key-with-at-least-thirty-two-bytes"
    JWT_SECRET_KEY = "test-jwt-secret-with-at-least-thirty-two-bytes"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    CORS_ORIGINS = "*"
    NOTIFICATIONS_ENABLED = True
    ABLY_API_KEY = ""
    ABLY_TOKEN_TTL_SECONDS = 3600
    CRON_SECRET = "test-cron-secret-with-at-least-thirty-two-bytes"
    DEVICE_HEARTBEAT_INTERVAL_SECONDS = 300
    DEVICE_OFFLINE_AFTER_SECONDS = 600
    PUBLIC_DEMO_DOOR_ID = ""
    PUBLIC_DEMO_DOOR_LABEL = "Amitai's door"
    GOOGLE_OAUTH_CLIENT_IDS = [
        "62060365746-5lrgdhjnr57qg7pbumo4p3durcf9nbl1.apps.googleusercontent.com",
        "62060365746-ht958df0nupek5s87uuthu274qin8s98.apps.googleusercontent.com",
    ]
    GOOGLE_WEB_CLIENT_ID = DEFAULT_GOOGLE_WEB_CLIENT_ID
    PASSWORD_RESET_BASE_URL = "https://amitaibenshalom.com/reset-password"
    PASSWORD_RESET_EXPIRES_MINUTES = 60
    MAIL_FROM = "no-reply@example.com"
    SMTP_HOST = ""
    SMTP_PORT = 587
    SMTP_USERNAME = ""
    SMTP_PASSWORD = ""
    SMTP_USE_TLS = True

    @classmethod
    def configure_app(cls, app):
        app.config["SQLALCHEMY_DATABASE_URI"] = cls.SQLALCHEMY_DATABASE_URI
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = cls.SQLALCHEMY_ENGINE_OPTIONS

    @classmethod
    def validate(cls, app):
        return None


def config_by_name(name=None):
    env_name = name or os.getenv("APP_ENV", "production")
    return {"testing": TestingConfig, "test": TestingConfig}.get(env_name, Config)
