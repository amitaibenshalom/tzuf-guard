import base64
import hashlib
import json
import logging
import math
from datetime import timedelta
from uuid import uuid4

import requests
from cryptography.fernet import Fernet
from flask import current_app
from sqlalchemy import or_
from sqlalchemy.dialects.sqlite import insert

from app.device_state import as_utc, door_is_online
from app.extensions import db
from app.models import BackgroundJob, DoorInvitation, PasswordResetToken, User, utcnow
from app.security import hash_reset_token
from app.serializers import isoformat

logger = logging.getLogger(__name__)
REMINDER_MINUTES = (0, 2, 5, 15, 30)


def enabled():
    return bool(current_app.config.get("QSTASH_TOKEN"))


def encrypt_payload(payload):
    key = hashlib.sha256((current_app.config["SECRET_KEY"] + ":background-jobs:v1").encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key)).encrypt(json.dumps(payload).encode()).decode()


def decrypt_payload(value):
    key = hashlib.sha256((current_app.config["SECRET_KEY"] + ":background-jobs:v1").encode()).digest()
    return json.loads(Fernet(base64.urlsafe_b64encode(key)).decrypt(value.encode()))


def create_job(kind, payload, *, key, due_at=None, door_id=None, user_id=None):
    existing = BackgroundJob.query.filter_by(deduplication_key=key).first()
    if existing:
        return existing
    due_at = as_utc(due_at) or utcnow()
    db.session.execute(insert(BackgroundJob).values(
        id=uuid4().hex, deduplication_key=key, kind=kind,
        payload=encrypt_payload(payload), due_at=due_at, next_dispatch_at=utcnow(),
        door_id=door_id, user_id=user_id, attempts=0, created_at=utcnow(),
    ).on_conflict_do_nothing(index_elements=["deduplication_key"]))
    return BackgroundJob.query.filter_by(deduplication_key=key).one()


def prepare_reminders(door):
    """Stage reminder changes in the same transaction as a door report/preference."""
    jobs = BackgroundJob.query.filter_by(door_id=door.id, kind="left_open").filter(
        BackgroundJob.completed_at.is_(None)
    ).all()
    if door.last_status != "opened" or not door.status_changed_at:
        for job in jobs:
            job.completed_at = utcnow()
        return

    opening = isoformat(door.status_changed_at)
    preferences = [(door.user_id, door)] + [(item.user_id, item) for item in door.memberships]
    valid_keys = set()
    for user_id, preference in preferences:
        minutes = preference.left_open_minutes or 0
        if not preference.notifications_enabled or not minutes:
            continue
        key = f"left-open:{door.id}:{user_id}:{opening}"
        valid_keys.add(key)
        due_at = as_utc(door.status_changed_at) + timedelta(minutes=minutes)
        job = create_job(
            "left_open", {"opening": opening, "minutes": minutes},
            key=key, due_at=due_at, door_id=door.id, user_id=user_id,
        )
        if job.completed_at is None and job.cancelled_at is not None:
            job.cancelled_at = None
            job.next_dispatch_at = utcnow()
        if job.completed_at is None and as_utc(job.due_at) != due_at:
            job.due_at = due_at
            job.next_dispatch_at = utcnow()
    for job in jobs:
        if job.deduplication_key not in valid_keys:
            job.cancelled_at = utcnow()


def publish_job(job):
    if not enabled() or job.completed_at is not None or job.cancelled_at is not None:
        return False
    now = utcnow()
    destination = f"{current_app.config['PUBLIC_APP_URL']}/api/internal/jobs"
    headers = {
        "Authorization": f"Bearer {current_app.config['QSTASH_TOKEN']}",
        "Content-Type": "application/json",
        "Upstash-Not-Before": str(max(math.ceil(as_utc(job.due_at).timestamp()), int(now.timestamp()))),
        "Upstash-Deduplication-Id": f"{job.id}-{int(as_utc(job.next_dispatch_at).timestamp())}",
        "Upstash-Retries": "6",
        "Upstash-Retry-Delay": "min(300000, 10000 * pow(2, retried))",
        "Upstash-Timeout": "30s",
    }
    try:
        response = requests.post(
            f"{current_app.config['QSTASH_URL']}/v2/publish/{destination}",
            json={"job_id": job.id}, headers=headers, timeout=(3, 8),
        )
        response.raise_for_status()
    except requests.RequestException as error:
        status = error.response.status_code if error.response is not None else None
        logger.warning("Background job publication failed job_id=%s reason=%s status=%s", job.id, type(error).__name__, status)
        job.next_dispatch_at = now + timedelta(minutes=5)
        db.session.commit()
        return False
    # A periodic sweep can recover jobs whose delivery retries were exhausted.
    job.next_dispatch_at = max(as_utc(job.due_at), now) + timedelta(minutes=30)
    db.session.commit()
    return True


def dispatch_pending(limit=20, door_id=None):
    if not enabled():
        return 0
    now = utcnow()
    query = BackgroundJob.query.filter(
        BackgroundJob.completed_at.is_(None),
        BackgroundJob.cancelled_at.is_(None),
        BackgroundJob.next_dispatch_at <= now,
        or_(BackgroundJob.lease_until.is_(None), BackgroundJob.lease_until <= now),
    )
    if door_id is not None:
        query = query.filter_by(door_id=door_id)
    jobs = query.order_by(BackgroundJob.next_dispatch_at, BackgroundJob.id).limit(limit).all()
    published = 0
    for job in jobs:
        if not publish_job(job):
            break
        published += 1
    return published


def process_job(job_id):
    job = db.session.get(BackgroundJob, job_id)
    if job is None or job.completed_at is not None:
        return "completed"
    if job.cancelled_at is not None:
        return "cancelled"
    now = utcnow()
    if as_utc(job.due_at) > now:
        publish_job(job)
        return "rescheduled"
    claimed = BackgroundJob.query.filter(
        BackgroundJob.id == job_id,
        BackgroundJob.completed_at.is_(None),
        or_(BackgroundJob.lease_until.is_(None), BackgroundJob.lease_until <= now),
    ).update({
        BackgroundJob.lease_until: now + timedelta(minutes=2),
        BackgroundJob.attempts: BackgroundJob.attempts + 1,
    }, synchronize_session=False)
    db.session.commit()
    if not claimed:
        raise RuntimeError("Job is already being processed")
    db.session.refresh(job)
    try:
        payload = decrypt_payload(job.payload)
        if job.kind == "left_open":
            deliver_reminder(job, payload)
        elif job.kind == "email":
            deliver_email(job, payload)
        elif job.kind == "notification":
            from app.services.notifications import notification_service
            notification_service.deliver_job(job, payload)
        elif job.kind == "cleanup":
            cleanup_expired_records()
        else:
            raise ValueError("Unsupported job type")
        job.completed_at = utcnow()
        job.lease_until = None
        # Clear sensitive contents promptly after the job finishes.
        job.payload = encrypt_payload({})
        db.session.commit()
    except Exception:
        db.session.rollback()
        job = db.session.get(BackgroundJob, job_id)
        if job:
            job.lease_until = None
            job.next_dispatch_at = utcnow() + timedelta(minutes=5)
            db.session.commit()
        raise
    return "completed"


def deliver_reminder(job, payload):
    door = job.door
    if door is None or job.user is None or door.last_status != "opened":
        return
    if isoformat(door.status_changed_at) != payload["opening"]:
        return
    preference = door if door.user_id == job.user_id else next(
        (item for item in door.memberships if item.user_id == job.user_id), None
    )
    if preference is None or not preference.notifications_enabled or not preference.left_open_minutes:
        return
    if not door_is_online(door):
        # Keep the reminder pending while the last known state is uncertain.
        raise RuntimeError("Waiting for the sensor to reconnect")
    from app.services.notifications import notification_service
    notification_service.deliver_job(job, {
        **payload,
        "title": f"{door.name} is still open",
        "body": f"{door.name} has been open for at least {preference.left_open_minutes} minutes.",
        "data": {"door_id": str(door.id), "event": "door_left_open"},
    })


def queue_email_retry(kind, record, token):
    if not enabled() or not current_app.config.get("SMTP_HOST"):
        return False
    user_id = record.user_id if kind == "password_reset" else record.invited_by_user_id
    job = create_job(
        "email", {"type": kind, "record_id": record.id, "token": token},
        key=f"email:{kind}:{record.id}:{hash_reset_token(token)}",
        user_id=user_id,
        door_id=record.door_id if kind == "invitation" else None,
        due_at=utcnow() + timedelta(seconds=30),
    )
    db.session.commit()
    publish_job(job)
    return True


def deliver_email(job, payload):
    from app.services.email import email_service
    if not current_app.config.get("SMTP_HOST"):
        raise RuntimeError("Email delivery is not configured")
    if payload["type"] == "invitation":
        record = db.session.get(DoorInvitation, payload["record_id"])
        if record is None or record.accepted_at or record.revoked_at or record.declined_at:
            return
        if as_utc(record.expires_at) <= utcnow() or record.token_hash != hash_reset_token(payload["token"]):
            return
        email_service.send_door_invitation(record, payload["token"])
    else:
        record = db.session.get(PasswordResetToken, payload["record_id"])
        if record is None or record.used_at or as_utc(record.expires_at) <= utcnow():
            return
        email_service.send_password_reset(record.user, payload["token"])


def cleanup_expired_records():
    now = utcnow()
    removed = {}
    for model, condition in (
        (BackgroundJob, or_(BackgroundJob.completed_at < now - timedelta(days=7), BackgroundJob.cancelled_at < now - timedelta(days=7))),
        (PasswordResetToken, PasswordResetToken.expires_at < now),
        (DoorInvitation, DoorInvitation.expires_at < now),
    ):
        rows = model.query.filter(condition).limit(200).all()
        for row in rows:
            db.session.delete(row)
        removed[model.__tablename__] = len(rows)
    continuation = None
    if enabled() and any(count == 200 for count in removed.values()):
        continuation = create_job(
            "cleanup", {}, key=f"cleanup:{uuid4().hex}",
            due_at=now + timedelta(seconds=30),
        )
    db.session.commit()
    if continuation:
        publish_job(continuation)
    return removed
