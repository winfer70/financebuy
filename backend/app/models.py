"""
models.py — SQLAlchemy ORM models for TickerTap.

Defines all database tables: users, accounts, transactions, securities,
holdings, orders, password_reset_tokens, email_verification_tokens,
user_reports, audit_log, news_articles, news_article_tickers,
score_outcomes, scoring_rules, watchlists, watchlist_items,
strategies, strategy_versions, backtest_results, trading_signals,
price_alerts, notifications, and user_webhooks.

All foreign keys specify ondelete behaviour and nullable=False where
a parent reference is required, ensuring referential integrity.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import relationship
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
    # Per-user Telegram notification target. The bot token stays a single
    # server-side secret (TELEGRAM_BOT_TOKEN env var) — this is just the
    # chat_id Telegram reports once this user's account has messaged the
    # bot, learned automatically via the /link command, never typed in.
    telegram_chat_id = Column(String(64), nullable=True)
    telegram_link_code = Column(String(16), nullable=True)
    telegram_link_code_expires_at = Column(DateTime(timezone=True), nullable=True)


class TelegramInvite(Base):
    """One-time invite code gating the Telegram-connect step on /register.

    Without a valid code, the register page never shows the Telegram step —
    this is what lets a friend register and link their own chat without an
    admin having to hand them anything more sensitive than a URL.
    """

    __tablename__ = "telegram_invites"

    invite_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(32), unique=True, nullable=False)
    created_by = Column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    used_by = Column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


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
    cash_balance = Column(Numeric(18, 4), nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship to trade history; cascade deletes when portfolio is removed
    trades = relationship("PortfolioTrade", back_populates="portfolio", cascade="all, delete-orphan")


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
    hard_stop_loss = Column(Numeric(18, 2), nullable=True)
    soft_stop_loss = Column(Numeric(18, 2), nullable=True)
    # Two-stage soft-stop delivery: NY dates last successfully pinged (at least
    # one of Telegram/ntfy). Stop itself is never auto-cleared.
    soft_stop_intraday_on = Column(Date, nullable=True)
    soft_stop_eod_on = Column(Date, nullable=True)
    soft_stop_delivery_json = Column(JSONB, nullable=True)
    profit_taking = Column(Numeric(18, 2), nullable=True)

    def reset_soft_stop_stages(self) -> None:
        """Clear two-stage alert state so a new soft-stop level can fire again."""
        self.soft_stop_intraday_on = None
        self.soft_stop_eod_on = None
        self.soft_stop_delivery_json = None
    # Rule-engine fields (added migration 0023) --------------------------------
    # T+2 settlement value in USD
    t2_usd = Column(Numeric(18, 2), nullable=True)
    # True when the position is semi-automated (rule-managed but user-confirmed)
    is_semi = Column(Boolean, default=False, nullable=False)
    # GICS sector label, e.g. "Technology"
    sector = Column(String(64), nullable=True)
    # Calendar date the position was first opened
    date_entered = Column(Date, nullable=True)
    # Risk tier: 1 = core, 2 = growth, 3 = speculative; CHECK (bucket IN (1,2,3))
    bucket = Column(SmallInteger, nullable=True)
    # Timestamp when the position was soft-closed
    closed_at = Column(DateTime(timezone=True), nullable=True)
    sold_reason = Column(Text, nullable=True)
    # DeGiro sync fields (added migration 0026) --------------------------------
    # ISIN code for DeGiro-synced positions (e.g. "US0378331005")
    isin = Column(String(12), nullable=True)
    # DeGiro internal product ID for upsert deduplication
    degiro_product_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PortfolioTrade(Base):
    """A recorded buy or sell trade within a Portfolio, created automatically
    when positions are added/sold with cash tracking enabled, or manually via
    the cash adjustment endpoint.

    Attributes:
        trade_id:     Unique UUID for the trade record.
        portfolio_id: Parent portfolio UUID (CASCADE on portfolio delete).
        trade_type:   'BUY' or 'SELL'.
        ticker:       Ticker symbol of the traded asset.
        quantity:     Number of units traded.
        price:        Per-unit price at the time of the trade.
        cost_basis:   Average cost per unit at time of SELL (NULL for BUY trades).
                      Used to compute realized P&L: (price - cost_basis) * quantity.
        total_value:  quantity × price (pre-computed for display).
        notes:        Optional user note.
        created_at:   UTC timestamp when the record was created.
    """

    __tablename__ = "portfolio_trades"
    __table_args__ = (
        Index("ix_portfolio_trades_portfolio_id", "portfolio_id"),
    )

    trade_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id = Column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.portfolio_id", ondelete="CASCADE"),
        nullable=False,
    )
    trade_type = Column(String(10), nullable=False)   # 'BUY' or 'SELL'
    ticker = Column(String(20), nullable=False)
    quantity = Column(Numeric(18, 6), nullable=False)
    price = Column(Numeric(18, 4), nullable=False)
    # Average cost per unit captured at sell time; NULL on BUY trades
    cost_basis = Column(Numeric(18, 4), nullable=True)
    total_value = Column(Numeric(18, 4), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Back-reference to the owning Portfolio
    portfolio = relationship("Portfolio", back_populates="trades")


class DegiroTransaction(Base):
    """A single buy/sell transaction pulled from DeGiro account history."""

    __tablename__ = "degiro_transactions"

    transaction_id = Column(BigInteger, primary_key=True)
    portfolio_id = Column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.portfolio_id", ondelete="CASCADE"),
        nullable=False,
    )
    date = Column(DateTime(timezone=True), nullable=False)
    product_name = Column(Text, nullable=True)
    isin = Column(String(12), nullable=True)
    ticker = Column(String(20), nullable=True)
    buysell = Column(String(1), nullable=True)
    quantity = Column(Numeric(18, 6), nullable=True)
    price = Column(Numeric(18, 4), nullable=True)
    value = Column(Numeric(18, 4), nullable=True)
    currency = Column(String(8), nullable=True)
    total_in_base = Column(Numeric(18, 4), nullable=True)
    fee_in_base = Column(Numeric(18, 4), nullable=True)
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


# ── Trading AI Models ─────────────────────────────────────────────────────


class Strategy(Base):
    """Trading strategy definition (user-created, system built-in, or AI-learned)."""

    __tablename__ = "strategies"
    __table_args__ = (
        Index("idx_strategies_user_id", "user_id"),
        Index("idx_strategies_type", "strategy_type"),
        Index(
            "idx_strategies_public",
            "is_public",
            postgresql_where="is_public = TRUE",
        ),
    )

    strategy_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=True,  # NULL for system strategies
    )
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    strategy_type = Column(String(30), nullable=False)  # builtin | learned | pinescript | ml
    category = Column(String(30), nullable=True)  # trend_following | mean_reversion | momentum | breakout | volatility | ml_based | hybrid
    timeframe = Column(String(20), nullable=True)  # scalping | day_trading | swing | position
    asset_class = Column(String(20), nullable=True)  # stocks | etfs | futures | crypto
    definition_json = Column(JSONB, nullable=False)
    is_public = Column(Boolean, server_default="FALSE", nullable=False)
    is_system = Column(Boolean, server_default="FALSE", nullable=False)
    version = Column(Integer, server_default="1", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class StrategyVersion(Base):
    """Immutable snapshot of a strategy definition at a specific version."""

    __tablename__ = "strategy_versions"
    __table_args__ = (
        UniqueConstraint(
            "strategy_id", "version_number",
            name="uq_strategy_versions_strategy_version",
        ),
    )

    version_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_id = Column(
        UUID(as_uuid=True),
        ForeignKey("strategies.strategy_id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number = Column(Integer, nullable=False)
    definition_json = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BacktestResult(Base):
    """Queued or completed backtest job with full results and metrics."""

    __tablename__ = "backtest_results"
    __table_args__ = (
        Index("idx_backtest_results_user_id", "user_id"),
        Index("idx_backtest_results_strategy_id", "strategy_id"),
        Index("idx_backtest_results_status", "status"),
    )

    result_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    strategy_id = Column(
        UUID(as_uuid=True),
        ForeignKey("strategies.strategy_id", ondelete="SET NULL"),
        nullable=True,
    )
    symbol = Column(String(20), nullable=False)
    interval = Column(String(10), nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    parameters_json = Column(JSONB, nullable=True)
    commission_per_trade = Column(Numeric(10, 4), server_default="1.00", nullable=False)
    slippage_pct = Column(Numeric(6, 4), server_default="0.0005", nullable=False)
    results_json = Column(JSONB, nullable=True)  # Trades, equity curve, signals
    metrics_json = Column(JSONB, nullable=True)  # Sharpe, drawdown, win rate, etc.
    benchmark_json = Column(JSONB, nullable=True)  # Buy-and-hold + SPY comparison
    overfit_warning = Column(Boolean, server_default="FALSE", nullable=False)
    status = Column(String(20), server_default="pending", nullable=False)  # pending | running | completed | failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class TradingSignal(Base):
    """Forward-looking entry/exit/stop-loss signal generated by a strategy."""

    __tablename__ = "trading_signals"
    __table_args__ = (
        Index("idx_trading_signals_user_strategy", "user_id", "strategy_id"),
        Index("idx_trading_signals_symbol", "symbol"),
        Index(
            "idx_trading_signals_active",
            "is_active",
            postgresql_where="is_active = TRUE",
        ),
    )

    signal_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_id = Column(
        UUID(as_uuid=True),
        ForeignKey("strategies.strategy_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol = Column(String(20), nullable=False)
    signal_type = Column(String(10), nullable=False)  # entry | exit | stop_loss
    direction = Column(String(10), nullable=False)  # long | short
    price = Column(Numeric(18, 4), nullable=False)
    confidence = Column(Numeric(5, 2), nullable=True)  # 0.00–1.00
    reasoning = Column(Text, nullable=True)
    is_active = Column(Boolean, server_default="TRUE", nullable=False)
    triggered_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ── Social / Marketplace Models ─────────────────────────────────────────


class StrategyRating(Base):
    """User rating (1–5 stars) and optional review for a public strategy."""

    __tablename__ = "strategy_ratings"
    __table_args__ = (
        UniqueConstraint(
            "strategy_id", "user_id",
            name="uq_strategy_ratings_strategy_user",
        ),
        Index("idx_strategy_ratings_strategy_id", "strategy_id"),
    )

    rating_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_id = Column(
        UUID(as_uuid=True),
        ForeignKey("strategies.strategy_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    stars = Column(SmallInteger, nullable=False)
    review = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class StrategyUsage(Base):
    """Tracks when a user clones a strategy from the marketplace."""

    __tablename__ = "strategy_usage"
    __table_args__ = (
        Index("idx_strategy_usage_strategy_id", "strategy_id"),
    )

    usage_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_id = Column(
        UUID(as_uuid=True),
        ForeignKey("strategies.strategy_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    cloned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ── Price Alert Models ────────────────────────────────────────────────────


class PriceAlert(Base):
    """
    User-defined price alert. Triggers a notification when the target
    price condition is met during market hours.
    """

    __tablename__ = "price_alerts"
    __table_args__ = (
        Index("idx_price_alerts_user", "user_id"),
        Index(
            "idx_price_alerts_active",
            "user_id",
            postgresql_where="is_active = TRUE",
        ),
    )

    alert_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol = Column(String(20), nullable=False)
    condition = Column(String(10), nullable=False)      # "above", "below", "crosses"
    target_price = Column(Numeric(18, 4), nullable=False)
    note = Column(String(500), nullable=True)
    is_active = Column(Boolean, server_default="TRUE", nullable=False)
    triggered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ── Notification & Webhook Models ────────────────────────────────────────


class Notification(Base):
    """In-app notification delivered to a user (signal alerts, backtest results, etc.)."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index(
            "idx_notifications_user_unread",
            "user_id",
            postgresql_where="is_read = FALSE",
        ),
    )

    notification_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=True)
    is_read = Column(Boolean, server_default="FALSE", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserWebhook(Base):
    """User-configured webhook URL for outbound notification delivery."""

    __tablename__ = "user_webhooks"
    __table_args__ = (
        Index("idx_user_webhooks_user", "user_id"),
    )

    webhook_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    url = Column(Text, nullable=False)
    events = Column(JSONB, server_default="'[]'::jsonb", nullable=False)
    is_active = Column(Boolean, server_default="TRUE", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ── Paper Trading Models ─────────────────────────────────────────────────


class PaperTrade(Base):
    """Virtual paper trading session tracking simulated positions and equity."""

    __tablename__ = "paper_trades"
    __table_args__ = (
        Index("idx_paper_trades_user_id", "user_id"),
        Index("idx_paper_trades_status", "status"),
    )

    paper_trade_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    strategy_id = Column(UUID(as_uuid=True), ForeignKey("strategies.strategy_id", ondelete="SET NULL"), nullable=True)
    symbol = Column(String(20), nullable=False)
    initial_capital = Column(Numeric(18, 2), nullable=False)
    current_equity = Column(Numeric(18, 2), nullable=False)
    status = Column(String(20), server_default="active", nullable=False)
    parameters_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    stopped_at = Column(DateTime(timezone=True), nullable=True)


class PaperTradePosition(Base):
    """Individual position (open or closed) within a paper trade session."""

    __tablename__ = "paper_trade_positions"
    __table_args__ = (
        Index("idx_paper_positions_trade_id", "paper_trade_id"),
    )

    position_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_trade_id = Column(UUID(as_uuid=True), ForeignKey("paper_trades.paper_trade_id", ondelete="CASCADE"), nullable=False)
    side = Column(String(10), nullable=False)
    entry_price = Column(Numeric(18, 4), nullable=False)
    entry_date = Column(DateTime(timezone=True), nullable=False)
    exit_price = Column(Numeric(18, 4), nullable=True)
    exit_date = Column(DateTime(timezone=True), nullable=True)
    quantity = Column(Numeric(18, 6), nullable=False)
    pnl = Column(Numeric(18, 4), nullable=True)
    status = Column(String(20), server_default="open", nullable=False)


class PaperTradeEquitySnapshot(Base):
    """Point-in-time equity snapshot for charting paper trade performance."""

    __tablename__ = "paper_trade_equity_snapshots"
    __table_args__ = (
        Index("idx_paper_equity_trade_id", "paper_trade_id"),
    )

    snapshot_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_trade_id = Column(UUID(as_uuid=True), ForeignKey("paper_trades.paper_trade_id", ondelete="CASCADE"), nullable=False)
    equity = Column(Numeric(18, 4), nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ── Volume Flow Scanner Models ────────────────────────────────────────────


class ScanResult(Base):
    """Queued or completed Volume Flow Scanner job with full results.

    Stores the top-down scan output: active sectors, active industries,
    candidate stocks with scores and position sizing.
    """

    __tablename__ = "scan_results"
    __table_args__ = (
        Index("idx_scan_results_user_id", "user_id"),
        Index("idx_scan_results_status", "status"),
    )

    result_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    # Scan parameters — e.g. {"portfolio_value_usd": 10000}
    parameters_json = Column(JSONB, nullable=True)
    # Full scan output — active_sectors, active_industries, candidates, counts, duration
    results_json = Column(JSONB, nullable=True)
    status = Column(String(20), server_default="pending", nullable=False)  # pending | running | complete | error
    error_message = Column(Text, nullable=True)
    # Highest phase successfully completed (1–3); null until the job finishes
    phase_reached = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    # How the scan was initiated: 'auto' | 'live' | 'prev-day' (added migration 0025)
    mode = Column(String(16), nullable=False, default="auto")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ── Rule Alert Models ─────────────────────────────────────────────────────


class RuleAlert(Base):
    """Rule-engine alert triggered when a portfolio position violates a rule.

    Alerts are linked to a user and optionally to a specific position (soft
    reference — position_id is stored as an integer for forward-compatibility
    but carries no FK constraint because portfolio_positions uses a UUID PK).

    Lifecycle states: active → snoozed → actioned | expired.
    Severity levels: info, warning, critical.

    Indexes:
        idx_rule_alerts_user_active  — fetch active alerts per user (descending).
        idx_rule_alerts_position     — look up alerts by position and rule type.
    """

    __tablename__ = "rule_alerts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    # Soft reference to portfolio_positions (UUID PK); no FK constraint in DB
    position_id = Column(BigInteger, nullable=True)
    portfolio_id = Column(BigInteger, nullable=True)
    rule_type = Column(String(32), nullable=False)
    severity = Column(String(10), nullable=False)   # info | warning | critical
    title = Column(String(200), nullable=True)
    body = Column(Text, nullable=True)
    triggered_value = Column(Numeric(18, 4), nullable=True)
    state = Column(String(16), nullable=False, default="active")  # active | snoozed | actioned | expired
    snoozed_until = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ── Trade Analysis Models ─────────────────────────────────────────────────


class TradeAnalysis(Base):
    """AI-generated trade analysis for a ticker, optionally linked to a position.

    Captures the full lifecycle of an Ollama-driven analysis: the market data
    and rules used as input, the recommendation produced, suggested entry/stop/
    target levels, and post-trade outcome data for learning and evaluation.

    Attributes:
        analysis_id:           UUID primary key.
        position_id:           Optional FK to portfolio_positions (SET NULL on delete).
        portfolio_id:          Optional FK to portfolios (CASCADE on delete).
        ticker:                Ticker symbol analysed (e.g. "AAPL").
        requested_at:          UTC timestamp when the analysis was requested.
        rules_snapshot:        Snapshot of investment_rules.json at analysis time.
        market_data_snapshot:  Price, RSI, SMA50, SMA200, PE, sector, etc.
        analysis_json:         Full Ollama response payload.
        recommendation:        BUY | HOLD | AVOID | WATCH.
        suggested_entry:       Suggested entry price.
        suggested_stop:        Suggested stop-loss price.
        suggested_target:      Suggested price target.
        risk_reward_ratio:     Pre-computed risk/reward ratio.
        actual_entry:          Actual entry price (filled when position opened).
        actual_exit:           Actual exit price (filled when position closed).
        actual_pnl_pct:        Realised P&L percentage (filled post-close).
        outcome:               WIN | LOSS | BREAK_EVEN | OPEN.
        evaluation_json:       Ollama post-trade critique payload.
        chromadb_id:           ChromaDB embedding document ID.
        created_at:            UTC timestamp when the record was inserted.
    """

    __tablename__ = "trade_analyses"

    analysis_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    position_id = Column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_positions.position_id", ondelete="SET NULL"),
        nullable=True,
    )
    portfolio_id = Column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.portfolio_id", ondelete="CASCADE"),
        nullable=True,
    )
    ticker = Column(String(20), nullable=False)
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    rules_snapshot = Column(JSON, nullable=True)
    market_data_snapshot = Column(JSON, nullable=True)
    analysis_json = Column(JSON, nullable=True)
    recommendation = Column(String(16), nullable=True)
    suggested_entry = Column(Numeric(18, 4), nullable=True)
    suggested_stop = Column(Numeric(18, 4), nullable=True)
    suggested_target = Column(Numeric(18, 4), nullable=True)
    risk_reward_ratio = Column(Numeric(8, 2), nullable=True)
    actual_entry = Column(Numeric(18, 4), nullable=True)
    actual_exit = Column(Numeric(18, 4), nullable=True)
    actual_pnl_pct = Column(Numeric(8, 4), nullable=True)
    outcome = Column(String(16), nullable=True)
    evaluation_json = Column(JSON, nullable=True)
    chromadb_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RuleRefinement(Base):
    """AI-generated rule change suggestion from weekly meta-analysis.

    Status: pending → approved | rejected.
    Rules never auto-update — user must approve via /approve_refinement bot command.
    """

    __tablename__ = "rule_refinements"

    refinement_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=True)
    period_end = Column(DateTime(timezone=True), nullable=True)
    trade_count = Column(Integer, nullable=True)
    win_rate_pct = Column(Numeric(5, 2), nullable=True)
    avg_pnl_pct = Column(Numeric(8, 4), nullable=True)
    pattern_summary = Column(Text, nullable=True)
    suggested_rules = Column(JSONB, nullable=True)
    raw_ollama_response = Column(Text, nullable=True)
    status = Column(String(16), server_default="pending", nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class InsiderFiling(Base):
    """One non-derivative Form 4 transaction ingested from EDGAR.

    Dedup is (accession, txn_index). Telegram is sent at most once per accession
    (notified_at). Cluster queries use ticker + transaction_code + date window.
    """

    __tablename__ = "insider_filings"
    __table_args__ = (
        UniqueConstraint("accession", "txn_index", name="uq_insider_filings_accession_txn"),
        Index("idx_insider_filings_ticker_code_date", "ticker", "transaction_code", "transaction_date"),
        Index("idx_insider_filings_accession", "accession"),
        Index(
            "idx_insider_filings_owner_hist",
            "owner_cik",
            "ticker",
            "transaction_code",
            "transaction_date",
        ),
    )

    filing_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    accession = Column(String(25), nullable=False)
    txn_index = Column(Integer, nullable=False, server_default="0")
    ticker = Column(String(20), nullable=False)
    issuer_cik = Column(String(10), nullable=True)
    owner_name = Column(String(256), nullable=True)
    owner_cik = Column(String(10), nullable=True)
    is_director = Column(Boolean, nullable=False, server_default="false")
    is_officer = Column(Boolean, nullable=False, server_default="false")
    is_ten_percent = Column(Boolean, nullable=False, server_default="false")
    officer_title = Column(String(128), nullable=True)
    transaction_code = Column(String(4), nullable=False)
    acquired_disposed = Column(String(1), nullable=True)
    shares = Column(Numeric(18, 4), nullable=True)
    price = Column(Numeric(18, 4), nullable=True)
    notional = Column(Numeric(18, 2), nullable=True)
    shares_after = Column(Numeric(18, 4), nullable=True)
    stake_pct = Column(Numeric(8, 6), nullable=True)
    transaction_date = Column(Date, nullable=True)
    is_10b5_1 = Column(Boolean, nullable=True)
    filing_url = Column(Text, nullable=True)
    notified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ShortInterestSnapshot(Base):
    """One ticker's biweekly short-interest reading from FINRA (Rule 4560).

    FINRA publishes a market-wide flat file (thousands of tickers) every
    two weeks with a ~2-3 week lag — finra_short_interest.py downloads the
    whole file but only keeps rows for tickers we actually track (open
    positions + anything with an insider filing on record), not the full
    market. Dedup is (ticker, settlement_date): the poller re-checks for a
    newer settlement date each cycle but never re-stores one already on file.

    Used to add squeeze/crowding context to insider alert advice — e.g. a
    high days_to_cover on a name with a fresh insider buy is a different
    setup than the same buy with negligible short interest.
    """

    __tablename__ = "short_interest_snapshots"
    __table_args__ = (
        UniqueConstraint("ticker", "settlement_date", name="uq_short_interest_ticker_date"),
        Index("idx_short_interest_ticker", "ticker"),
    )

    snapshot_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(20), nullable=False)
    settlement_date = Column(Date, nullable=False)
    current_short_position = Column(Numeric(20, 2), nullable=True)
    previous_short_position = Column(Numeric(20, 2), nullable=True)
    average_daily_volume = Column(Numeric(20, 2), nullable=True)
    days_to_cover = Column(Numeric(10, 2), nullable=True)
    change_percent = Column(Numeric(8, 2), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Form144Notice(Base):
    """One Form 144 (Notice of Proposed Sale) ingested from EDGAR.

    A leading indicator for insider Form 4 sells — filed before or on the
    day of a proposed sale of restricted/control stock, stating the exact
    share count and intended sale date. Ticker isn't embedded in the XML
    (unlike Form 4's issuerTradingSymbol), so it's resolved from issuer_cik
    via cik_ticker_map.py at ingest time; a null ticker means resolution
    failed and the row is kept CIK-only rather than dropped.

    Dedup is accession (one notice per filing, unlike Form 4's multi-row
    shape). Correlated against InsiderFiling by (owner_cik, ticker) in
    insider_monitor.py to give a sell alert's advice section a "this was
    pre-announced" note instead of treating every sale as a surprise.
    """

    __tablename__ = "form144_notices"
    __table_args__ = (
        UniqueConstraint("accession", name="uq_form144_notices_accession"),
        Index("idx_form144_notices_owner_ticker", "owner_cik", "ticker"),
        Index("idx_form144_notices_ticker", "ticker"),
    )

    notice_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    accession = Column(String(25), nullable=False)
    ticker = Column(String(20), nullable=True)
    issuer_cik = Column(String(10), nullable=True)
    issuer_name = Column(String(256), nullable=True)
    owner_cik = Column(String(10), nullable=True)
    owner_name = Column(String(256), nullable=True)
    relationships = Column(String(128), nullable=True)
    broker = Column(String(256), nullable=True)
    shares = Column(Numeric(18, 4), nullable=True)
    aggregate_value = Column(Numeric(18, 2), nullable=True)
    approx_sale_date = Column(Date, nullable=True)
    notice_date = Column(Date, nullable=True)
    filing_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Form3Statement(Base):
    """One Form 3 (Initial Statement of Beneficial Ownership) ingested from
    EDGAR — filed when someone *becomes* an insider (new officer, director,
    or 10%+ owner), stating their starting position before any Form 4
    activity exists.

    Same ownershipDocument XML family as Form 4 (parse_form3_xml reuses its
    helpers) — a single point-in-time holding, not a transaction, so there's
    no price/date/code, just shares_owned as of period_of_report.

    Gives a baseline for a first-ever Form 4 sale — insider_monitor.py's
    sell-gate path correlates by (owner_cik, ticker) and computes what
    fraction of this starting position a sale represents ("sold 10% of
    initial grant" vs "sold 80%").
    """

    __tablename__ = "form3_statements"
    __table_args__ = (
        UniqueConstraint("accession", name="uq_form3_statements_accession"),
        Index("idx_form3_statements_owner_ticker", "owner_cik", "ticker"),
    )

    statement_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    accession = Column(String(25), nullable=False)
    ticker = Column(String(20), nullable=False)
    issuer_cik = Column(String(10), nullable=True)
    owner_name = Column(String(256), nullable=True)
    owner_cik = Column(String(10), nullable=True)
    is_director = Column(Boolean, nullable=False, server_default="false")
    is_officer = Column(Boolean, nullable=False, server_default="false")
    is_ten_percent = Column(Boolean, nullable=False, server_default="false")
    officer_title = Column(String(128), nullable=True)
    shares_owned = Column(Numeric(18, 4), nullable=True)
    period_of_report = Column(Date, nullable=True)
    filing_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BeneficialOwnership(Base):
    """One reporting person's row from a Schedule 13D or 13G ingested from
    EDGAR — beneficial ownership >5% of a public company's shares.

    13D = "activist" intent (may seek control/board seats, states a
    purpose in purpose_text). 13G = passive investor (index funds, most
    institutions), same 5% threshold, no intent language — purpose_text is
    always null for these.

    One row per reporting person, not per filing: a 13D can be a joint
    "group" filing naming several people/entities on one cover page (see
    schedule13_edgar.py), each with their own shares_owned/pct_owned.
    Dedup is (accession, person_index). Ticker isn't embedded in either
    schema (only CUSIP) — resolved from issuer_cik via cik_ticker_map.py,
    same as Form 144.

    Surfaced ticker-wide (not owner-correlated like Form 144/3 — 13D/13G
    filers are typically institutions/activists, not the same individuals
    filing Form 4s) as general market color on insider alerts for that name.
    """

    __tablename__ = "beneficial_ownership"
    __table_args__ = (
        UniqueConstraint("accession", "person_index", name="uq_beneficial_ownership_accession_person"),
        Index("idx_beneficial_ownership_ticker", "ticker"),
    )

    ownership_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    accession = Column(String(25), nullable=False)
    person_index = Column(Integer, nullable=False, server_default="0")
    is_13d = Column(Boolean, nullable=False, server_default="true")
    is_amendment = Column(Boolean, nullable=False, server_default="false")
    ticker = Column(String(20), nullable=True)
    issuer_cik = Column(String(10), nullable=True)
    issuer_name = Column(String(256), nullable=True)
    filer_cik = Column(String(10), nullable=True)
    filer_name = Column(String(256), nullable=True)
    shares_owned = Column(Numeric(20, 4), nullable=True)
    pct_owned = Column(Numeric(8, 4), nullable=True)
    event_date = Column(Date, nullable=True)
    purpose_text = Column(Text, nullable=True)
    filing_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EightKFiling(Base):
    """One Form 8-K (Material Event) ingested from EDGAR, for tracked
    tickers only.

    Unlike Form 4/144/3/13D-13G, item codes (which material event
    triggered the filing — M&A, executive changes, earnings, bankruptcy,
    etc.) come straight from EDGAR's getcurrent atom <summary> text, not a
    per-filing XML/document fetch — see form8k_edgar.py. 8-K volume is
    dozens per 5-minute tick across every US issuer, so form8k_monitor.py
    resolves each entry's issuer CIK to a ticker and discards anything not
    already tracked (open positions + insider filers) *before* storing —
    this table only ever holds filings for names the user actually cares
    about, never the market-wide firehose.

    items is a JSONB list of {"code": "5.02", "description": "..."} — kept
    as-is rather than normalized into a join table since it's small and
    read-only display data, not queried by item code anywhere yet.
    """

    __tablename__ = "eight_k_filings"
    __table_args__ = (
        UniqueConstraint("accession", name="uq_eight_k_filings_accession"),
        Index("idx_eight_k_filings_ticker", "ticker"),
    )

    filing_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    accession = Column(String(25), nullable=False)
    ticker = Column(String(20), nullable=False)
    issuer_cik = Column(String(10), nullable=True)
    issuer_name = Column(String(256), nullable=True)
    is_amendment = Column(Boolean, nullable=False, server_default="false")
    items = Column(JSONB, nullable=True)
    filed_at = Column(DateTime(timezone=True), nullable=True)
    filing_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Form13FHolding(Base):
    """One tracked-ticker holding from a Form 13F-HR (quarterly
    institutional holdings, >$100M AUM, filed 45 days after quarter-end).

    Positioning data, not a trading signal — filings roll in as a burst
    around the 45-day deadline, not evenly through the quarter, and can
    already be over a month stale the day they're filed. Reported by CUSIP,
    not ticker — resolved via cusip_ticker_map.py (the free OpenFIGI API),
    since 13F's own schema (verified live) doesn't reliably expose a
    composite/exchange-level FIGI the same lookup could use directly.

    form13f_monitor.py resolves every CUSIP in a filing's information
    table and discards holdings that don't match an already-tracked ticker
    (open positions + insider filers) before storing — same "filter before
    storing" principle as Form 8-K, since a single filer can hold hundreds
    of positions. One row per (accession, cusip): a filer's information
    table lists each holding once.
    """

    __tablename__ = "form13f_holdings"
    __table_args__ = (
        UniqueConstraint("accession", "cusip", name="uq_form13f_holdings_accession_cusip"),
        Index("idx_form13f_holdings_ticker", "ticker"),
    )

    holding_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    accession = Column(String(25), nullable=False)
    filer_cik = Column(String(10), nullable=True)
    filer_name = Column(String(256), nullable=True)
    ticker = Column(String(20), nullable=False)
    cusip = Column(String(9), nullable=False)
    issuer_name = Column(String(256), nullable=True)
    shares = Column(Numeric(20, 2), nullable=True)
    value_usd = Column(Numeric(20, 2), nullable=True)
    is_amendment = Column(Boolean, nullable=False, server_default="false")
    filed_at = Column(DateTime(timezone=True), nullable=True)
    filing_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
