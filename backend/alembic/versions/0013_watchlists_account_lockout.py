"""
0013_watchlists_account_lockout — Add account lockout columns and
watchlist/watchlist-item tables.

Adds failed_login_attempts and locked_until columns to the users table
to support brute-force protection with progressive account lockout.

Creates the watchlists table so users can organise named lists of assets
they want to track without holding a position.

Creates the watchlist_items table for the individual symbols within each
watchlist, with a unique constraint preventing duplicate tickers per list.

Revision: 0013
Revises:  0012_reports_email_verify
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# Revision identifiers
revision = "0013"
down_revision = "0012_reports_email_verify"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add lockout columns to users, create watchlists and watchlist_items tables."""

    # ── 1. Account lockout columns on the users table ─────────────────
    # Tracks consecutive failed login attempts; resets on success.
    op.add_column(
        "users",
        sa.Column(
            "failed_login_attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="Consecutive failed login attempts; resets on successful login.",
        ),
    )

    # Timestamp until which the account is locked out (NULL = not locked).
    op.add_column(
        "users",
        sa.Column(
            "locked_until",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Account is locked until this timestamp; NULL means not locked.",
        ),
    )

    # ── 2. watchlists table ───────────────────────────────────────────
    op.create_table(
        "watchlists",
        # Primary key — auto-generated UUID.
        sa.Column(
            "watchlist_id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        # Owning user — cascade delete so watchlists are cleaned up.
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Human-readable watchlist name.
        sa.Column("name", sa.String(128), nullable=False),
        # Timestamps.
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    # ── 3. watchlist_items table ──────────────────────────────────────
    op.create_table(
        "watchlist_items",
        # Primary key — auto-generated UUID.
        sa.Column(
            "item_id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        # Parent watchlist — cascade delete so items are removed with list.
        sa.Column(
            "watchlist_id",
            UUID(as_uuid=True),
            sa.ForeignKey("watchlists.watchlist_id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Ticker symbol (e.g. "AAPL", "BTC-USD").
        sa.Column("symbol", sa.String(20), nullable=False),
        # Asset classification: stock, crypto, etf, physical.
        sa.Column(
            "asset_type",
            sa.String(20),
            server_default="stock",
            nullable=False,
        ),
        # Free-form user note for this watchlist entry.
        sa.Column("notes", sa.Text(), nullable=True),
        # Manual ordering within the watchlist.
        sa.Column(
            "position_order",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        # Snapshot of the market price at the moment the symbol was added.
        sa.Column("price_when_added", sa.Numeric(18, 4), nullable=True),
        # Timestamp when the item was added to the watchlist.
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        # Prevent duplicate symbols within the same watchlist.
        sa.UniqueConstraint("watchlist_id", "symbol", name="uq_watchlist_item_symbol"),
    )

    # Index on watchlist_id for fast look-ups of items within a list.
    op.create_index(
        "idx_watchlist_items_watchlist_id",
        "watchlist_items",
        ["watchlist_id"],
    )


def downgrade() -> None:
    """Remove watchlist_items, watchlists tables, and lockout columns from users."""

    # Drop watchlist_items (index first, then table).
    op.drop_index("idx_watchlist_items_watchlist_id", table_name="watchlist_items")
    op.drop_table("watchlist_items")

    # Drop watchlists table.
    op.drop_table("watchlists")

    # Drop lockout columns from users.
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_attempts")
