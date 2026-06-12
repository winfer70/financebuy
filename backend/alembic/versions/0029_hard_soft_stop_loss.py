"""Rename stop_loss to hard_stop_loss; add soft_stop_loss."""

from alembic import op
import sqlalchemy as sa

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("portfolio_positions", "stop_loss", new_column_name="hard_stop_loss")
    op.add_column(
        "portfolio_positions",
        sa.Column("soft_stop_loss", sa.Numeric(18, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("portfolio_positions", "soft_stop_loss")
    op.alter_column("portfolio_positions", "hard_stop_loss", new_column_name="stop_loss")
