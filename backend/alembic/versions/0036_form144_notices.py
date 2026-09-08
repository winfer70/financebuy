"""Store ingested Form 144 (Notice of Proposed Sale) filings."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "form144_notices",
        sa.Column("notice_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("accession", sa.String(25), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=True),
        sa.Column("issuer_cik", sa.String(10), nullable=True),
        sa.Column("issuer_name", sa.String(256), nullable=True),
        sa.Column("owner_cik", sa.String(10), nullable=True),
        sa.Column("owner_name", sa.String(256), nullable=True),
        sa.Column("relationships", sa.String(128), nullable=True),
        sa.Column("broker", sa.String(256), nullable=True),
        sa.Column("shares", sa.Numeric(18, 4), nullable=True),
        sa.Column("aggregate_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("approx_sale_date", sa.Date(), nullable=True),
        sa.Column("notice_date", sa.Date(), nullable=True),
        sa.Column("filing_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("accession", name="uq_form144_notices_accession"),
    )
    op.create_index(
        "idx_form144_notices_owner_ticker", "form144_notices", ["owner_cik", "ticker"]
    )
    op.create_index("idx_form144_notices_ticker", "form144_notices", ["ticker"])


def downgrade() -> None:
    op.drop_index("idx_form144_notices_ticker", table_name="form144_notices")
    op.drop_index("idx_form144_notices_owner_ticker", table_name="form144_notices")
    op.drop_table("form144_notices")
