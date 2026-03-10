"""
models.py — SQLAlchemy ORM models for TickerTap.

Defines all database tables: users, accounts, transactions, securities,
holdings, orders, password_reset_tokens, email_verification_tokens,
user_reports, audit_log, news_articles, news_article_tickers,
score_outcomes, scoring_rules, watchlists, and watchlist_items.

All foreign keys specify ondelete behaviour and nullable=False where
a parent reference is required, ensuring referential integrity.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.sql import func
import uuid

from .db import Base


class User(Base):
    """Registered platform user."""

    __tablename__ = "users"

    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100))
    last_name = Column(String(100))
    phone = Column(String(20))
    kyc_status = Column(String(20), server_default="pending")
    is_active = Column(Boolean, server_default="true")
    email_verified = Column(Boolean, server_default="true", nullable=False)
    deactivated_at = Column(DateTime(timezone=True), nullable=True)
    deletion_scheduled_at = Column(DateTime(timezone=True), nullable=True)
    failed_login_attempts = Column(Integer, server_default="0", nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
    preferences = Column(JSONB, server_default="{}", nullable=True)


class Account(Base):
    """Brokerage account owned by a user."""

    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_accounts_balance_positive"),
    )

    account_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    account_type = Column(String(50), nullable=False)
    account_number = Column(String(50), unique=True, nullable=False)
    balance = Column(Numeric(18, 2), server_default="0.00")
    currency = Column(String(3), server_default="USD")
    status = Column(String(20), server_default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class Transaction(Base):
    """Monetary transaction (deposit/withdrawal) on an account."""

    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        Index("idx_transactions_account_created", "account_id", "created_at"),
    )

    transaction_id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.account_id", ondelete="CASCADE"),
        nullable=False,
    )
    transaction_type = Column(String(20), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(3), server_default="USD")
    status = Column(String(20), server_default="pending")
    description = Column(Text)
    reference_number = Column(String(100), unique=True)
    executed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Security(Base):
    """Tradeable security (stock, ETF, etc.)."""

    __tablename__ = "securities"

    security_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(10), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    security_type = Column(String(50), nullable=False)
    exchange = Column(String(50))
    currency = Column(String(3), server_default="USD")
    is_active = Column(Boolean, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Holding(Base):
    """Position in a security held within an account."""

    __tablename__ = "holdings"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_holdings_quantity_positive"),
    )

    holding_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.account_id", ondelete="CASCADE"),
        nullable=False,
    )
    security_id = Column(
        UUID(as_uuid=True),
        ForeignKey("securities.security_id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity = Column(Numeric(18, 6), nullable=False)
    average_cost = Column(Numeric(18, 2))
    current_price = Column(Numeric(18, 2))
    last_updated = Column(DateTime(timezone=True), server_default=func.now())


class Order(Base):
    """Buy/sell order placed against an account."""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_orders_quantity_positive"),
        Index("idx_orders_account_status", "account_id", "status"),
    )

    order_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.account_id", ondelete="CASCADE"),
        nullable=False,
    )
    security_id = Column(
        UUID(as_uuid=True),
        ForeignKey("securities.security_id", ondelete="RESTRICT"),
        nullable=False,
    )
    order_type = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)
    quantity = Column(Numeric(18, 6), nullable=False)
    price = Column(Numeric(18, 2))
    status = Column(String(20), server_default="pending")
    filled_quantity = Column(Numeric(18, 6), server_default="0")
    filled_price = Column(Numeric(18, 2))
    placed_at = Column(DateTime(timezone=True), server_default=func.now())
    executed_at = Column(DateTime(timezone=True))
    cancelled_at = Column(DateTime(timezone=True))


class PasswordResetToken(Base):
    """One-time password reset token linked to a user."""

    __tablename__ = "password_reset_tokens"

    token_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    token = Column(String(128), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RefreshToken(Base):
    """Long-lived refresh token linked to a user session (P6.3).

    The raw token value is sent to the client via an httpOnly, Secure,
    SameSite=Strict cookie only.  Only the SHA-256 hash is persisted here
    so that a compromised database cannot be used to issue new access tokens.

    Lifecycle:
        - Created at login alongside the short-lived access token.
        - Consumed at /auth/refresh to issue a new access token.
        - Rotated on each use (old token deleted, new token issued).
        - Expires after REFRESH_TOKEN_EXPIRE_DAYS days (default: 7).
        - Deleted on explicit logout.

    Relationships:
        user: The User who owns this token (CASCADE on user deletion).

    Indexes:
        token — unique index for O(1) lookup by hash.
    """

    __tablename__ = "refresh_tokens"

    token_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    # SHA-256 hex digest of the raw refresh token — never store the raw value
    token = Column(String(128), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EmailVerificationToken(Base):
    """One-time token for email verification, email changes, reactivation,
    and deletion cancellation."""

    __tablename__ = "email_verification_tokens"

    token_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    token = Column(String(128), unique=True, nullable=False, index=True)
    token_type = Column(String(30), nullable=False)
    new_email = Column(String(255), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserReport(Base):
    """User-submitted bug report or feature suggestion."""

    __tablename__ = "user_reports"
    __table_args__ = (
        Index("idx_user_reports_status", "status"),
        Index("idx_user_reports_created", "created_at"),
    )

    report_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    reporter_email = Column(String(255), nullable=False)
    report_type = Column(String(20), nullable=False)
    category = Column(String(50), nullable=True)
    subject = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String(20), server_default="new", nullable=False)
    admin_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)


class Portfolio(Base):
    """Named portfolio owned by a user for tracking custom positions."""

    __tablename__ = "portfolios"

    portfolio_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(128), nullable=False)
    strategy = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PortfolioPosition(Base):
    """A single holding within a Portfolio."""

    __tablename__ = "portfolio_positions"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_portfolio_positions_quantity_positive"),
        Index("idx_portfolio_positions_portfolio_id", "portfolio_id"),
    )

    position_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id = Column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.portfolio_id", ondelete="CASCADE"),
        nullable=False,
    )
    ticker = Column(String(20), nullable=False)
    name = Column(String(256), nullable=True)
    quantity = Column(Numeric(18, 6), nullable=False)
    purchase_date = Column(DateTime(timezone=True), nullable=True)
    purchase_price = Column(Numeric(18, 2), nullable=False)
    group_tag = Column(String(64), nullable=True)
    is_excluded = Column(Boolean, server_default="false", nullable=False)
    asset_type = Column(String(20), server_default="stock", nullable=False)
    physical_type = Column(String(20), nullable=True)
    stop_loss = Column(Numeric(18, 2), nullable=True)
    profit_taking = Column(Numeric(18, 2), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    """Immutable audit trail for all user-initiated actions."""

    __tablename__ = "audit_log"

    log_id = Column(
        Numeric(asdecimal=False), primary_key=True, autoincrement=True
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
    )
    action = Column(String(100), nullable=False)
    table_name = Column(String(100))
    record_id = Column(UUID(as_uuid=True))
    old_values = Column(JSONB)
    new_values = Column(JSONB)
    ip_address = Column(INET)
    user_agent = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ChartTemplate(Base):
    """Saved chart template with drawings and overlay configuration."""

    __tablename__ = "chart_templates"
    __table_args__ = (
        Index("idx_chart_templates_user_id", "user_id"),
    )

    template_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(128), nullable=False)
    symbol = Column(String(20), nullable=True)
    interval = Column(String(10), nullable=True)
    drawings_json = Column(JSONB, nullable=False, server_default="'[]'::jsonb")
    overlays_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class NewsArticle(Base):
    """Pre-scored news article ingested by the background LLM worker.

    Articles are posted by Server B via the internal ingestion API and
    served directly from PostgreSQL — no live RSS fetching or on-request
    LLM inference.  Each article carries a general market impact score
    and may be linked to specific tickers via NewsArticleTicker.
    """

    __tablename__ = "news_articles"
    __table_args__ = (
        UniqueConstraint("url", name="uq_news_articles_url"),
        Index("idx_news_articles_published", "published_at"),
        Index("idx_news_articles_scored", "scored_at"),
    )

    article_id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    url = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    source = Column(String(20), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    scored_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # General market impact score: -5 (extremely bearish) to +5 (extremely bullish)
    general_score = Column(SmallInteger, nullable=False, server_default="0")
    general_reasoning = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class NewsArticleTicker(Base):
    """Per-ticker impact score for a news article.

    Junction table linking news_articles to individual ticker symbols.
    Each row carries a ticker-specific score and reasoning produced by
    the LLM, independent of the article's general market score.
    """

    __tablename__ = "news_article_tickers"
    __table_args__ = (
        UniqueConstraint("article_id", "ticker", name="uq_article_ticker"),
        Index("idx_news_article_tickers_ticker", "ticker"),
        Index("idx_news_article_tickers_article", "article_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    article_id = Column(
        UUID(as_uuid=True),
        ForeignKey("news_articles.article_id", ondelete="CASCADE"),
        nullable=False,
    )
    ticker = Column(String(20), nullable=False)
    # Ticker-specific impact score: -5 (extremely bearish) to +5 (extremely bullish)
    score = Column(SmallInteger, nullable=False, server_default="0")
    reasoning = Column(Text, nullable=True)


class ScoreOutcome(Base):
    """Recorded outcome comparing an LLM prediction against actual price movement.

    Each row captures what happened to a stock (or SPY for general scores) after
    the LLM scored a news article.  The accuracy_grade summarises whether the
    prediction direction and magnitude matched real price movement.

    Used by the learner to identify scoring biases and generate calibration rules.
    """

    __tablename__ = "score_outcomes"
    __table_args__ = (
        UniqueConstraint(
            "article_id", "ticker", "score_type",
            name="uq_score_outcome_article_ticker",
        ),
        CheckConstraint(
            "score_type IN ('general', 'ticker')",
            name="ck_score_outcomes_score_type",
        ),
        CheckConstraint(
            "accuracy_grade IN ('correct', 'close', 'wrong', 'opposite')",
            name="ck_score_outcomes_grade",
        ),
        CheckConstraint(
            "predicted_score BETWEEN -5 AND 5",
            name="ck_score_outcomes_predicted",
        ),
        Index("idx_score_outcomes_article", "article_id"),
        Index("idx_score_outcomes_checked", "checked_at"),
        Index("idx_score_outcomes_grade", "accuracy_grade"),
        Index("idx_score_outcomes_ticker", "ticker"),
    )

    outcome_id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    article_id = Column(
        UUID(as_uuid=True),
        ForeignKey("news_articles.article_id", ondelete="CASCADE"),
        nullable=False,
    )
    ticker = Column(String(20), nullable=False)
    score_type = Column(String(10), nullable=False)
    predicted_score = Column(SmallInteger, nullable=False)
    predicted_reasoning = Column(Text, nullable=True)
    price_at_score = Column(Numeric(18, 4), nullable=True)
    price_after = Column(Numeric(18, 4), nullable=True)
    actual_change_pct = Column(Numeric(10, 4), nullable=True)
    accuracy_grade = Column(String(10), nullable=False)
    scored_at = Column(DateTime(timezone=True), nullable=False)
    checked_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ScoringRule(Base):
    """Versioned set of calibration rules generated by the learner.

    Only one rule set is active at any time.  When the worker fetches rules,
    it receives the active version and injects the rules_text into the LLM
    scoring prompt.  Historical versions are kept for accuracy tracking.
    """

    __tablename__ = "scoring_rules"
    __table_args__ = (
        UniqueConstraint("rule_version", name="uq_scoring_rules_version"),
        Index(
            "idx_scoring_rules_active",
            "is_active",
            postgresql_where="is_active = TRUE",
        ),
    )

    rule_id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rule_version = Column(Integer, nullable=False)
    rules_text = Column(Text, nullable=False)
    analysis_summary = Column(Text, nullable=True)
    sample_size = Column(Integer, nullable=True)
    accuracy_before = Column(Numeric(5, 2), nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="FALSE")
    generated_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Watchlist(Base):
    """Named watchlist owned by a user for tracking assets without positions."""

    __tablename__ = "watchlists"

    watchlist_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class WatchlistItem(Base):
    """A single asset tracked within a Watchlist."""

    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("watchlist_id", "symbol", name="uq_watchlist_item_symbol"),
        Index("idx_watchlist_items_watchlist_id", "watchlist_id"),
    )

    item_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    watchlist_id = Column(
        UUID(as_uuid=True),
        ForeignKey("watchlists.watchlist_id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol = Column(String(20), nullable=False)
    asset_type = Column(String(20), server_default="stock", nullable=False)
    notes = Column(Text, nullable=True)
    position_order = Column(Integer, server_default="0", nullable=False)
    price_when_added = Column(Numeric(18, 4), nullable=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())
