"""
0012_reports_email_verify — Add email verification, account management,
and user reports infrastructure.

Adds email_verified, deactivated_at, and deletion_scheduled_at columns
to the users table so accounts can be verified, soft-deactivated, and
scheduled for permanent deletion.

Creates the user_reports table for bug reports, feature suggestions,
and activation-related issues submitted by users.

Creates the email_verification_tokens table to store single-use tokens
for email verification, email changes, reactivation, and deletion
cancellation flows.

Revision: 0012_reports_email_verify
Revises:  0011_user_preferences
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# Revision identifiers
revision = "0012_reports_email_verify"
down_revision = "0011_user_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add email verification columns, user_reports table, and email_verification_tokens table."""

    # ── 1. New columns on the users table ────────────────────────────
    # email_verified defaults to true so every existing row is treated
    # as already verified; only future sign-ups go through the flow.
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            server_default="true",
            nullable=False,
            comment="Whether the user has verified their email address.",
        ),
    )

    # Timestamp when an account was soft-deactivated (NULL = active).
    op.add_column(
        "users",
        sa.Column(
            "deactivated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when the account was deactivated; NULL means active.",
        ),
    )

    # Timestamp when a permanent deletion is scheduled (NULL = none).
    op.add_column(
        "users",
        sa.Column(
            "deletion_scheduled_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when permanent account deletion is scheduled.",
        ),
    )

    # ── 2. user_reports table ────────────────────────────────────────
    op.create_table(
        "user_reports",
        # Primary key — auto-generated UUID.
        sa.Column(
            "report_id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        # Link back to the reporting user (nullable; SET NULL on delete).
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Reporter email kept separately so reports survive user deletion.
        sa.Column("reporter_email", sa.String(255), nullable=False),
        # Report classification: bug | suggestion | activation_bug.
        sa.Column("report_type", sa.String(20), nullable=False),
        # Optional sub-category for finer-grained triage.
        sa.Column("category", sa.String(50), nullable=True),
        # Short summary and full body.
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        # Workflow status — defaults to "new".
        sa.Column(
            "status",
            sa.String(20),
            server_default="new",
            nullable=False,
        ),
        # Internal admin notes (not visible to end users).
        sa.Column("admin_notes", sa.Text(), nullable=True),
        # Timestamps.
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes for common query patterns (filter by status, sort by date).
    op.create_index("ix_user_reports_status", "user_reports", ["status"])
    op.create_index("ix_user_reports_created_at", "user_reports", ["created_at"])

    # ── 3. email_verification_tokens table ───────────────────────────
    op.create_table(
        "email_verification_tokens",
        # Primary key — auto-generated UUID.
        sa.Column(
            "token_id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        # Owning user — cascade delete so tokens are cleaned up.
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        # The opaque token string (unique, indexed for fast look-ups).
        sa.Column(
            "token",
            sa.String(128),
            unique=True,
            nullable=False,
            index=True,
        ),
        # Token purpose: email_verify | email_change | reactivate | cancel_deletion.
        sa.Column("token_type", sa.String(30), nullable=False),
        # Only populated for email_change tokens.
        sa.Column("new_email", sa.String(255), nullable=True),
        # Hard expiry — tokens cannot be used after this timestamp.
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        # Whether the token has already been consumed.
        sa.Column("used", sa.Boolean(), server_default="false"),
        # Creation timestamp.
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    """Remove email_verification_tokens, user_reports, and user account columns."""

    # Drop tables in reverse creation order.
    op.drop_table("email_verification_tokens")

    # Drop indexes before the table (explicit for clarity).
    op.drop_index("ix_user_reports_created_at", table_name="user_reports")
    op.drop_index("ix_user_reports_status", table_name="user_reports")
    op.drop_table("user_reports")

    # Drop the three new columns from users.
    op.drop_column("users", "deletion_scheduled_at")
    op.drop_column("users", "deactivated_at")
    op.drop_column("users", "email_verified")
