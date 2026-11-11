import logging
import json

import requests
from flask import current_app

from app.extensions import db
from app.models import PushDevice
from app.serializers import isoformat

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
                "status_changed_at": isoformat(door.status_changed_at),
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
            defer=True,
        )

    def _send_to_users(self, user_ids, title, body, data, defer=False):
        from app.services.background import create_job, enabled, process_job, publish_job
        if enabled():
            from uuid import uuid4
            for user_id in set(user_ids):
                job = create_job(
                    "notification", {"title": title, "body": body, "data": data or {}},
                    key=f"notification:{uuid4().hex}", user_id=user_id,
                    door_id=int(data["door_id"]) if data and data.get("door_id") else None,
                )
                if defer:
                    continue
                db.session.commit()
                try:
                    process_job(job.id)
                except Exception:
                    logger.warning("Notification retry queued job_id=%s", job.id)
                    publish_job(job)
            if defer:
                db.session.commit()
            return
        for user_id in set(user_ids):
            devices = PushDevice.query.filter_by(user_id=user_id).all()
            for device in devices:
                self.send_push(device, title, body, data)

    def deliver_job(self, job, payload):
        from app.services.background import decrypt_payload, encrypt_payload
        from app.models import WebPushSubscription
        from pywebpush import WebPushException, webpush

        if not current_app.config["NOTIFICATIONS_ENABLED"] or job.user is None:
            return
        if job.door_id:
            door = job.door
            if door is None:
                return
            preference = door if door.user_id == job.user_id else next(
                (item for item in door.memberships if item.user_id == job.user_id), None
            )
            if preference is None or not preference.notifications_enabled:
                return
            opening = payload.get("data", {}).get("status_changed_at")
            if opening and opening != isoformat(door.status_changed_at):
                return
            if payload.get("data", {}).get("event") == "sensor_offline":
                from app.device_state import door_is_online
                if door_is_online(door):
                    return

        delivered = payload.setdefault("delivered", [])
        failed = False
        for device in PushDevice.query.filter_by(user_id=job.user_id).all():
            delivery_key = f"expo:{device.id}"
            if delivery_key in delivered:
                continue
            if self.send_push(device, payload["title"], payload["body"], payload.get("data")):
                delivered.append(delivery_key)
                job.payload = encrypt_payload(payload)
                db.session.commit()
            else:
                failed = True

        for subscription in WebPushSubscription.query.filter_by(user_id=job.user_id).all():
            delivery_key = f"web:{subscription.id}"
            if delivery_key in delivered:
                continue
            try:
                webpush(
                    subscription_info=decrypt_payload(subscription.subscription),
                    data=json.dumps({
                        "title": payload["title"], "body": payload["body"],
                        "data": payload.get("data", {}), "tag": job.id,
                    }),
                    vapid_private_key=current_app.config["VAPID_PRIVATE_KEY"],
                    vapid_claims={"sub": current_app.config["VAPID_SUBJECT"]},
                    ttl=300, timeout=8,
                )
            except WebPushException as error:
                if error.response is not None and error.response.status_code in (404, 410):
                    db.session.delete(subscription)
                else:
                    failed = True
                    continue
            delivered.append(delivery_key)
            job.payload = encrypt_payload(payload)
            db.session.commit()
        if failed:
            raise RuntimeError("Some notification deliveries failed")

    def send_push(self, push_device, title, body, data=None):
        token = push_device.push_token

        if not token or not token.startswith(("ExponentPushToken[", "ExpoPushToken[")):
            logger.warning("Skipping invalid Expo push token id=%s", push_device.id)
            return True

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
                    return True
                return False

            logger.info("Expo push sent token_id=%s ticket=%s", push_device.id, ticket)
            return True

        except requests.RequestException:
            logger.exception("Expo push request failed token_id=%s", push_device.id)
            return False


notification_service = NotificationService()
