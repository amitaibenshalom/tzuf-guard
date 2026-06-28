from .errors import ApiError

VALID_STATUSES = {"opened", "closed"}
VALID_PUSH_PLATFORMS = {"android", "ios", "expo", "web"}


def require_json(request):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Request body must be a JSON object.", 400, "invalid_json")
    return data


def string_field(data, name, required=True, min_length=1, max_length=255):
    value = data.get(name)
    if value is None:
        if required:
            raise ApiError(f"'{name}' is required.", 400, "validation_error")
        return None

    if not isinstance(value, str):
        raise ApiError(f"'{name}' must be a string.", 400, "validation_error")

    value = value.strip()
    if required and len(value) < min_length:
        raise ApiError(f"'{name}' is required.", 400, "validation_error")
    if value and len(value) < min_length:
        raise ApiError(
            f"'{name}' must be at least {min_length} characters.",
            400,
            "validation_error",
        )
    if len(value) > max_length:
        raise ApiError(
            f"'{name}' must be at most {max_length} characters.",
            400,
            "validation_error",
        )
    return value or None


def int_field(data, name, required=False, min_value=None, max_value=None):
    value = data.get(name)
    if value is None:
        if required:
            raise ApiError(f"'{name}' is required.", 400, "validation_error")
        return None

    if not isinstance(value, int) or isinstance(value, bool):
        raise ApiError(f"'{name}' must be an integer.", 400, "validation_error")
    if min_value is not None and value < min_value:
        raise ApiError(
            f"'{name}' must be at least {min_value}.", 400, "validation_error"
        )
    if max_value is not None and value > max_value:
        raise ApiError(
            f"'{name}' must be at most {max_value}.", 400, "validation_error"
        )
    return value


def validate_status(status):
    if status not in VALID_STATUSES:
        raise ApiError(
            "'status' must be either 'opened' or 'closed'.",
            400,
            "invalid_status",
        )
    return status
