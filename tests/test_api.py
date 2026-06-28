import pytest

from app import create_app
from app.models import Door, DoorEvent, PushDevice

from .conftest import auth_headers, login_user, register_user


def test_production_config_requires_turso(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "secret-key-with-at-least-thirty-two-bytes")
    monkeypatch.setenv("JWT_SECRET_KEY", "jwt-secret-with-at-least-thirty-two-bytes")
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="TURSO_DATABASE_URL"):
        create_app()


def test_homepage(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"TzufGuard" in response.data


def test_health_and_cors(client):
    response = client.get(
        "/api/health",
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"


def test_user_registration(client):
    response = register_user(client, email="new@example.com")

    assert response.status_code == 201
    body = response.get_json()
    assert body["user"]["email"] == "new@example.com"
    assert "access_token" in body
    assert "password_hash" not in body["user"]


def test_duplicate_user_email(client):
    register_user(client, email="dupe@example.com")
    response = register_user(client, email="dupe@example.com")

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "duplicate_email"


def test_login_success_and_failure(client):
    register_user(client, email="login@example.com", password="password123")

    success = login_user(client, email="login@example.com", password="password123")
    failure = login_user(client, email="login@example.com", password="wrongpass")

    assert success.status_code == 200
    assert "access_token" in success.get_json()
    assert failure.status_code == 401


def test_current_user_endpoint(client):
    response = register_user(client, email="me@example.com")
    headers = auth_headers(response.get_json()["access_token"])

    me = client.get("/api/me", headers=headers)

    assert me.status_code == 200
    assert me.get_json()["user"]["email"] == "me@example.com"


def test_create_door(client, auth):
    response = client.post(
        "/api/doors",
        headers=auth,
        json={"name": "Front Door", "token": "front-door-secret-token"},
    )

    assert response.status_code == 201
    door = response.get_json()["door"]
    assert door["name"] == "Front Door"
    assert "token" not in door
    assert "token_hash" not in door


def test_duplicate_door_token(client, auth):
    payload = {"name": "Front Door", "token": "shared-secret-token"}
    client.post("/api/doors", headers=auth, json=payload)
    response = client.post(
        "/api/doors",
        headers=auth,
        json={"name": "Back Door", "token": "shared-secret-token"},
    )

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "duplicate_token"


def test_users_cannot_access_another_users_door(client):
    first = register_user(client, email="first@example.com").get_json()["access_token"]
    second = register_user(client, email="second@example.com").get_json()["access_token"]

    created = client.post(
        "/api/doors",
        headers=auth_headers(first),
        json={"name": "Private Door", "token": "private-secret-token"},
    )
    door_id = created.get_json()["door"]["id"]

    response = client.get(f"/api/doors/{door_id}", headers=auth_headers(second))

    assert response.status_code == 404


def test_esp32_status_update_success(client, auth):
    client.post(
        "/api/doors",
        headers=auth,
        json={"name": "Front Door", "token": "esp32-secret-token"},
    )

    response = client.post(
        "/api/door-status",
        json={
            "token": "esp32-secret-token",
            "status": "opened",
            "battery_mv": 3100,
            "device": "TzufGuard-ABC123",
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["door"]["last_status"] == "opened"
    assert body["event"]["status"] == "opened"
    assert body["status_changed"] is True


def test_unknown_device_token(client):
    response = client.post(
        "/api/door-status",
        json={"token": "unknown-secret-token", "status": "closed"},
    )

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "unknown_door_token"


def test_invalid_status(client, auth):
    client.post(
        "/api/doors",
        headers=auth,
        json={"name": "Front Door", "token": "invalid-status-token"},
    )

    response = client.post(
        "/api/door-status",
        json={"token": "invalid-status-token", "status": "ajar"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_status"


def test_event_history_creation(client, auth, app):
    client.post(
        "/api/doors",
        headers=auth,
        json={"name": "Front Door", "token": "history-secret-token"},
    )

    client.post(
        "/api/door-status",
        json={"token": "history-secret-token", "status": "closed"},
    )
    client.post(
        "/api/door-status",
        json={"token": "history-secret-token", "status": "opened"},
    )

    with app.app_context():
        door = Door.query.one()
        assert DoorEvent.query.filter_by(door_id=door.id).count() == 2


def test_no_duplicate_push_notification_when_status_unchanged(
    client, auth, monkeypatch
):
    calls = []

    class StubNotificationService:
        def send_door_status_changed(self, door, previous_status):
            calls.append((door.id, previous_status, door.last_status))

    monkeypatch.setattr(
        "app.services.doors.notification_service", StubNotificationService()
    )

    client.post(
        "/api/doors",
        headers=auth,
        json={"name": "Front Door", "token": "notify-secret-token"},
    )
    client.post(
        "/api/door-status",
        json={"token": "notify-secret-token", "status": "opened"},
    )
    client.post(
        "/api/door-status",
        json={"token": "notify-secret-token", "status": "opened"},
    )

    assert len(calls) == 1


def test_push_token_registration(client, auth, app):
    response = client.post(
        "/api/push-devices",
        headers=auth,
        json={"platform": "android", "push_token": "push-token-123"},
    )

    assert response.status_code == 201
    assert response.get_json()["push_device"]["platform"] == "android"

    with app.app_context():
        assert PushDevice.query.count() == 1
