"""Add shares_after / stake_pct and owner-history index on insider_filings."""

from alembic import op
import sqlalchemy as sa

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "insider_filings",
        sa.Column("shares_after", sa.Numeric(18, 4), nullable=True),
    )
    op.add_column(
        "insider_filings",
        sa.Column("stake_pct", sa.Numeric(8, 6), nullable=True),
    )
    op.create_index(
        "idx_insider_filings_owner_hist",
        "insider_filings",
        ["owner_cik", "ticker", "transaction_code", "transaction_date"],
    )


def downgrade() -> None:
    op.drop_index("idx_insider_filings_owner_hist", table_name="insider_filings")
    op.drop_column("insider_filings", "stake_pct")
    op.drop_column("insider_filings", "shares_after")
