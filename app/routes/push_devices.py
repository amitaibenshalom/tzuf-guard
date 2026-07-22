from flask import Blueprint, jsonify, request

from app.extensions import db
from app.errors import ApiError
from app.models import PushDevice
from app.serializers import push_device_to_dict
from app.validation import VALID_PUSH_PLATFORMS, require_json, string_field
from .common import current_user_required

push_devices_bp = Blueprint("push_devices", __name__)


@push_devices_bp.post("")
@current_user_required
def register_push_device(current_user):
    data = require_json(request)
    platform = string_field(data, "platform", max_length=32).lower()
    push_token = string_field(data, "push_token", max_length=512)

    if platform not in VALID_PUSH_PLATFORMS:
        raise ApiError("Unsupported push platform.", 400, "invalid_platform")

    push_device = PushDevice.query.filter_by(
        user_id=current_user.id, push_token=push_token
    ).first()
    status_code = 200
    if push_device is None:
        push_device = PushDevice(
            user_id=current_user.id,
            platform=platform,
            push_token=push_token,
        )
        db.session.add(push_device)
        status_code = 201
    else:
        push_device.platform = platform

    db.session.commit()
    return jsonify({"push_device": push_device_to_dict(push_device)}), status_code


@push_devices_bp.delete("")
@current_user_required
def delete_push_device(current_user):
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        raise ApiError("Request body must be a JSON object.", 400, "invalid_json")

    push_token = string_field(
        data,
        "push_token",
        required=False,
        max_length=512,
    )
    if not push_token:
        raise ApiError("push_token is required.", 400, "missing_push_token")

    platform = string_field(
        data,
        "platform",
        required=False,
        max_length=32,
    )
    platform = (platform or "android").lower()

    if platform not in VALID_PUSH_PLATFORMS:
        raise ApiError("Unsupported push platform.", 400, "invalid_platform")

    PushDevice.query.filter_by(
        user_id=current_user.id,
        platform=platform,
        push_token=push_token,
    ).delete()

    db.session.commit()
    return jsonify({"message": "Push device deleted."})
