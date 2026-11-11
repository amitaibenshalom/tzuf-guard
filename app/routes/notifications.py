import base64
import hashlib
from urllib.parse import urlparse
from sqlalchemy.dialects.sqlite import insert
from cryptography.hazmat.primitives.asymmetric import ec

from flask import Blueprint, current_app, jsonify, request

from app.errors import ApiError
from app.extensions import db
from app.models import WebPushSubscription, utcnow
from app.services.background import encrypt_payload
from app.services.notifications import notification_service
from app.validation import require_json
from .common import current_user_required

notifications_bp = Blueprint("notifications", __name__)
PUSH_HOSTS = ("fcm.googleapis.com", "push.services.mozilla.com", "web.push.apple.com", "notify.windows.com")


@notifications_bp.get("/web-push/config")
def web_push_config():
    public_key = current_app.config.get("VAPID_PUBLIC_KEY", "")
    return jsonify({"enabled": bool(public_key), "public_key": public_key})


def subscription_endpoint(data):
    endpoint = data.get("endpoint", "")
    if not isinstance(endpoint, str) or len(endpoint) > 2048:
        raise ApiError("Invalid browser subscription.", 400, "validation_error")
    try:
        parsed = urlparse(endpoint)
        valid_port = parsed.port in (None, 443)
    except ValueError as error:
        raise ApiError("Invalid browser subscription.", 400, "validation_error") from error
    host = parsed.hostname or ""
    if parsed.scheme != "https" or not valid_port or parsed.username or parsed.password or parsed.fragment or not any(
        host == allowed or host.endswith(f".{allowed}") for allowed in PUSH_HOSTS
    ):
        raise ApiError("Unsupported browser notification service.", 400, "validation_error")
    return endpoint


@notifications_bp.post("/web-push/subscriptions")
@current_user_required
def subscribe(current_user):
    if not current_app.config.get("VAPID_PRIVATE_KEY"):
        raise ApiError("Browser alerts are not configured.", 503, "push_unavailable")
    data = require_json(request)
    endpoint = subscription_endpoint(data)
    keys = data.get("keys")
    try:
        if not isinstance(keys, dict):
            raise ValueError()
        decoded = {}
        for key, size in (("p256dh", 65), ("auth", 16)):
            value = keys[key]
            if not isinstance(value, str) or len(value) > 100:
                raise ValueError()
            decoded[key] = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
            if len(decoded[key]) != size:
                raise ValueError()
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), decoded["p256dh"])
    except (ValueError, KeyError, TypeError) as error:
        raise ApiError("Invalid browser subscription keys.", 400, "validation_error") from error
    endpoint_hash = hashlib.sha256(endpoint.encode()).hexdigest()
    encrypted = encrypt_payload({"endpoint": endpoint, "keys": keys})
    db.session.execute(insert(WebPushSubscription).values(
        endpoint_hash=endpoint_hash, user_id=current_user.id,
        subscription=encrypted, created_at=utcnow(),
    ).on_conflict_do_update(index_elements=["endpoint_hash"], set_={
        "user_id": current_user.id, "subscription": encrypted,
    }))
    db.session.commit()
    return jsonify({"status": "enabled"})


@notifications_bp.delete("/web-push/subscriptions")
@current_user_required
def unsubscribe(current_user):
    endpoint = subscription_endpoint(require_json(request))
    WebPushSubscription.query.filter_by(
        user_id=current_user.id, endpoint_hash=hashlib.sha256(endpoint.encode()).hexdigest()
    ).delete()
    db.session.commit()
    return jsonify({"status": "disabled"})


@notifications_bp.post("/notifications/test")
@current_user_required
def test_notification(current_user):
    if not current_app.config["NOTIFICATIONS_ENABLED"]:
        raise ApiError("Notifications are disabled.", 503, "notifications_disabled")
    notification_service._send_to_users(
        [current_user.id], "Your TzufGuard alerts are ready", "This is a test notification.", {"event": "test"}
    )
    return jsonify({"status": "queued"}), 202
