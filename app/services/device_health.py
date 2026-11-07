from app.device_state import as_utc, offline_cutoff
from app.extensions import db
from app.models import Door, utcnow
from app.services.firmware import version_key
from app.services.notifications import notification_service
from app.services.realtime import realtime_service


def record_device_contact(
    door,
    *,
    device_name=None,
    firmware_version=None,
    heartbeat=False,
    received_at=None,
):
    contact_at = as_utc(received_at) or utcnow()
    recovered = door.offline_since is not None
    previous_firmware = door.firmware_version
    had_update_request = door.firmware_update_requested_at is not None

    door.last_seen_at = contact_at
    if heartbeat:
        door.last_heartbeat_at = contact_at
    if device_name:
        door.device_name = device_name
    if firmware_version:
        door.firmware_version = firmware_version
    door.offline_since = None

    target = door.firmware_update_target_version
    if (
        target
        and version_key(firmware_version) is not None
        and version_key(firmware_version) >= version_key(target)
    ):
        door.firmware_update_requested_at = None
        door.firmware_update_target_version = None

    return {
        "recovered": recovered,
        "firmware_changed": bool(
            firmware_version and firmware_version != previous_firmware
        ),
        "update_completed": bool(
            had_update_request and door.firmware_update_requested_at is None
        ),
        "received_at": contact_at,
    }


def publish_contact_transitions(door, transitions):
    if transitions["recovered"]:
        realtime_service.publish_door_health_changed(door, "online")
    if transitions["firmware_changed"] or transitions["update_completed"]:
        realtime_service.publish_door_device_changed(door)


def mark_stale_doors_offline(now=None):
    checked_at = as_utc(now) or utcnow()
    cutoff = offline_cutoff(checked_at)
    stale_ids = [
        door_id
        for (door_id,) in (
            db.session.query(Door.id)
            .filter(
                Door.last_seen_at.isnot(None),
                Door.offline_since.is_(None),
                Door.last_seen_at < cutoff,
            )
            .all()
        )
    ]

    transitioned = []
    for door_id in stale_ids:
        updated = (
            db.session.query(Door)
            .filter(
                Door.id == door_id,
                Door.offline_since.is_(None),
                Door.last_seen_at < cutoff,
            )
            .update({Door.offline_since: checked_at}, synchronize_session=False)
        )
        if not updated:
            continue
        db.session.commit()
        door = db.session.get(Door, door_id)
        transitioned.append(door)
        realtime_service.publish_door_health_changed(door, "offline")
        notification_service.send_sensor_offline(door)

    return transitioned
