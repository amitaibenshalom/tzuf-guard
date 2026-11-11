from sqlalchemy.exc import IntegrityError

from app.errors import ApiError
from app.extensions import db
from app.models import Door, DoorEvent, utcnow
from app.security import hash_door_token
from app.services.device_health import (
    publish_contact_transitions,
    record_device_contact,
)
from app.services.notifications import notification_service
from app.services.background import dispatch_pending, prepare_reminders
from app.services.realtime import realtime_service


def create_door_for_user(user, name, token, location=None):
    door = Door(
        user_id=user.id,
        name=name,
        location=location,
        token_hash=hash_door_token(token),
    )
    db.session.add(door)

    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ApiError("Door token is already registered.", 409, "duplicate_token") from exc

    return door


def update_door_status(token, status, device_name=None, firmware_version=None):
    door = Door.query.filter_by(token_hash=hash_door_token(token)).first()
    if door is None:
        raise ApiError("Unknown door token.", 404, "unknown_door_token")

    previous_status = door.last_status
    status_changed = previous_status != status
    received_at = utcnow()
    transitions = record_device_contact(
        door,
        device_name=device_name,
        firmware_version=firmware_version,
        received_at=received_at,
    )

    door.last_status = status

    event = None
    if status_changed:
        door.status_changed_at = received_at
        event = DoorEvent(
            door=door,
            status=status,
            device_name=device_name,
            received_at=received_at,
        )
        db.session.add(event)
    prepare_reminders(door)
    db.session.commit()

    if status_changed:
        realtime_service.publish_door_status_changed(door, event)
        notification_service.send_door_status_changed(door, previous_status)
    publish_contact_transitions(door, transitions)
    dispatch_pending(door_id=door.id)

    return door, event, status_changed
