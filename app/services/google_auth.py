from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token


def verify_google_id_token(raw_id_token, audiences):
    last_error = None
    request = google_requests.Request()

    for audience in audiences:
        try:
            return google_id_token.verify_oauth2_token(
                raw_id_token,
                request,
                audience,
            )
        except (GoogleAuthError, ValueError) as exc:
            last_error = exc

    raise ValueError("Google token verification failed.") from last_error
