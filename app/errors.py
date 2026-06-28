from flask import jsonify


class ApiError(Exception):
    def __init__(self, message, status_code=400, code="bad_request"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def error_response(message, status_code=400, code="bad_request", details=None):
    payload = {"error": {"code": code, "message": message}}
    if details:
        payload["error"]["details"] = details
    return jsonify(payload), status_code
