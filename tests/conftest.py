import pytest
import base64
import hashlib
import time
import jwt

from app import create_app
from app.extensions import db


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def register_user(client, email="user@example.com", password="password123", name="User"):
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "name": name},
    )


def login_user(client, email="user@example.com", password="password123"):
    return client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def qstash_headers(app, path, body="{}", key=None):
    now = int(time.time())
    signature = jwt.encode({
        "iss": "Upstash", "sub": app.config["PUBLIC_APP_URL"] + path,
        "iat": now, "nbf": now - 1, "exp": now + 300,
        "body": base64.urlsafe_b64encode(hashlib.sha256(body.encode()).digest()).decode().rstrip("="),
    }, key or app.config["QSTASH_CURRENT_SIGNING_KEY"], algorithm="HS256")
    return {"Upstash-Signature": signature, "Content-Type": "application/json"}


@pytest.fixture()
def auth(client):
    response = register_user(client)
    token = response.get_json()["access_token"]
    return auth_headers(token)
