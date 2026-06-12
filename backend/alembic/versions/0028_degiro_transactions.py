"""Add degiro_transactions table."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "degiro_transactions",
        sa.Column("transaction_id", sa.BigInteger, primary_key=True),
        sa.Column(
            "portfolio_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("portfolios.portfolio_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("product_name", sa.Text, nullable=True),
        sa.Column("isin", sa.String(12), nullable=True),
        sa.Column("ticker", sa.String(20), nullable=True),
        sa.Column("buysell", sa.String(1), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=True),
        sa.Column("price", sa.Numeric(18, 4), nullable=True),
        sa.Column("value", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("total_in_base", sa.Numeric(18, 4), nullable=True),
        sa.Column("fee_in_base", sa.Numeric(18, 4), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_degiro_transactions_portfolio_id",
        "degiro_transactions",
        ["portfolio_id"],
    )
    op.create_index(
        "ix_degiro_transactions_date",
        "degiro_transactions",
        ["date"],
    )


def downgrade() -> None:
    op.drop_index("ix_degiro_transactions_date", "degiro_transactions")
    op.drop_index("ix_degiro_transactions_portfolio_id", "degiro_transactions")
    op.drop_table("degiro_transactions")
