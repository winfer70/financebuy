"""Create news_articles and news_article_tickers tables.

Adds the two tables required by the background news pipeline:
  - news_articles:         stores pre-scored articles posted by the LLM worker
  - news_article_tickers:  junction table for per-ticker impact scores

Revision ID: 0009_news_articles
Revises: 0008_chart_templates
Create Date: 2026-03-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0009_news_articles"
down_revision = "0008_chart_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── news_articles — stores pre-scored articles from the LLM worker ───────
    op.create_table(
        "news_articles",
        sa.Column(
            "article_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "scored_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # General market impact score (-5 to +5)
        sa.Column(
            "general_score",
            sa.SmallInteger,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("general_reasoning", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # Dedup constraint on URL
        sa.UniqueConstraint("url", name="uq_news_articles_url"),
    )
    op.create_index(
        "idx_news_articles_published",
        "news_articles",
        [sa.text("published_at DESC")],
    )
    op.create_index(
        "idx_news_articles_scored",
        "news_articles",
        [sa.text("scored_at DESC")],
    )

    # ── news_article_tickers — per-ticker impact scores ──────────────────────
    op.create_table(
        "news_article_tickers",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "article_id",
            UUID(as_uuid=True),
            sa.ForeignKey("news_articles.article_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ticker", sa.String(20), nullable=False),
        # Ticker-specific impact score (-5 to +5)
        sa.Column(
            "score",
            sa.SmallInteger,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("reasoning", sa.Text, nullable=True),
        # Each article can reference a ticker only once
        sa.UniqueConstraint("article_id", "ticker", name="uq_article_ticker"),
    )
    op.create_index(
        "idx_news_article_tickers_ticker",
        "news_article_tickers",
        ["ticker"],
    )
    op.create_index(
        "idx_news_article_tickers_article",
        "news_article_tickers",
        ["article_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_news_article_tickers_article", table_name="news_article_tickers"
    )
    op.drop_index(
        "idx_news_article_tickers_ticker", table_name="news_article_tickers"
    )
    op.drop_table("news_article_tickers")

    op.drop_index("idx_news_articles_scored", table_name="news_articles")
    op.drop_index("idx_news_articles_published", table_name="news_articles")
    op.drop_table("news_articles")
