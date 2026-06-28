import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


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

    @classmethod
    def configure_app(cls, app):
        secret_key = os.getenv("SECRET_KEY", "").strip()
        jwt_secret_key = os.getenv("JWT_SECRET_KEY", secret_key).strip()
        app.config["SECRET_KEY"] = secret_key
        app.config["JWT_SECRET_KEY"] = jwt_secret_key
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


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key-with-at-least-thirty-two-bytes"
    JWT_SECRET_KEY = "test-jwt-secret-with-at-least-thirty-two-bytes"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    CORS_ORIGINS = "*"
    NOTIFICATIONS_ENABLED = True

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
