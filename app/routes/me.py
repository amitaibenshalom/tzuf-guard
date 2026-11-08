from flask import Blueprint, jsonify, request

from app.errors import ApiError
from app.extensions import db
from app.security import normalize_email
from app.serializers import user_to_dict
from app.validation import require_json, string_field
from .common import current_user_required

me_bp = Blueprint("me", __name__)


@me_bp.get("/me")
@current_user_required
def me(current_user):
    return jsonify({"user": user_to_dict(current_user)})


@me_bp.delete("/me")
@current_user_required
def delete_me(current_user):
    data = require_json(request)
    confirmation_email = normalize_email(
        string_field(data, "confirmation_email", max_length=255)
    )
    if confirmation_email != current_user.email:
        raise ApiError(
            "Enter your account email to confirm deletion.",
            400,
            "email_confirmation_mismatch",
        )

    db.session.delete(current_user)
    db.session.commit()
    return jsonify({"message": "Account and associated data deleted."})
