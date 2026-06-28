from sqlalchemy.exc import IntegrityError

from app.errors import ApiError
from app.extensions import db
from app.models import Door, DoorEvent, utcnow
from app.security import hash_door_token
from app.services.notifications import notification_service


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


def update_door_status(token, status, battery_mv=None, device_name=None):
    door = Door.query.filter_by(token_hash=hash_door_token(token)).first()
    if door is None:
        raise ApiError("Unknown door token.", 404, "unknown_door_token")

    previous_status = door.last_status
    status_changed = previous_status != status
    received_at = utcnow()

    door.last_status = status
    door.last_seen_at = received_at
    door.battery_mv = battery_mv
    door.device_name = device_name

    event = DoorEvent(
        door=door,
        status=status,
        battery_mv=battery_mv,
        device_name=device_name,
        received_at=received_at,
    )
    db.session.add(event)
    db.session.commit()

    if status_changed:
        notification_service.send_door_status_changed(door, previous_status)

    return door, event, status_changed
