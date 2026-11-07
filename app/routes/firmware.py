from flask import Blueprint, current_app, make_response, request, send_file

from app.errors import ApiError
from app.models import Door
from app.security import hash_door_token
from app.services.firmware import load_release, version_key


firmware_bp = Blueprint("firmware", __name__)
def authenticated_door():
    token = request.headers.get("X-TzufGuard-Token", "").strip()
    if not 16 <= len(token) <= 255:
        raise ApiError("A valid device token is required.", 403, "firmware_forbidden")
    door = Door.query.filter_by(token_hash=hash_door_token(token)).first()
    if door is None:
        raise ApiError("Device is not registered.", 403, "firmware_forbidden")
    return door


@firmware_bp.get("/<model>")
def get_firmware(model):
    if model not in current_app.config["FIRMWARE_MODELS"]:
        raise ApiError("Firmware model was not found.", 404, "firmware_not_found")
    authenticated_door()

    release = load_release(model)
    if release is None:
        response = make_response("", 204)
        response.headers["Cache-Control"] = "no-store"
        return response

    version = release["version"]
    checksum = release["md5"]
    binary_path = release["binary_path"]
    current_version = request.headers.get("X-ESP32-Version", "").strip()
    current_key = version_key(current_version)
    if current_key is not None and current_key >= version_key(version):
        response = make_response("", 304)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Firmware-Version"] = version
        return response

    response = send_file(
        binary_path,
        mimetype="application/octet-stream",
        conditional=False,
        download_name=binary_path.name,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-MD5"] = checksum
    response.headers["X-Firmware-Version"] = version
    return response
