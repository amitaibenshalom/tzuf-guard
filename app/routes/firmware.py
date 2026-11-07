import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

from flask import Blueprint, current_app, make_response, request, send_file

from app.errors import ApiError
from app.models import Door
from app.security import hash_door_token


firmware_bp = Blueprint("firmware", __name__)
VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
MD5_PATTERN = re.compile(r"^[0-9a-f]{32}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def version_key(value):
    match = VERSION_PATTERN.fullmatch(value or "")
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())


@lru_cache(maxsize=8)
def binary_checksums(path, modified_ns, size):
    del modified_ns, size
    md5_digest = hashlib.md5(usedforsecurity=False)
    sha256_digest = hashlib.sha256()
    with Path(path).open("rb") as firmware_file:
        for chunk in iter(lambda: firmware_file.read(128 * 1024), b""):
            md5_digest.update(chunk)
            sha256_digest.update(chunk)
    return md5_digest.hexdigest(), sha256_digest.hexdigest()


def authenticated_door():
    token = request.headers.get("X-TzufGuard-Token", "").strip()
    if not 16 <= len(token) <= 255:
        raise ApiError("A valid device token is required.", 403, "firmware_forbidden")
    door = Door.query.filter_by(token_hash=hash_door_token(token)).first()
    if door is None:
        raise ApiError("Device is not registered.", 403, "firmware_forbidden")
    return door


def load_release(model):
    firmware_directory = Path(current_app.config["FIRMWARE_DIRECTORY"])
    manifest_path = firmware_directory / f"{model}.json"
    if not manifest_path.is_file():
        return None

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        current_app.logger.error("Invalid firmware manifest %s: %s", manifest_path, exc)
        raise ApiError(
            "Firmware service is temporarily unavailable.",
            503,
            "firmware_unavailable",
        ) from exc

    version = manifest.get("version")
    filename = manifest.get("filename")
    expected_md5 = manifest.get("md5")
    expected_sha256 = manifest.get("sha256")
    expected_size = manifest.get("size")
    if (
        manifest.get("model") != model
        or version_key(version) is None
        or not isinstance(filename, str)
        or Path(filename).name != filename
        or MD5_PATTERN.fullmatch(expected_md5 or "") is None
        or SHA256_PATTERN.fullmatch(expected_sha256 or "") is None
        or not isinstance(expected_size, int)
        or expected_size <= 0
    ):
        raise ApiError(
            "Firmware service is temporarily unavailable.",
            503,
            "firmware_unavailable",
        )

    binary_path = firmware_directory / filename
    if not binary_path.is_file():
        raise ApiError(
            "Firmware service is temporarily unavailable.",
            503,
            "firmware_unavailable",
        )
    stat = binary_path.stat()
    actual_md5, actual_sha256 = binary_checksums(
        str(binary_path), stat.st_mtime_ns, stat.st_size
    )
    if (
        stat.st_size != expected_size
        or actual_md5 != expected_md5
        or actual_sha256 != expected_sha256
    ):
        current_app.logger.error("Firmware checksum mismatch for %s", binary_path)
        raise ApiError(
            "Firmware service is temporarily unavailable.",
            503,
            "firmware_unavailable",
        )
    return version, expected_md5, binary_path


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

    version, checksum, binary_path = release
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
