"""add portfolios and portfolio_positions tables

Adds the portfolios and portfolio_positions tables used by the
Portfolio Manager feature.  Users can track multiple named portfolios,
each containing positions with ticker, quantity, purchase price, and
optional group tag.

Revision ID: 0005_portfolio_manager
Revises: 0004_refresh_tokens
Create Date: 2026-03-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_portfolio_manager"
down_revision = "0004_refresh_tokens"
branch_labels = None
depends_on = None


def upgrade():
    # ── portfolios ────────────────────────────────────────────────────────────
    op.create_table(
        "portfolios",
        sa.Column(
            "portfolio_id",
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
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("strategy", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
    )

    # ── portfolio_positions ───────────────────────────────────────────────────
    op.create_table(
        "portfolio_positions",
        sa.Column(
            "position_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "portfolio_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("portfolios.portfolio_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("name", sa.String(256), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("purchase_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purchase_price", sa.Numeric(18, 2), nullable=False),
        sa.Column("group_tag", sa.String(64), nullable=True),
        sa.Column(
            "is_excluded",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint("quantity > 0", name="ck_portfolio_positions_quantity_positive"),
    )

    op.create_index(
        "idx_portfolio_positions_portfolio_id",
        "portfolio_positions",
        ["portfolio_id"],
    )


def downgrade():
    op.drop_index("idx_portfolio_positions_portfolio_id", table_name="portfolio_positions")
    op.drop_table("portfolio_positions")
    op.drop_table("portfolios")
