import json
from datetime import timedelta

import pytest
import requests

from app.extensions import db
from app.models import BackgroundJob, Door, DoorEvent, DoorMembership, PushDevice, User, utcnow
from app.serializers import isoformat
from app.services.background import decrypt_payload, dispatch_pending, prepare_reminders, process_job
from .conftest import auth_headers, qstash_headers, register_user


def make_open_door(client, auth, app, minutes=5):
    result = client.post("/api/doors", headers=auth, json={"name": "Front door"}).get_json()
    door_id = result["door"]["id"]
    client.patch(f"/api/doors/{door_id}", headers=auth, json={"left_open_minutes": minutes})
    client.post("/api/door-status", json={"token": result["provisioning_token"], "status": "opened"})
    door = db.session.get(Door, door_id)
    return door, result["provisioning_token"]


def make_reminder_due(door):
    door.status_changed_at = utcnow() - timedelta(minutes=6)
    prepare_reminders(door)
    db.session.commit()
    return BackgroundJob.query.filter_by(door_id=door.id, kind="left_open", completed_at=None, cancelled_at=None).one()


def test_qstash_verifies_body_url_and_rotated_key(client, app):
    path = "/api/internal/jobs"
    body = json.dumps({"job_id": "0" * 32})
    valid = qstash_headers(app, path, body)
    assert client.post(path, data=body, headers=valid).status_code == 200
    assert client.post(path, data=body + " ", headers=valid).status_code == 401
    wrong_url = qstash_headers(app, "/api/internal/cleanup", body)
    assert client.post(path, data=body, headers=wrong_url).status_code == 401
    next_key = qstash_headers(app, path, body, app.config["QSTASH_NEXT_SIGNING_KEY"])
    assert client.post(path, data=body, headers=next_key).status_code == 200


def test_reminder_sends_once_and_closed_openings_are_obsolete(client, auth, app, monkeypatch):
    door, token = make_open_door(client, auth, app)
    job = make_reminder_due(door)
    db.session.add(PushDevice(user_id=door.user_id, platform="android", push_token="ExponentPushToken[test]"))
    db.session.commit()
    sent = []
    monkeypatch.setattr("app.services.notifications.notification_service.send_push", lambda *args: sent.append(args) or True)
    assert process_job(job.id) == "completed"
    assert process_job(job.id) == "completed"
    assert len(sent) == 1
    client.post("/api/door-status", json={"token": token, "status": "closed"})
    client.post("/api/door-status", json={"token": token, "status": "opened"})
    pending = BackgroundJob.query.filter_by(door_id=door.id, kind="left_open", completed_at=None).one()
    client.post("/api/door-status", json={"token": token, "status": "closed"})
    sent.clear()
    process_job(pending.id)
    assert sent == []


def test_reminder_preferences_are_personal_and_can_be_reenabled(client, auth, app):
    door, _token = make_open_door(client, auth, app)
    owner_job = BackgroundJob.query.filter_by(door_id=door.id, kind="left_open").one()
    client.patch(f"/api/doors/{door.id}", headers=auth, json={"left_open_minutes": 0})
    assert owner_job.cancelled_at is not None
    client.patch(f"/api/doors/{door.id}", headers=auth, json={"left_open_minutes": 15})
    assert owner_job.cancelled_at is None
    assert decrypt_payload(owner_job.payload)["opening"] == isoformat(door.status_changed_at)
    member_response = register_user(client, "member@example.com").get_json()
    member_id = member_response["user"]["id"]
    db.session.add(DoorMembership(door_id=door.id, user_id=member_id))
    db.session.commit()
    response = client.patch(f"/api/doors/{door.id}", headers=auth_headers(member_response["access_token"]), json={"left_open_minutes": 2})
    assert response.get_json()["door"]["left_open_minutes"] == 2
    assert door.left_open_minutes == 15
    assert BackgroundJob.query.filter_by(door_id=door.id, kind="left_open", user_id=member_id).count() == 1
    assert client.patch(f"/api/doors/{door.id}", headers=auth, json={"left_open_minutes": True}).status_code == 400
    assert client.patch(f"/api/doors/{door.id}", headers=auth, json={"left_open_minutes": 3}).status_code == 400


def test_reminder_defers_offline_and_retries_only_failed_devices(client, auth, app, monkeypatch):
    door, _token = make_open_door(client, auth, app)
    job = make_reminder_due(door)
    door.last_seen_at = utcnow() - timedelta(minutes=11)
    db.session.commit()
    with pytest.raises(RuntimeError, match="reconnect"):
        process_job(job.id)
    assert job.completed_at is None
    assert job.lease_until is None
    door.last_seen_at = utcnow()
    first = PushDevice(user_id=door.user_id, platform="android", push_token="ExponentPushToken[first]")
    second = PushDevice(user_id=door.user_id, platform="android", push_token="ExponentPushToken[second]")
    db.session.add_all([first, second])
    db.session.commit()
    attempts = []
    def send(device, *_args):
        attempts.append(device.id)
        return device.id == first.id
    monkeypatch.setattr("app.services.notifications.notification_service.send_push", send)
    with pytest.raises(RuntimeError, match="deliveries"):
        process_job(job.id)
    assert job.completed_at is None
    monkeypatch.setattr("app.services.notifications.notification_service.send_push", lambda device, *_args: attempts.append(device.id) or True)
    process_job(job.id)
    assert attempts.count(first.id) == 1
    assert attempts.count(second.id) == 2


def test_revoked_member_does_not_receive_reminder(client, auth, app, monkeypatch):
    door, _token = make_open_door(client, auth, app, minutes=0)
    member_response = register_user(client, "removed@example.com").get_json()
    membership = DoorMembership(door_id=door.id, user_id=member_response["user"]["id"], left_open_minutes=5)
    db.session.add(membership)
    db.session.commit()
    job = make_reminder_due(door)
    db.session.delete(membership)
    db.session.commit()
    sent = []
    monkeypatch.setattr("app.services.notifications.notification_service.deliver_job", lambda *args: sent.append(args))
    process_job(job.id)
    assert sent == []


def test_failed_publication_keeps_recoverable_jobs(client, auth, app, monkeypatch):
    app.config["QSTASH_TOKEN"] = "test-token"
    calls = []
    def unavailable(url, **kwargs):
        calls.append((url, kwargs))
        raise requests.ConnectionError("offline")
    monkeypatch.setattr("app.services.background.requests.post", unavailable)
    door, _token = make_open_door(client, auth, app)
    jobs = BackgroundJob.query.filter_by(door_id=door.id, completed_at=None).all()
    assert jobs
    assert calls
    for _url, arguments in calls:
        assert set(arguments["json"]) == {"job_id"}
        # QStash rejects colons in the public deduplication header.
        assert ":" not in arguments["headers"]["Upstash-Deduplication-Id"]
    for job in jobs:
        job.next_dispatch_at = utcnow() - timedelta(seconds=1)
    db.session.commit()
    class Accepted:
        def raise_for_status(self):
            return None
    monkeypatch.setattr("app.services.background.requests.post", lambda *args, **kwargs: Accepted())
    assert dispatch_pending() == len(jobs)


def test_filtered_history_uses_local_boundaries_and_stable_cursor(client, auth, app):
    result = client.post("/api/doors", headers=auth, json={"name": "History"}).get_json()
    door_id = result["door"]["id"]
    from datetime import datetime, timezone
    for hour in (0, 1, 2, 3):
        db.session.add(DoorEvent(door_id=door_id, status="opened", received_at=datetime(2026, 11, 10, hour, tzinfo=timezone.utc)))
    db.session.commit()
    path = f"/api/doors/{door_id}/events"
    query = {"from": "2026-11-10T03:00:00+02:00", "until": "2026-11-10T05:00:00+02:00", "per_page": 1}
    first = client.get(path, headers=auth, query_string=query).get_json()
    assert first["pagination"]["total"] == 2
    db.session.add(DoorEvent(door_id=door_id, status="closed", received_at=datetime(2026, 11, 10, 2, 30, tzinfo=timezone.utc)))
    db.session.commit()
    second = client.get(path, headers=auth, query_string={**query, "cursor": first["pagination"]["next_cursor"]}).get_json()
    assert first["events"][0]["id"] != second["events"][0]["id"]
    assert second["events"][0]["received_at"].startswith("2026-11-10T01:")
    assert second["pagination"]["has_more"] is False
    assert client.get(path, headers=auth, query_string={"from": "invalid"}).status_code == 400
    assert client.get(path, headers=auth, query_string={"from": "2026-11-11", "until": "2026-11-10"}).status_code == 400


def test_failed_invitation_email_is_queued_and_secret_is_encrypted(client, auth, app, monkeypatch):
    app.config.update(QSTASH_TOKEN="test-token", SMTP_HOST="smtp.example.com")
    monkeypatch.setattr("app.services.background.publish_job", lambda job: True)
    def unavailable(*args):
        raise RuntimeError("SMTP unavailable")
    monkeypatch.setattr("app.routes.sharing.email_service.send_door_invitation", unavailable)
    door = client.post("/api/doors", headers=auth, json={"name": "Shared door"}).get_json()["door"]
    response = client.post(f"/api/doors/{door['id']}/invitations", headers=auth, json={"email": "friend@example.com"})
    assert response.status_code == 201
    assert response.get_json()["email_sent"] is False
    assert response.get_json()["email_delivery"] == "queued"
    job = BackgroundJob.query.filter_by(kind="email").one()
    token = response.get_json()["invitation_url"].split("token=")[1]
    assert token not in job.payload
    assert decrypt_payload(job.payload)["token"] == token
    job.due_at = utcnow() - timedelta(seconds=1)
    db.session.commit()
    sent = []
    monkeypatch.setattr("app.services.email.email_service.send_door_invitation", lambda *args: sent.append(args) or True)
    process_job(job.id)
    assert len(sent) == 1
    assert decrypt_payload(job.payload) == {}


def test_threshold_change_cannot_send_from_an_earlier_callback(client, auth, app, monkeypatch):
    door, _token = make_open_door(client, auth, app)
    job = make_reminder_due(door)
    client.patch(f"/api/doors/{door.id}", headers=auth, json={"left_open_minutes": 15})
    published = []
    monkeypatch.setattr("app.services.background.publish_job", lambda item: published.append(item.id) or True)
    assert process_job(job.id) == "rescheduled"
    assert published == [job.id]
    assert job.completed_at is None


def test_browser_subscription_upsert_and_account_deletion(client, auth, app):
    import base64
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    from app.models import WebPushSubscription
    app.config["VAPID_PRIVATE_KEY"] = "test-private-key"
    data = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint",
        "keys": {
            "p256dh": base64.urlsafe_b64encode(ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)).decode().rstrip("="),
            "auth": base64.urlsafe_b64encode(b"y" * 16).decode().rstrip("="),
        },
    }
    path = "/api/web-push/subscriptions"
    assert client.post(path, headers=auth, json=data).status_code == 200
    assert client.post(path, headers=auth, json=data).status_code == 200
    assert WebPushSubscription.query.count() == 1
    assert data["endpoint"] not in WebPushSubscription.query.one().subscription
    assert client.post(path, headers=auth, json={**data, "endpoint": "http://127.0.0.1/private"}).status_code == 400
    door, _ = make_open_door(client, auth, app)
    assert BackgroundJob.query.filter_by(door_id=door.id).count() == 1
    deleted = client.delete("/api/me", headers=auth, json={"confirmation_email": "user@example.com"})
    assert deleted.status_code == 200
    assert WebPushSubscription.query.count() == 0
    assert BackgroundJob.query.count() == 0


def test_cleanup_preserves_active_tokens_and_jobs(client, auth, app):
    from app.models import PasswordResetToken
    from app.services.background import create_job
    user_id = User.query.one().id
    now = utcnow()
    db.session.add_all([
        PasswordResetToken(user_id=user_id, token_hash="expired", expires_at=now - timedelta(hours=1)),
        PasswordResetToken(user_id=user_id, token_hash="active", expires_at=now + timedelta(hours=1)),
    ])
    active = create_job("notification", {}, key="active", user_id=user_id)
    old = create_job("notification", {}, key="completed", user_id=user_id)
    old.completed_at = now - timedelta(days=8)
    cancelled = create_job("notification", {}, key="cancelled", user_id=user_id)
    cancelled.cancelled_at = now - timedelta(days=8)
    db.session.commit()
    path = "/api/internal/cleanup"
    response = client.post(path, data="{}", headers=qstash_headers(app, path))
    assert response.status_code == 200
    assert PasswordResetToken.query.one().token_hash == "active"
    assert BackgroundJob.query.one().id == active.id
