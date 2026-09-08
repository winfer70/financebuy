"""Store Form 8-K filings for tracked tickers only."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "eight_k_filings",
        sa.Column("filing_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("accession", sa.String(25), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("issuer_cik", sa.String(10), nullable=True),
        sa.Column("issuer_name", sa.String(256), nullable=True),
        sa.Column("is_amendment", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("items", JSONB(), nullable=True),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filing_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("accession", name="uq_eight_k_filings_accession"),
    )
    op.create_index("idx_eight_k_filings_ticker", "eight_k_filings", ["ticker"])


def downgrade() -> None:
    op.drop_index("idx_eight_k_filings_ticker", table_name="eight_k_filings")
    op.drop_table("eight_k_filings")
