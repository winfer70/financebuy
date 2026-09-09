"""Store ingested Form 4 non-derivative transactions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "insider_filings",
        sa.Column("filing_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("accession", sa.String(25), nullable=False),
        sa.Column("txn_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("issuer_cik", sa.String(10), nullable=True),
        sa.Column("owner_name", sa.String(256), nullable=True),
        sa.Column("owner_cik", sa.String(10), nullable=True),
        sa.Column("is_director", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_officer", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_ten_percent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("officer_title", sa.String(128), nullable=True),
        sa.Column("transaction_code", sa.String(4), nullable=False),
        sa.Column("acquired_disposed", sa.String(1), nullable=True),
        sa.Column("shares", sa.Numeric(18, 4), nullable=True),
        sa.Column("price", sa.Numeric(18, 4), nullable=True),
        sa.Column("notional", sa.Numeric(18, 2), nullable=True),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("is_10b5_1", sa.Boolean(), nullable=True),
        sa.Column("filing_url", sa.Text(), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("accession", "txn_index", name="uq_insider_filings_accession_txn"),
    )
    op.create_index(
        "idx_insider_filings_ticker_code_date",
        "insider_filings",
        ["ticker", "transaction_code", "transaction_date"],
    )
    op.create_index("idx_insider_filings_accession", "insider_filings", ["accession"])


def downgrade() -> None:
    op.drop_index("idx_insider_filings_accession", table_name="insider_filings")
    op.drop_index("idx_insider_filings_ticker_code_date", table_name="insider_filings")
    op.drop_table("insider_filings")
