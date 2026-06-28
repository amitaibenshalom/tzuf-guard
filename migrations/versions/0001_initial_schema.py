"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "doors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("location", sa.String(length=120), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("last_status", sa.String(length=16), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("battery_mv", sa.Integer(), nullable=True),
        sa.Column("device_name", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_doors_token_hash"), "doors", ["token_hash"], unique=True)
    op.create_index(op.f("ix_doors_user_id"), "doors", ["user_id"], unique=False)

    op.create_table(
        "door_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("door_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("battery_mv", sa.Integer(), nullable=True),
        sa.Column("device_name", sa.String(length=120), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["door_id"], ["doors.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_door_events_door_id"), "door_events", ["door_id"], unique=False
    )

    op.create_table(
        "push_devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("push_token", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "push_token", name="uq_user_push_token"),
    )
    op.create_index(
        op.f("ix_push_devices_user_id"), "push_devices", ["user_id"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_push_devices_user_id"), table_name="push_devices")
    op.drop_table("push_devices")
    op.drop_index(op.f("ix_door_events_door_id"), table_name="door_events")
    op.drop_table("door_events")
    op.drop_index(op.f("ix_doors_user_id"), table_name="doors")
    op.drop_index(op.f("ix_doors_token_hash"), table_name="doors")
    op.drop_table("doors")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
