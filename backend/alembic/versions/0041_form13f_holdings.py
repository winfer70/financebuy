"""Store Form 13F-HR holdings for tracked tickers only."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "form13f_holdings",
        sa.Column("holding_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("accession", sa.String(25), nullable=False),
        sa.Column("filer_cik", sa.String(10), nullable=True),
        sa.Column("filer_name", sa.String(256), nullable=True),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("cusip", sa.String(9), nullable=False),
        sa.Column("issuer_name", sa.String(256), nullable=True),
        sa.Column("shares", sa.Numeric(20, 2), nullable=True),
        sa.Column("value_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("is_amendment", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filing_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("accession", "cusip", name="uq_form13f_holdings_accession_cusip"),
    )
    op.create_index("idx_form13f_holdings_ticker", "form13f_holdings", ["ticker"])


def downgrade() -> None:
    op.drop_index("idx_form13f_holdings_ticker", table_name="form13f_holdings")
    op.drop_table("form13f_holdings")
