import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

from flask import current_app

from app.errors import ApiError


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
    return {
        "version": version,
        "md5": expected_md5,
        "sha256": expected_sha256,
        "size": expected_size,
        "binary_path": binary_path,
    }
