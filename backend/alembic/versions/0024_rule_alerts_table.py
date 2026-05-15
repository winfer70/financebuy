"""Create rule_alerts table

Stores rule-engine alerts triggered by portfolio position analysis.
Alerts are linked to a user and optionally to a specific position.
Supports snoozing, expiry, and multiple severity levels.

NOTE: position_id is stored as a BIGINT for forward-compatibility but
carries NO foreign key constraint because portfolio_positions uses a
UUID primary key (position_id).  The column is a soft reference only.

Revision ID: 0024
Revises: 0023
Create Date: 2026-05-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rule_alerts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Soft reference — portfolio_positions uses UUID PK, not BIGINT id
        sa.Column("position_id", sa.BigInteger(), nullable=True),
        sa.Column("portfolio_id", sa.BigInteger(), nullable=True),
        sa.Column("rule_type", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("triggered_value", sa.Numeric(18, 4), nullable=True),
        sa.Column(
            "state",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # CHECK: severity must be one of the allowed values
    op.create_check_constraint(
        "ck_rule_alerts_severity",
        "rule_alerts",
        "severity IN ('info', 'warning', 'critical')",
    )

    # CHECK: state must be one of the allowed values
    op.create_check_constraint(
        "ck_rule_alerts_state",
        "rule_alerts",
        "state IN ('active', 'snoozed', 'actioned', 'expired')",
    )

    # Composite index for fetching active alerts per user (most common query)
    op.create_index(
        "idx_rule_alerts_user_active",
        "rule_alerts",
        ["user_id", "state", sa.text("created_at DESC")],
    )

    # Index for looking up alerts by position and rule type
    op.create_index(
        "idx_rule_alerts_position",
        "rule_alerts",
        ["position_id", "rule_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_rule_alerts_position", table_name="rule_alerts")
    op.drop_index("idx_rule_alerts_user_active", table_name="rule_alerts")
    op.drop_table("rule_alerts")
