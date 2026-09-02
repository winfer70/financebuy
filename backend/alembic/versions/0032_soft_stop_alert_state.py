"""Track two-stage soft-stop alert delivery without clearing the stop."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "portfolio_positions",
        sa.Column("soft_stop_intraday_on", sa.Date(), nullable=True),
    )
    op.add_column(
        "portfolio_positions",
        sa.Column("soft_stop_eod_on", sa.Date(), nullable=True),
    )
    op.add_column(
        "portfolio_positions",
        sa.Column("soft_stop_delivery_json", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("portfolio_positions", "soft_stop_delivery_json")
    op.drop_column("portfolio_positions", "soft_stop_eod_on")
    op.drop_column("portfolio_positions", "soft_stop_intraday_on")
