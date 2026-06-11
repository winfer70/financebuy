"""add sold_reason to portfolio_positions

Revision ID: 0027
Revises: 0026
Create Date: 2026-06-11
"""

from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "portfolio_positions",
        sa.Column("sold_reason", sa.Text, nullable=True),
    )


def downgrade():
    op.drop_column("portfolio_positions", "sold_reason")
