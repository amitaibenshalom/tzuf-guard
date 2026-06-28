import pytest

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


@pytest.fixture()
def auth(client):
    response = register_user(client)
    token = response.get_json()["access_token"]
    return auth_headers(token)
