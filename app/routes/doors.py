from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from app.errors import ApiError
from app.extensions import db
from app.models import Door
from app.security import hash_door_token
from app.serializers import door_to_dict
from app.services.doors import create_door_for_user
from app.validation import require_json, string_field
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
    token = string_field(data, "token", min_length=16, max_length=255)
    location = string_field(data, "location", required=False, max_length=120)

    door = create_door_for_user(current_user, name, token, location)
    return jsonify({"door": door_to_dict(door)}), 201


@doors_bp.get("")
@current_user_required
def list_doors(current_user):
    doors = Door.query.filter_by(user_id=current_user.id).order_by(Door.created_at).all()
    return jsonify({"doors": [door_to_dict(door) for door in doors]})


@doors_bp.get("/<int:door_id>")
@current_user_required
def get_door(current_user, door_id):
    door = get_owned_door_or_404(current_user, door_id)
    return jsonify({"door": door_to_dict(door, include_events=True)})


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
