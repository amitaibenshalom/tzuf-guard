import hmac

from flask import Blueprint, current_app, jsonify, request

from app.errors import ApiError
from app.services.device_health import mark_stale_doors_offline


maintenance_bp = Blueprint("maintenance", __name__)


@maintenance_bp.get("/device-health")
def check_device_health():
    secret = current_app.config.get("CRON_SECRET", "")
    authorization = request.headers.get("Authorization", "")
    if not secret or not hmac.compare_digest(authorization, f"Bearer {secret}"):
        raise ApiError("Cron authentication failed.", 401, "cron_unauthorized")

    offline_doors = mark_stale_doors_offline()
    return jsonify(
        {
            "status": "ok",
            "newly_offline": len(offline_doors),
            "door_ids": [door.id for door in offline_doors],
        }
    )
