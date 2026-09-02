"""Add rule_refinements table for AI-suggested rule changes."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rule_refinements",
        sa.Column("refinement_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trade_count", sa.Integer, nullable=True),
        sa.Column("win_rate_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("avg_pnl_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("pattern_summary", sa.Text, nullable=True),
        sa.Column("suggested_rules", JSONB, nullable=True),
        sa.Column("raw_ollama_response", sa.Text, nullable=True),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),  # pending|approved|rejected
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_rule_refinements_status", "rule_refinements", ["status"])
    op.create_index("idx_rule_refinements_generated_at", "rule_refinements", ["generated_at"])


def downgrade() -> None:
    op.drop_index("idx_rule_refinements_generated_at", table_name="rule_refinements")
    op.drop_index("idx_rule_refinements_status", table_name="rule_refinements")
    op.drop_table("rule_refinements")
