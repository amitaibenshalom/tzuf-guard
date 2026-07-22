import pytest
import requests

from app import create_app
from app.extensions import db
from app.models import Door, DoorEvent, PushDevice
from app.services.notifications import NotificationService

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


def test_delete_push_device_by_token(client, auth, app):
    client.post(
        "/api/push-devices",
        headers=auth,
        json={"platform": "android", "push_token": "push-token-123"},
    )
    client.post(
        "/api/push-devices",
        headers=auth,
        json={"platform": "ios", "push_token": "push-token-123"},
    )

    response = client.delete(
        "/api/push-devices",
        headers=auth,
        json={"push_token": "push-token-123"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"message": "Push device deleted."}

    with app.app_context():
        remaining = PushDevice.query.one()
        assert remaining.platform == "ios"
        assert remaining.push_token == "push-token-123"


def test_delete_push_device_requires_token(client, auth):
    response = client.delete(
        "/api/push-devices",
        headers=auth,
        json={},
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "missing_push_token"


def test_status_change_sends_expo_push(client, auth, monkeypatch):
    sent = []

    class StubResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"status": "ok", "id": "ticket-123"}}

    def fake_post(url, **kwargs):
        sent.append((url, kwargs))
        return StubResponse()

    monkeypatch.setattr("app.services.notifications.requests.post", fake_post)

    client.post(
        "/api/push-devices",
        headers=auth,
        json={
            "platform": "ios",
            "push_token": "ExponentPushToken[valid-token]",
        },
    )
    client.post(
        "/api/doors",
        headers=auth,
        json={"name": "Front Door", "token": "expo-secret-token"},
    )
    response = client.post(
        "/api/door-status",
        json={"token": "expo-secret-token", "status": "opened"},
    )

    assert response.status_code == 200
    assert len(sent) == 1
    url, kwargs = sent[0]
    assert url == "https://exp.host/--/api/v2/push/send"
    assert kwargs["json"]["to"] == "ExponentPushToken[valid-token]"
    assert kwargs["json"]["title"] == "🚨 Front Door opened!"
    assert kwargs["json"]["body"] == "🚪 Someone opened Front Door."
    assert kwargs["json"]["data"] == {
        "door_id": str(response.get_json()["door"]["id"]),
        "status": "opened",
        "previous_status": "",
    }
    assert kwargs["json"]["sound"] == "default"
    assert kwargs["json"]["priority"] == "high"
    assert kwargs["timeout"] == 10


def test_status_change_closed_uses_safe_emoji(client, auth, monkeypatch):
    sent = []

    class StubResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"status": "ok", "id": "ticket-123"}}

    monkeypatch.setattr(
        "app.services.notifications.requests.post",
        lambda url, **kwargs: sent.append((url, kwargs)) or StubResponse(),
    )

    client.post(
        "/api/push-devices",
        headers=auth,
        json={
            "platform": "ios",
            "push_token": "ExponentPushToken[valid-token]",
        },
    )
    client.post(
        "/api/doors",
        headers=auth,
        json={"name": "Front Door", "token": "closed-emoji-token"},
    )
    client.post(
        "/api/door-status",
        json={"token": "closed-emoji-token", "status": "opened"},
    )
    response = client.post(
        "/api/door-status",
        json={"token": "closed-emoji-token", "status": "closed"},
    )

    assert response.status_code == 200
    assert len(sent) == 2
    assert sent[1][1]["json"]["title"] == "✅ Front Door closed"
    assert sent[1][1]["json"]["body"] == "🔒 Front Door is now closed."


def test_status_change_includes_location_when_present(client, auth, monkeypatch):
    sent = []

    class StubResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"status": "ok", "id": "ticket-123"}}

    monkeypatch.setattr(
        "app.services.notifications.requests.post",
        lambda url, **kwargs: sent.append((url, kwargs)) or StubResponse(),
    )

    client.post(
        "/api/push-devices",
        headers=auth,
        json={
            "platform": "ios",
            "push_token": "ExponentPushToken[valid-token]",
        },
    )
    client.post(
        "/api/doors",
        headers=auth,
        json={
            "name": "Front Door",
            "location": "the hallway",
            "token": "location-emoji-token",
        },
    )
    response = client.post(
        "/api/door-status",
        json={"token": "location-emoji-token", "status": "opened"},
    )

    assert response.status_code == 200
    assert sent[0][1]["json"]["body"] == "🚪 Someone opened Front Door in the hallway."


def test_notification_service_skips_invalid_expo_token(app, monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr("app.services.notifications.requests.post", fake_post)

    with app.app_context():
        push_device = PushDevice(
            user_id=1,
            platform="android",
            push_token="not-an-expo-token",
        )
        push_device.id = 42

        NotificationService().send_push(push_device, "Title", "Body")

    assert calls == []


def test_notification_service_deletes_unregistered_device(app, monkeypatch):
    class StubResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": {
                    "status": "error",
                    "message": "Device not registered",
                    "details": {"error": "DeviceNotRegistered"},
                }
            }

    monkeypatch.setattr(
        "app.services.notifications.requests.post", lambda *args, **kwargs: StubResponse()
    )

    with app.app_context():
        user = register_user(app.test_client(), email="pushdelete@example.com").get_json()[
            "user"
        ]
        push_device = PushDevice(
            user_id=user["id"],
            platform="ios",
            push_token="ExponentPushToken[stale-token]",
        )
        db.session.add(push_device)
        db.session.commit()
        push_device_id = push_device.id

        NotificationService().send_push(push_device, "Title", "Body")

        assert db.session.get(PushDevice, push_device_id) is None


def test_notification_service_logs_request_failures(app, monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise requests.Timeout("too slow")

    monkeypatch.setattr("app.services.notifications.requests.post", raise_timeout)

    with app.app_context():
        push_device = PushDevice(
            user_id=1,
            platform="ios",
            push_token="ExponentPushToken[timeout-token]",
        )
        push_device.id = 99

        NotificationService().send_push(push_device, "Title", "Body")
