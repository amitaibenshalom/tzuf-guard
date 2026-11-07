from flask import Blueprint, jsonify

from app.services.realtime import realtime_service
from .common import current_user_required


realtime_bp = Blueprint("realtime", __name__)


@realtime_bp.post("/token")
@current_user_required
def create_realtime_token(current_user):
    response = jsonify(realtime_service.subscriber_credentials(current_user))
    response.headers["Cache-Control"] = "no-store"
    return response
