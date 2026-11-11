from flask import Blueprint, current_app, jsonify

from app.errors import ApiError
from app.services.notifications import notification_service
from .common import current_user_required

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.post("/notifications/test")
@current_user_required
def test_notification(current_user):
    if not current_app.config["NOTIFICATIONS_ENABLED"]:
        raise ApiError("Notifications are disabled.", 503, "notifications_disabled")
    notification_service._send_to_users(
        [current_user.id],
        "Your TzufGuard alerts are ready",
        "This is a test notification.",
        {"event": "test"},
    )
    return jsonify({"status": "queued"}), 202
