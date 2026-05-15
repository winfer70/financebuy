"""Add rule-engine columns to portfolio_positions

Adds six columns that the portfolio rule engine needs to classify and
track positions: t2_usd (T+2 settlement value), is_semi (semi-automated
flag), sector, date_entered, bucket (1/2/3 risk tier), and closed_at.

A CHECK constraint ensures bucket can only be 1, 2, or 3.

Revision ID: 0023
Revises: a1b2
Create Date: 2026-05-14
"""

from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- t2_usd: T+2 settlement value in USD, nullable -----------------------
    op.add_column(
        "portfolio_positions",
        sa.Column("t2_usd", sa.Numeric(18, 2), nullable=True),
    )

    # -- is_semi: semi-automated position flag --------------------------------
    op.add_column(
        "portfolio_positions",
        sa.Column(
            "is_semi",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # -- sector: GICS sector label (e.g. "Technology") ----------------------
    op.add_column(
        "portfolio_positions",
        sa.Column("sector", sa.String(64), nullable=True),
    )

    # -- date_entered: calendar date the position was opened -----------------
    op.add_column(
        "portfolio_positions",
        sa.Column("date_entered", sa.Date(), nullable=True),
    )

    # -- bucket: risk tier (1 = core, 2 = growth, 3 = speculative) ----------
    op.add_column(
        "portfolio_positions",
        sa.Column("bucket", sa.SmallInteger(), nullable=True),
    )

    # CHECK: bucket must be 1, 2, or 3 when not NULL
    op.create_check_constraint(
        "ck_portfolio_positions_bucket",
        "portfolio_positions",
        "bucket IN (1, 2, 3)",
    )

    # -- closed_at: timestamp when the position was closed (soft-close) ------
    op.add_column(
        "portfolio_positions",
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    # Drop the check constraint before dropping the column it guards
    op.drop_constraint(
        "ck_portfolio_positions_bucket",
        "portfolio_positions",
        type_="check",
    )

    op.drop_column("portfolio_positions", "closed_at")
    op.drop_column("portfolio_positions", "bucket")
    op.drop_column("portfolio_positions", "date_entered")
    op.drop_column("portfolio_positions", "sector")
    op.drop_column("portfolio_positions", "is_semi")
    op.drop_column("portfolio_positions", "t2_usd")
