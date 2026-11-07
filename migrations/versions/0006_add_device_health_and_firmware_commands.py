"""add device health and firmware command state

Revision ID: 0006_device_health_firmware
Revises: 0005_add_door_preferences
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa


revision = "0006_device_health_firmware"
down_revision = "0005_add_door_preferences"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "doors",
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "doors",
        sa.Column("offline_since", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "doors",
        sa.Column("firmware_version", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "doors",
        sa.Column(
            "firmware_update_requested_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "doors",
        sa.Column("firmware_update_target_version", sa.String(length=32), nullable=True),
    )
    op.create_index("ix_doors_last_seen_at", "doors", ["last_seen_at"])


def downgrade():
    op.drop_index("ix_doors_last_seen_at", table_name="doors")
    op.drop_column("doors", "firmware_update_target_version")
    op.drop_column("doors", "firmware_update_requested_at")
    op.drop_column("doors", "firmware_version")
    op.drop_column("doors", "offline_since")
    op.drop_column("doors", "last_heartbeat_at")
