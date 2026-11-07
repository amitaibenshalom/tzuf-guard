from datetime import datetime, timedelta, timezone

from flask import current_app


def as_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def offline_cutoff(now=None):
    reference = as_utc(now) or datetime.now(timezone.utc)
    return reference - timedelta(
        seconds=current_app.config["DEVICE_OFFLINE_AFTER_SECONDS"]
    )


def door_is_online(door, now=None):
    seen_at = as_utc(door.last_seen_at)
    if seen_at is None or door.offline_since is not None:
        return False
    return seen_at >= offline_cutoff(now)
