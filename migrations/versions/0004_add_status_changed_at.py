"""add door status changed timestamp

Revision ID: 0004_add_status_changed_at
Revises: 0003_remove_battery_fields
Create Date: 2026-10-31
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_add_status_changed_at"
down_revision = "0003_remove_battery_fields"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "doors",
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE doors
        SET status_changed_at = COALESCE(
            (
                SELECT MAX(door_events.received_at)
                FROM door_events
                WHERE door_events.door_id = doors.id
            ),
            last_seen_at
        )
        WHERE last_status IS NOT NULL
        """
    )


def downgrade():
    op.drop_column("doors", "status_changed_at")
