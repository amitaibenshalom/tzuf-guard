"""Remove retired website notification subscriptions."""
from alembic import op
import sqlalchemy as sa

revision = "0009_remove_browser_push"
down_revision = "0008_background_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("web_push_subscriptions")


def downgrade():
    op.create_table(
        "web_push_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("endpoint_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("subscription", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_web_push_subscriptions_user_id", "web_push_subscriptions", ["user_id"])
