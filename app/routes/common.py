from functools import wraps

from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.errors import ApiError
from app.extensions import db
from app.models import Door, DoorMembership, User


def current_user_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user = db.session.get(User, int(get_jwt_identity()))
        if user is None:
            raise ApiError("Authenticated user was not found.", 401, "unauthorized")
        return fn(user, *args, **kwargs)

    return wrapper


def get_door_access_or_404(user, door_id):
    door = Door.query.filter_by(id=door_id).first()
    if door is None:
        raise ApiError("Door was not found.", 404, "door_not_found")
    if door.user_id == user.id:
        return door, None
    membership = DoorMembership.query.filter_by(
        door_id=door.id,
        user_id=user.id,
    ).first()
    if membership is None:
        raise ApiError("Door was not found.", 404, "door_not_found")
    return door, membership


def require_door_owner(user, door):
    if door.user_id != user.id:
        raise ApiError(
            "Only the door owner can do that.",
            403,
            "door_owner_required",
        )
    return door
