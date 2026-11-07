"""add per-door notification and pin preferences

Revision ID: 0005_add_door_preferences
Revises: 0004_add_status_changed_at
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_add_door_preferences"
down_revision = "0004_add_status_changed_at"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "doors",
        sa.Column(
            "notifications_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "doors",
        sa.Column(
            "is_pinned",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column("doors", "is_pinned")
    op.drop_column("doors", "notifications_enabled")
