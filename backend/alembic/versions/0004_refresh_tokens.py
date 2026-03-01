"""add refresh_tokens table

Adds the refresh_tokens table used by the P6.3 JWT refresh token
mechanism.  Refresh tokens are stored as SHA-256 hashes with a
configurable expiry (default 7 days).  Each token is scoped to a
single user and deleted on explicit logout or expiry.

Revision ID: 0004_refresh_tokens
Revises: 0003_integrity_fixes
Create Date: 2026-03-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_refresh_tokens"
down_revision = "0003_integrity_fixes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "refresh_tokens",
        sa.Column(
            "token_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        # SHA-256 hex digest of the raw refresh token (64 hex chars = 256 bits)
        sa.Column("token", sa.String(128), unique=True, nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
    )

    # Index for fast O(1) lookup by token hash on /auth/refresh calls
    op.create_index(
        "idx_refresh_tokens_token",
        "refresh_tokens",
        ["token"],
        unique=True,
    )

    # Index for efficient cleanup of all tokens belonging to a user on logout
    op.create_index(
        "idx_refresh_tokens_user_id",
        "refresh_tokens",
        ["user_id"],
    )


def downgrade():
    op.drop_index("idx_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_index("idx_refresh_tokens_token", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
