from datetime import datetime, timezone

from sqlalchemy import UniqueConstraint
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class User(TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120), nullable=True)
    google_sub = db.Column(db.String(255), nullable=True, unique=True, index=True)

    doors = db.relationship("Door", back_populates="user", cascade="all, delete-orphan")
    push_devices = db.relationship(
        "PushDevice", back_populates="user", cascade="all, delete-orphan"
    )
    password_reset_tokens = db.relationship(
        "PasswordResetToken", back_populates="user", cascade="all, delete-orphan"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Door(TimestampMixin, db.Model):
    __tablename__ = "doors"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(120), nullable=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    last_status = db.Column(db.String(16), nullable=True)
    last_seen_at = db.Column(db.DateTime(timezone=True), nullable=True)
    battery_mv = db.Column(db.Integer, nullable=True)
    device_name = db.Column(db.String(120), nullable=True)

    user = db.relationship("User", back_populates="doors")
    events = db.relationship(
        "DoorEvent",
        back_populates="door",
        cascade="all, delete-orphan",
        order_by="DoorEvent.received_at.desc()",
    )


class DoorEvent(db.Model):
    __tablename__ = "door_events"

    id = db.Column(db.Integer, primary_key=True)
    door_id = db.Column(db.Integer, db.ForeignKey("doors.id"), nullable=False, index=True)
    status = db.Column(db.String(16), nullable=False)
    battery_mv = db.Column(db.Integer, nullable=True)
    device_name = db.Column(db.String(120), nullable=True)
    received_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    door = db.relationship("Door", back_populates="events")


class PushDevice(TimestampMixin, db.Model):
    __tablename__ = "push_devices"
    __table_args__ = (UniqueConstraint("user_id", "push_token", name="uq_user_push_token"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    platform = db.Column(db.String(32), nullable=False)
    push_token = db.Column(db.String(512), nullable=False)

    user = db.relationship("User", back_populates="push_devices")


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    user = db.relationship("User", back_populates="password_reset_tokens")
