from flask import Blueprint, jsonify

from app.serializers import user_to_dict
from .common import current_user_required

me_bp = Blueprint("me", __name__)


@me_bp.get("/me")
@current_user_required
def me(current_user):
    return jsonify({"user": user_to_dict(current_user)})
