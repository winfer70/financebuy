"""
0014_profit_taking — Add profit-taking target price column to portfolio
positions.

Adds a nullable profit_taking column (Numeric 18,2) to the
portfolio_positions table.  Users can set a target price at which they
intend to take profits, analogous to the existing stop_loss column.

Revision: 0014
Revises:  0013
"""

from alembic import op
import sqlalchemy as sa

# Revision identifiers
revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add profit_taking column to portfolio_positions."""

    op.add_column(
        "portfolio_positions",
        sa.Column(
            "profit_taking",
            sa.Numeric(18, 2),
            nullable=True,
            comment="Target price at which the user intends to take profits.",
        ),
    )


def downgrade() -> None:
    """Remove profit_taking column from portfolio_positions."""

    op.drop_column("portfolio_positions", "profit_taking")
