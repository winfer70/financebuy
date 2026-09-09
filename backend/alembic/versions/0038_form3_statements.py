"""Store ingested Form 3 (Initial Statement of Beneficial Ownership) filings."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "form3_statements",
        sa.Column("statement_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("accession", sa.String(25), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("issuer_cik", sa.String(10), nullable=True),
        sa.Column("owner_name", sa.String(256), nullable=True),
        sa.Column("owner_cik", sa.String(10), nullable=True),
        sa.Column("is_director", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_officer", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_ten_percent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("officer_title", sa.String(128), nullable=True),
        sa.Column("shares_owned", sa.Numeric(18, 4), nullable=True),
        sa.Column("period_of_report", sa.Date(), nullable=True),
        sa.Column("filing_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("accession", name="uq_form3_statements_accession"),
    )
    op.create_index(
        "idx_form3_statements_owner_ticker", "form3_statements", ["owner_cik", "ticker"]
    )


def downgrade() -> None:
    op.drop_index("idx_form3_statements_owner_ticker", table_name="form3_statements")
    op.drop_table("form3_statements")
