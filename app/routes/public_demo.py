from datetime import timezone

from flask import Blueprint, current_app, jsonify

from app.extensions import db
from app.models import Door, utcnow


public_demo_bp = Blueprint("public_demo", __name__)


def elapsed_seconds(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return max(0, int((utcnow() - value).total_seconds()))


def demo_response(available=False, status=None, duration_seconds=None):
    response = jsonify(
        {
            "available": available,
            "label": current_app.config["PUBLIC_DEMO_DOOR_LABEL"],
            "status": status,
            "duration_seconds": duration_seconds,
        }
    )
    response.headers["Cache-Control"] = (
        "public, max-age=0, s-maxage=5, stale-while-revalidate=10"
    )
    return response


@public_demo_bp.get("/demo-door")
def get_demo_door():
    raw_door_id = current_app.config["PUBLIC_DEMO_DOOR_ID"]
    if not raw_door_id:
        return demo_response()

    try:
        door_id = int(raw_door_id)
    except (TypeError, ValueError):
        current_app.logger.error("PUBLIC_DEMO_DOOR_ID must be an integer.")
        return demo_response()

    door = db.session.get(Door, door_id)
    if door is None:
        return demo_response()

    status = door.last_status if door.last_status in {"opened", "closed"} else None
    return demo_response(
        available=True,
        status=status,
        duration_seconds=elapsed_seconds(door.status_changed_at),
    )
