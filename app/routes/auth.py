from datetime import timedelta

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import create_access_token
from sqlalchemy.exc import IntegrityError

from app.errors import ApiError
from app.extensions import db
from app.models import PasswordResetToken, User, utcnow
from app.security import generate_secure_token, hash_reset_token, normalize_email
from app.serializers import user_to_dict
from app.services.email import email_service
from app.services.google_auth import verify_google_id_token
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


@auth_bp.post("/google")
def google_login():
    data = require_json(request)
    raw_id_token = string_field(
        data,
        "id_token",
        required=False,
        max_length=4096,
    )
    if not raw_id_token:
        raise ApiError("Google sign-in failed.", 400, "missing_google_token")

    try:
        claims = verify_google_id_token(
            raw_id_token,
            current_app.config["GOOGLE_OAUTH_CLIENT_IDS"],
        )
    except ValueError as exc:
        raise ApiError("Google sign-in failed.", 401, "invalid_google_token") from exc

    if claims.get("email_verified") is not True:
        raise ApiError(
            "Google email is not verified.",
            401,
            "google_email_unverified",
        )

    google_sub = claims.get("sub")
    email = claims.get("email")
    if not google_sub or not email:
        raise ApiError("Google sign-in failed.", 401, "invalid_google_token")

    email = normalize_email(email)
    name = claims.get("name")

    user = User.query.filter_by(google_sub=google_sub).first()
    if user is None:
        user = User.query.filter_by(email=email).first()
        if user is not None:
            user.google_sub = google_sub
            if not user.name and name:
                user.name = name
        else:
            user = User(
                email=email,
                name=name,
                google_sub=google_sub,
            )
            user.set_password(generate_secure_token())
            db.session.add(user)

    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ApiError("Google sign-in failed.", 401, "invalid_google_token") from exc

    token = create_access_token(identity=str(user.id))
    return jsonify({"user": user_to_dict(user), "access_token": token})


@auth_bp.post("/forgot-password")
def forgot_password():
    data = require_json(request)
    email = normalize_email(string_field(data, "email", max_length=255))
    user = User.query.filter_by(email=email).first()

    if user is not None:
        reset_token = generate_secure_token()
        token_record = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_reset_token(reset_token),
            expires_at=utcnow()
            + timedelta(minutes=current_app.config["PASSWORD_RESET_EXPIRES_MINUTES"]),
        )
        db.session.add(token_record)
        db.session.commit()

        try:
            email_service.send_password_reset(user, reset_token)
        except Exception:
            current_app.logger.exception(
                "Password reset email failed user_id=%s",
                user.id,
            )

    return jsonify({"message": "If that email exists, reset instructions were sent."})


@auth_bp.post("/reset-password")
def reset_password():
    data = require_json(request)
    reset_token = string_field(data, "token", max_length=512)
    password = string_field(data, "password", min_length=8, max_length=128)
    token_hash = hash_reset_token(reset_token)
    token_record = PasswordResetToken.query.filter_by(token_hash=token_hash).first()

    if (
        token_record is None
        or token_record.used_at is not None
        or _is_expired(token_record.expires_at)
    ):
        raise ApiError(
            "Password reset token is invalid or expired.",
            400,
            "invalid_reset_token",
        )

    token_record.user.set_password(password)
    token_record.used_at = utcnow()
    db.session.commit()

    return jsonify({"message": "Password reset successfully."})


def _is_expired(expires_at):
    now = utcnow()
    if expires_at.tzinfo is None:
        now = now.replace(tzinfo=None)
    return expires_at <= now
