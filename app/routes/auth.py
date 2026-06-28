from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token
from sqlalchemy.exc import IntegrityError

from app.errors import ApiError
from app.extensions import db
from app.models import User
from app.security import normalize_email
from app.serializers import user_to_dict
from app.validation import require_json, string_field

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/register")
def register():
    data = require_json(request)
    email = normalize_email(string_field(data, "email", max_length=255))
    password = string_field(data, "password", min_length=8, max_length=128)
    name = string_field(data, "name", required=False, max_length=120)

    user = User(email=email, name=name)
    user.set_password(password)
    db.session.add(user)

    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ApiError("Email is already registered.", 409, "duplicate_email") from exc

    token = create_access_token(identity=str(user.id))
    return jsonify({"user": user_to_dict(user), "access_token": token}), 201


@auth_bp.post("/login")
def login():
    data = require_json(request)
    email = normalize_email(string_field(data, "email", max_length=255))
    password = string_field(data, "password", max_length=128)

    user = User.query.filter_by(email=email).first()
    if user is None or not user.check_password(password):
        raise ApiError("Invalid email or password.", 401, "invalid_credentials")

    token = create_access_token(identity=str(user.id))
    return jsonify({"user": user_to_dict(user), "access_token": token})
