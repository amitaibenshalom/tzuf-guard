"""google auth and password reset

Revision ID: 0002_google_auth_password_reset
Revises: 0001_initial_schema
Create Date: 2026-07-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_google_auth_password_reset"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "password_hash",
            existing_type=sa.String(length=255),
            nullable=True,
        )
        batch_op.add_column(sa.Column("google_sub", sa.String(length=255), nullable=True))

    op.create_index(op.f("ix_users_google_sub"), "users", ["google_sub"], unique=True)

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_password_reset_tokens_token_hash"),
        "password_reset_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_password_reset_tokens_user_id"),
        "password_reset_tokens",
        ["user_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_password_reset_tokens_user_id"), table_name="password_reset_tokens"
    )
    op.drop_index(
        op.f("ix_password_reset_tokens_token_hash"), table_name="password_reset_tokens"
    )
    op.drop_table("password_reset_tokens")

    op.drop_index(op.f("ix_users_google_sub"), table_name="users")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("google_sub")
        batch_op.alter_column(
            "password_hash",
            existing_type=sa.String(length=255),
            nullable=False,
        )
