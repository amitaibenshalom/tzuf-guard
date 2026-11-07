import json
import platform
import re
from datetime import datetime, timezone
from urllib.parse import quote

import jwt
import requests
from flask import current_app

from app.errors import ApiError
from app.device_state import door_is_online
from app.serializers import door_event_to_dict, door_to_dict


DOOR_STATUS_EVENT = "door.status.changed"
DOOR_HEALTH_EVENT = "door.health.changed"
DOOR_DEVICE_EVENT = "door.device.changed"
PUBLIC_DEMO_EVENT = "demo.status.changed"
PUBLIC_DEMO_CHANNEL = "demo:public-door"
ABLY_REST_ENDPOINT = "https://main.realtime.ably.net"


def user_door_channel(user_id):
    return f"doors:user:{int(user_id)}"


class RealtimeService:
    def subscriber_credentials(self, user):
        channel = user_door_channel(user.id)
        return self._subscriber_credentials(channel, f"user-{user.id}")

    def public_demo_credentials(self, client_id):
        if not isinstance(client_id, str) or re.fullmatch(
            r"demo-[a-f0-9]{32}", client_id
        ) is None:
            raise ApiError(
                "A valid realtime client ID is required.",
                400,
                "invalid_realtime_client",
            )
        return self._subscriber_credentials(
            PUBLIC_DEMO_CHANNEL,
            client_id,
        )

    @staticmethod
    def _subscriber_credentials(channel, client_id):
        api_key = current_app.config.get("ABLY_API_KEY", "").strip()
        if not api_key:
            raise ApiError(
                "Realtime updates are not configured.",
                503,
                "realtime_unavailable",
            )

        try:
            key_name, key_secret = api_key.split(":", 1)
        except ValueError as exc:
            current_app.logger.error("ABLY_API_KEY is not in name:secret format.")
            raise ApiError(
                "Realtime updates are temporarily unavailable.",
                503,
                "realtime_unavailable",
            ) from exc

        now = int(datetime.now(timezone.utc).timestamp())
        capability = json.dumps(
            {channel: ["subscribe"]},
            separators=(",", ":"),
        )
        token = jwt.encode(
            {
                "iat": now,
                "exp": now + current_app.config["ABLY_TOKEN_TTL_SECONDS"],
                "x-ably-capability": capability,
                "x-ably-clientId": client_id,
            },
            key_secret,
            algorithm="HS256",
            headers={"kid": key_name, "typ": "JWT"},
        )
        return {"token": token, "channel": channel}

    def publish_door_status_changed(self, door, event):
        return self._publish_door_update(door, DOOR_STATUS_EVENT, event=event)

    def publish_door_health_changed(self, door, health):
        return self._publish_door_update(
            door,
            DOOR_HEALTH_EVENT,
            reason=health,
        )

    def publish_door_device_changed(self, door):
        return self._publish_door_update(door, DOOR_DEVICE_EVENT)

    def _publish_door_update(self, door, event_name, event=None, reason=None):
        api_key = current_app.config.get("ABLY_API_KEY", "").strip()
        if not api_key:
            return False

        payload = {
            "version": 1,
            "door": door_to_dict(door),
            "event": door_event_to_dict(event) if event is not None else None,
            "reason": reason,
        }
        publications = [
            (user_door_channel(door.user_id), event_name, payload)
        ]
        if event_name in {DOOR_STATUS_EVENT, DOOR_HEALTH_EVENT} and self._is_public_demo_door(door.id):
            publications.append(
                (
                    PUBLIC_DEMO_CHANNEL,
                    PUBLIC_DEMO_EVENT,
                    self._public_demo_payload(door),
                )
            )

        try:
            self._publish(api_key, publications)
        except Exception:
            # Turso is the source of truth. A realtime delivery problem must not
            # turn an already-committed sensor update into a failed request.
            current_app.logger.exception(
                "Could not publish Ably %s update for door %s.",
                event_name,
                door.id,
            )
            return False
        return True

    @staticmethod
    def _is_public_demo_door(door_id):
        raw_door_id = current_app.config.get("PUBLIC_DEMO_DOOR_ID", "")
        try:
            return bool(raw_door_id) and int(raw_door_id) == door_id
        except (TypeError, ValueError):
            return False

    def _public_demo_payload(self, door):
        status = door.last_status if door.last_status in {"opened", "closed"} else None
        duration_seconds = None
        if door.status_changed_at is not None:
            changed_at = door.status_changed_at
            if changed_at.tzinfo is None:
                changed_at = changed_at.replace(tzinfo=timezone.utc)
            duration_seconds = max(
                0,
                int((datetime.now(timezone.utc) - changed_at).total_seconds()),
            )
        return {
            "version": 1,
            "available": True,
            "label": current_app.config["PUBLIC_DEMO_DOOR_LABEL"],
            "status": status,
            "duration_seconds": duration_seconds,
            "online": door_is_online(door),
            "last_seen_seconds": self._elapsed_seconds(door.last_seen_at),
        }

    @staticmethod
    def _elapsed_seconds(value):
        if value is None:
            return None
        timestamp = value
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - timestamp).total_seconds()))

    @staticmethod
    def _publish(api_key, publications):
        key_name, key_secret = api_key.split(":", 1)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Ably-Version": "6",
            "Ably-Agent": f"tzufguard-server/1.0 python/{platform.python_version()}",
        }
        for channel_name, event_name, payload in publications:
            encoded_channel = quote(channel_name, safe="")
            response = requests.post(
                f"{ABLY_REST_ENDPOINT}/channels/{encoded_channel}/messages",
                params={"clientType": "server"},
                auth=(key_name, key_secret),
                headers=headers,
                json={"name": event_name, "data": payload},
                timeout=(3, 5),
            )
            response.raise_for_status()


realtime_service = RealtimeService()
