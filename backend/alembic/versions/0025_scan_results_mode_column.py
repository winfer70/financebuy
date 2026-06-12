"""Add mode column to scan_results

Adds a mode column to distinguish how a scan was initiated:
  - 'auto'     : triggered automatically (default, backward-compatible)
  - 'live'     : user-initiated scan using live market data
  - 'prev-day' : user-initiated scan using previous-day close data

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-14
"""

from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add mode column — existing rows default to 'auto' for backward compat
    op.add_column(
        "scan_results",
        sa.Column(
            "mode",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'auto'"),
        ),
    )

    # CHECK: mode must be one of the three supported scan modes
    op.create_check_constraint(
        "ck_scan_results_mode",
        "scan_results",
        "mode IN ('auto', 'live', 'prev-day')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_scan_results_mode", "scan_results", type_="check")
    op.drop_column("scan_results", "mode")
