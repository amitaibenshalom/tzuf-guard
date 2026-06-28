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
