from flask import Blueprint, current_app, jsonify, request

from app.errors import ApiError
from app.extensions import db
from app.models import Door
from app.security import hash_door_token
from app.serializers import door_event_to_dict, door_to_dict
from app.services.device_health import (
    publish_contact_transitions,
    record_device_contact,
)
from app.services.doors import update_door_status
from app.services.firmware import version_key
from app.validation import require_json, string_field, validate_status

device_status_bp = Blueprint("device_status", __name__)


@device_status_bp.post("/door-status")
def door_status():
    data = require_json(request)
    token = string_field(data, "token", min_length=16, max_length=255)
    status = validate_status(string_field(data, "status", max_length=16))
    device_name = string_field(data, "device", required=False, max_length=120)
    firmware_version = string_field(
        data, "firmware_version", required=False, max_length=32
    )
    if firmware_version and version_key(firmware_version) is None:
        raise ApiError(
            "firmware_version must use MAJOR.MINOR.PATCH format.",
            400,
            "validation_error",
        )

    door, event, status_changed = update_door_status(
        token=token,
        status=status,
        device_name=device_name,
        firmware_version=firmware_version,
    )
    return jsonify(
        {
            "door": door_to_dict(door),
            "event": door_event_to_dict(event) if event else None,
            "status_changed": status_changed,
        }
    )
@device_status_bp.post("/device/heartbeat")
def device_heartbeat():
    data = require_json(request)
    token = string_field(data, "token", min_length=16, max_length=255)
    device_name = string_field(data, "device", required=False, max_length=120)
    firmware_version = string_field(data, "firmware_version", max_length=32)
    if version_key(firmware_version) is None:
        raise ApiError(
            "firmware_version must use MAJOR.MINOR.PATCH format.",
            400,
            "validation_error",
        )

    door = Door.query.filter_by(token_hash=hash_door_token(token)).first()
    if door is None:
        raise ApiError("Unknown door token.", 404, "unknown_door_token")

    transitions = record_device_contact(
        door,
        device_name=device_name,
        firmware_version=firmware_version,
        heartbeat=True,
    )
    db.session.commit()
    publish_contact_transitions(door, transitions)

    update_requested = bool(
        door.firmware_update_requested_at
        and door.firmware_update_target_version
        and version_key(firmware_version) < version_key(
            door.firmware_update_target_version
        )
    )
    return jsonify(
        {
            "door": door_to_dict(door),
            "firmware_update_requested": update_requested,
            "firmware_update_target_version": (
                door.firmware_update_target_version if update_requested else None
            ),
            "next_heartbeat_seconds": current_app.config[
                "DEVICE_HEARTBEAT_INTERVAL_SECONDS"
            ],
        }
    )
