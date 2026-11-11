"""Add personal left-open reminders, durable jobs, and browser subscriptions."""
from alembic import op
import sqlalchemy as sa

revision = "0008_background_jobs"
down_revision = "0007_door_sharing"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("doors", "door_memberships"):
        op.add_column(table, sa.Column("left_open_minutes", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("deduplication_key", sa.String(255), nullable=False, unique=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("door_id", sa.Integer(), sa.ForeignKey("doors.id")),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_dispatch_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_background_jobs_next_dispatch_at", "background_jobs", ["next_dispatch_at"])
    op.create_index("ix_background_jobs_door_id", "background_jobs", ["door_id"])
    op.create_index("ix_background_jobs_user_id", "background_jobs", ["user_id"])
    op.create_index("ix_background_jobs_completed_at", "background_jobs", ["completed_at"])
    op.create_table(
        "web_push_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("endpoint_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("subscription", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_web_push_subscriptions_user_id", "web_push_subscriptions", ["user_id"])
    op.create_index("ix_door_events_door_received", "door_events", ["door_id", "received_at", "id"])
    op.create_index("ix_password_reset_tokens_expires_at", "password_reset_tokens", ["expires_at"])
    op.create_index("ix_door_invitations_expires_at", "door_invitations", ["expires_at"])


def downgrade():
    op.drop_index("ix_door_invitations_expires_at", table_name="door_invitations")
    op.drop_index("ix_password_reset_tokens_expires_at", table_name="password_reset_tokens")
    op.drop_index("ix_door_events_door_received", table_name="door_events")
    op.drop_table("web_push_subscriptions")
    op.drop_table("background_jobs")
    for table in ("door_memberships", "doors"):
        op.drop_column(table, "left_open_minutes")
