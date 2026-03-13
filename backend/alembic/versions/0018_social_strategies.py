"""
0018_social_strategies — Strategy ratings and usage tracking tables.

Creates:
  - strategy_ratings   — User ratings (1–5 stars) and reviews for public strategies
  - strategy_usage     — Tracks when users clone strategies from the marketplace

Revision: 0018
Revises:  0017
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    # -- strategy_ratings table ------------------------------------------------
    op.create_table(
        "strategy_ratings",
        sa.Column("rating_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "strategy_id", UUID(as_uuid=True),
            sa.ForeignKey("strategies.strategy_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "stars", sa.SmallInteger, nullable=False,
        ),
        sa.Column("review", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # One rating per user per strategy
        sa.UniqueConstraint("strategy_id", "user_id", name="uq_strategy_ratings_strategy_user"),
        # Stars must be between 1 and 5
        sa.CheckConstraint("stars >= 1 AND stars <= 5", name="ck_strategy_ratings_stars_range"),
    )

    op.create_index(
        "idx_strategy_ratings_strategy_id",
        "strategy_ratings",
        ["strategy_id"],
    )

    # -- strategy_usage table --------------------------------------------------
    op.create_table(
        "strategy_usage",
        sa.Column("usage_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "strategy_id", UUID(as_uuid=True),
            sa.ForeignKey("strategies.strategy_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "cloned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index(
        "idx_strategy_usage_strategy_id",
        "strategy_usage",
        ["strategy_id"],
    )


def downgrade():
    op.drop_table("strategy_usage")
    op.drop_table("strategy_ratings")
