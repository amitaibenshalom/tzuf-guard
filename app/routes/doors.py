from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from app.errors import ApiError
from app.extensions import db
from app.models import Door, DoorEvent
from app.security import generate_door_token, hash_door_token
from app.serializers import door_event_to_dict, door_to_dict
from app.services.doors import create_door_for_user
from app.validation import boolean_field, require_json, string_field
from .common import current_user_required

doors_bp = Blueprint("doors", __name__)


def get_owned_door_or_404(user, door_id):
    door = Door.query.filter_by(id=door_id, user_id=user.id).first()
    if door is None:
        raise ApiError("Door was not found.", 404, "door_not_found")
    return door


@doors_bp.post("")
@current_user_required
def create_door(current_user):
    data = require_json(request)
    name = string_field(data, "name", max_length=120)
    # Explicit tokens remain supported for older API clients. New clients omit
    # the field and receive a strong, memorable phrase exactly once.
    token = string_field(data, "token", required=False, min_length=16, max_length=255)
    token = token or generate_door_token()
    location = string_field(data, "location", required=False, max_length=120)

    door = create_door_for_user(current_user, name, token, location)
    return jsonify(
        {"door": door_to_dict(door), "provisioning_token": token}
    ), 201


@doors_bp.get("")
@current_user_required
def list_doors(current_user):
    doors = (
        Door.query.filter_by(user_id=current_user.id)
        .order_by(Door.is_pinned.desc(), Door.created_at.asc())
        .all()
    )
    return jsonify({"doors": [door_to_dict(door) for door in doors]})


@doors_bp.get("/<int:door_id>")
@current_user_required
def get_door(current_user, door_id):
    door = get_owned_door_or_404(current_user, door_id)
    events = (
        DoorEvent.query.filter_by(door_id=door.id)
        .order_by(DoorEvent.received_at.desc())
        .limit(100)
        .all()
    )
    return jsonify({"door": door_to_dict(door, events=events)})


@doors_bp.get("/<int:door_id>/events")
@current_user_required
def list_door_events(current_user, door_id):
    door = get_owned_door_or_404(current_user, door_id)
    try:
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(max(int(request.args.get("per_page", 50)), 1), 100)
    except ValueError as exc:
        raise ApiError("Invalid pagination values.", 400, "validation_error") from exc

    query = DoorEvent.query.filter_by(door_id=door.id).order_by(
        DoorEvent.received_at.desc()
    )
    total = query.count()
    events = query.offset((page - 1) * per_page).limit(per_page).all()
    return jsonify(
        {
            "events": [door_event_to_dict(event) for event in events],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "has_more": page * per_page < total,
            },
        }
    )


@doors_bp.patch("/<int:door_id>")
@current_user_required
def patch_door(current_user, door_id):
    door = get_owned_door_or_404(current_user, door_id)
    data = require_json(request)

    if "name" in data:
        door.name = string_field(data, "name", max_length=120)
    if "location" in data:
        door.location = string_field(data, "location", required=False, max_length=120)
    if "token" in data:
        token = string_field(data, "token", min_length=16, max_length=255)
        door.token_hash = hash_door_token(token)
    if "notifications_enabled" in data:
        door.notifications_enabled = boolean_field(data, "notifications_enabled")
    if "is_pinned" in data:
        door.is_pinned = boolean_field(data, "is_pinned")

    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ApiError("Door token is already registered.", 409, "duplicate_token") from exc

    return jsonify({"door": door_to_dict(door)})


@doors_bp.delete("/<int:door_id>")
@current_user_required
def delete_door(current_user, door_id):
    door = get_owned_door_or_404(current_user, door_id)
    db.session.delete(door)
    db.session.commit()
    return jsonify({"message": "Door deleted."})


@doors_bp.post("/<int:door_id>/setup-token")
@current_user_required
def regenerate_setup_token(current_user, door_id):
    door = get_owned_door_or_404(current_user, door_id)
    token = generate_door_token()
    door.token_hash = hash_door_token(token)
    db.session.commit()
    return jsonify(
        {"door": door_to_dict(door), "provisioning_token": token}
    )
