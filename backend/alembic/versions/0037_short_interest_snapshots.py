"""Store FINRA biweekly short-interest snapshots for tracked tickers."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "short_interest_snapshots",
        sa.Column("snapshot_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("settlement_date", sa.Date(), nullable=False),
        sa.Column("current_short_position", sa.Numeric(20, 2), nullable=True),
        sa.Column("previous_short_position", sa.Numeric(20, 2), nullable=True),
        sa.Column("average_daily_volume", sa.Numeric(20, 2), nullable=True),
        sa.Column("days_to_cover", sa.Numeric(10, 2), nullable=True),
        sa.Column("change_percent", sa.Numeric(8, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("ticker", "settlement_date", name="uq_short_interest_ticker_date"),
    )
    op.create_index("idx_short_interest_ticker", "short_interest_snapshots", ["ticker"])


def downgrade() -> None:
    op.drop_index("idx_short_interest_ticker", table_name="short_interest_snapshots")
    op.drop_table("short_interest_snapshots")
