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
    door_memberships = db.relationship(
        "DoorMembership", back_populates="user", cascade="all, delete-orphan"
    )
    sent_door_invitations = db.relationship(
        "DoorInvitation",
        foreign_keys="DoorInvitation.invited_by_user_id",
        back_populates="invited_by",
        cascade="all, delete-orphan",
    )
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
    status_changed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    last_seen_at = db.Column(db.DateTime(timezone=True), nullable=True)
    last_heartbeat_at = db.Column(db.DateTime(timezone=True), nullable=True)
    offline_since = db.Column(db.DateTime(timezone=True), nullable=True)
    device_name = db.Column(db.String(120), nullable=True)
    firmware_version = db.Column(db.String(32), nullable=True)
    firmware_update_requested_at = db.Column(db.DateTime(timezone=True), nullable=True)
    firmware_update_target_version = db.Column(db.String(32), nullable=True)
    notifications_enabled = db.Column(db.Boolean, default=True, nullable=False)
    is_pinned = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship("User", back_populates="doors")
    memberships = db.relationship(
        "DoorMembership", back_populates="door", cascade="all, delete-orphan"
    )
    invitations = db.relationship(
        "DoorInvitation", back_populates="door", cascade="all, delete-orphan"
    )
    events = db.relationship(
        "DoorEvent",
        back_populates="door",
        cascade="all, delete-orphan",
        order_by="DoorEvent.received_at.desc()",
    )


class DoorMembership(db.Model):
    __tablename__ = "door_memberships"
    __table_args__ = (
        UniqueConstraint("door_id", "user_id", name="uq_door_membership_user"),
    )

    id = db.Column(db.Integer, primary_key=True)
    door_id = db.Column(db.Integer, db.ForeignKey("doors.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    notifications_enabled = db.Column(db.Boolean, default=True, nullable=False)
    is_pinned = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    door = db.relationship("Door", back_populates="memberships")
    user = db.relationship("User", back_populates="door_memberships")


class DoorInvitation(db.Model):
    __tablename__ = "door_invitations"
    __table_args__ = (
        UniqueConstraint("door_id", "email", name="uq_door_invitation_email"),
    )

    id = db.Column(db.Integer, primary_key=True)
    door_id = db.Column(db.Integer, db.ForeignKey("doors.id"), nullable=False, index=True)
    invited_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    email = db.Column(db.String(255), nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    accepted_at = db.Column(db.DateTime(timezone=True), nullable=True)
    declined_at = db.Column(db.DateTime(timezone=True), nullable=True)
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    door = db.relationship("Door", back_populates="invitations")
    invited_by = db.relationship(
        "User",
        foreign_keys=[invited_by_user_id],
        back_populates="sent_door_invitations",
    )


class DoorEvent(db.Model):
    __tablename__ = "door_events"

    id = db.Column(db.Integer, primary_key=True)
    door_id = db.Column(db.Integer, db.ForeignKey("doors.id"), nullable=False, index=True)
    status = db.Column(db.String(16), nullable=False)
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
