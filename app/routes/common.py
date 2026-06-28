from functools import wraps

from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.errors import ApiError
from app.extensions import db
from app.models import User


def current_user_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user = db.session.get(User, int(get_jwt_identity()))
        if user is None:
            raise ApiError("Authenticated user was not found.", 401, "unauthorized")
        return fn(user, *args, **kwargs)

    return wrapper
