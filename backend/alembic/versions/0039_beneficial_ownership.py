"""Store ingested Schedule 13D/13G (beneficial ownership >5%) filings."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "beneficial_ownership",
        sa.Column("ownership_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("accession", sa.String(25), nullable=False),
        sa.Column("person_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_13d", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_amendment", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ticker", sa.String(20), nullable=True),
        sa.Column("issuer_cik", sa.String(10), nullable=True),
        sa.Column("issuer_name", sa.String(256), nullable=True),
        sa.Column("filer_cik", sa.String(10), nullable=True),
        sa.Column("filer_name", sa.String(256), nullable=True),
        sa.Column("shares_owned", sa.Numeric(20, 4), nullable=True),
        sa.Column("pct_owned", sa.Numeric(8, 4), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("purpose_text", sa.Text(), nullable=True),
        sa.Column("filing_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "accession", "person_index", name="uq_beneficial_ownership_accession_person"
        ),
    )
    op.create_index("idx_beneficial_ownership_ticker", "beneficial_ownership", ["ticker"])


def downgrade() -> None:
    op.drop_index("idx_beneficial_ownership_ticker", table_name="beneficial_ownership")
    op.drop_table("beneficial_ownership")
