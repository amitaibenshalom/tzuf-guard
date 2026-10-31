from flask import Blueprint, current_app, jsonify

from app.extensions import db
from app.models import Door


public_demo_bp = Blueprint("public_demo", __name__)


def demo_response(available=False, status=None):
    response = jsonify(
        {
            "available": available,
            "label": current_app.config["PUBLIC_DEMO_DOOR_LABEL"],
            "status": status,
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
    return demo_response(available=True, status=status)
