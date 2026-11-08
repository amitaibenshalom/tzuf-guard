import logging

import requests
from flask import current_app

from app.extensions import db
from app.models import PushDevice

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


class NotificationService:
    def send_door_status_changed(self, door, previous_status):
        if not current_app.config["NOTIFICATIONS_ENABLED"]:
            return

        recipients = []
        if door.notifications_enabled:
            recipients.append(door.user_id)
        recipients.extend(
            membership.user_id
            for membership in door.memberships
            if membership.notifications_enabled
        )
        location = f" in {door.location}" if door.location else ""
        if door.last_status == "opened":
            title = f"🚨 {door.name} opened!"
            body = f"🚪 Someone opened {door.name}{location}."
        else:
            title = f"✅ {door.name} closed"
            body = f"🔒 {door.name}{location} is now closed."

        self._send_to_users(
            recipients,
            title,
            body,
            {
                "door_id": str(door.id),
                "status": door.last_status,
                "previous_status": previous_status or "",
            },
        )

    def send_sensor_offline(self, door):
        if not current_app.config["NOTIFICATIONS_ENABLED"]:
            return

        recipients = []
        if door.notifications_enabled:
            recipients.append(door.user_id)
        recipients.extend(
            membership.user_id
            for membership in door.memberships
            if membership.notifications_enabled
        )
        location = f" in {door.location}" if door.location else ""
        self._send_to_users(
            recipients,
            f"{door.name} sensor is offline",
            f"No signal has been received from {door.name}{location} for 10 minutes.",
            {"door_id": str(door.id), "event": "sensor_offline"},
        )

    def _send_to_users(self, user_ids, title, body, data):
        for user_id in set(user_ids):
            devices = PushDevice.query.filter_by(user_id=user_id).all()
            for device in devices:
                self.send_push(device, title, body, data)

    def send_push(self, push_device, title, body, data=None):
        token = push_device.push_token

        if not token or not token.startswith("ExponentPushToken["):
            logger.warning("Skipping invalid Expo push token id=%s", push_device.id)
            return

        payload = {
            "to": token,
            "title": title,
            "body": body,
            "data": data or {},
            "sound": "default",
            "priority": "high",
        }

        try:
            response = requests.post(
                EXPO_PUSH_URL,
                json=payload,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=10,
            )
            response.raise_for_status()
            result = response.json()

            ticket = result.get("data", {})
            if ticket.get("status") == "error":
                logger.warning(
                    "Expo push failed token_id=%s details=%s",
                    push_device.id,
                    ticket,
                )
                if ticket.get("details", {}).get("error") == "DeviceNotRegistered":
                    db.session.delete(push_device)
                    db.session.commit()
                return

            logger.info("Expo push sent token_id=%s ticket=%s", push_device.id, ticket)

        except requests.RequestException:
            logger.exception("Expo push request failed token_id=%s", push_device.id)


notification_service = NotificationService()
