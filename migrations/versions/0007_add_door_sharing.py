"""add door memberships and invitations

Revision ID: 0007_door_sharing
Revises: 0006_device_health_firmware
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa


revision = "0007_door_sharing"
down_revision = "0006_device_health_firmware"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "door_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("door_id", sa.Integer(), sa.ForeignKey("doors.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("notifications_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("door_id", "user_id", name="uq_door_membership_user"),
    )
    op.create_index("ix_door_memberships_door_id", "door_memberships", ["door_id"])
    op.create_index("ix_door_memberships_user_id", "door_memberships", ["user_id"])

    op.create_table(
        "door_invitations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("door_id", sa.Integer(), sa.ForeignKey("doors.id"), nullable=False),
        sa.Column("invited_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("door_id", "email", name="uq_door_invitation_email"),
    )
    op.create_index("ix_door_invitations_door_id", "door_invitations", ["door_id"])
    op.create_index("ix_door_invitations_email", "door_invitations", ["email"])
    op.create_index(
        "ix_door_invitations_invited_by_user_id",
        "door_invitations",
        ["invited_by_user_id"],
    )
    op.create_index(
        "ix_door_invitations_token_hash",
        "door_invitations",
        ["token_hash"],
        unique=True,
    )


def downgrade():
    op.drop_index("ix_door_invitations_token_hash", table_name="door_invitations")
    op.drop_index("ix_door_invitations_invited_by_user_id", table_name="door_invitations")
    op.drop_index("ix_door_invitations_email", table_name="door_invitations")
    op.drop_index("ix_door_invitations_door_id", table_name="door_invitations")
    op.drop_table("door_invitations")
    op.drop_index("ix_door_memberships_user_id", table_name="door_memberships")
    op.drop_index("ix_door_memberships_door_id", table_name="door_memberships")
    op.drop_table("door_memberships")
