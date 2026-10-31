"""remove battery fields

Revision ID: 0003_remove_battery_fields
Revises: 0002_google_auth_password_reset
Create Date: 2026-10-31
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_remove_battery_fields"
down_revision = "0002_google_auth_password_reset"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column("door_events", "battery_mv")
    op.drop_column("doors", "battery_mv")


def downgrade():
    op.add_column("doors", sa.Column("battery_mv", sa.Integer(), nullable=True))
    op.add_column("door_events", sa.Column("battery_mv", sa.Integer(), nullable=True))
