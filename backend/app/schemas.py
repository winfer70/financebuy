"""
schemas.py — Pydantic request/response schemas for TickerTap API.

All schemas include field-level validation constraints and descriptions
so that the auto-generated OpenAPI docs are meaningful to API consumers.

Conventions:
  - *Create schemas: input validation (strict types, ranges, enums)
  - *Out schemas: output serialisation (orm_mode = True)
  - Sensitive fields (password_hash, raw tokens) are never included in *Out
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ── User schemas ─────────────────────────────────────────────────────────────

class UserBase(BaseModel):
    """Shared fields for user create / update operations."""

    email: EmailStr = Field(..., description="User's email address (must be unique).", example="alice@example.com")
    first_name: Optional[str] = Field(None, max_length=100, description="First name.", example="Alice")
    last_name: Optional[str] = Field(None, max_length=100, description="Last name.", example="Smith")
    phone: Optional[str] = Field(None, max_length=20, description="Phone number in E.164 format.", example="+15551234567")


class UserCreate(UserBase):
    """Registration payload — password is hashed before storage."""

    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Plaintext password (8–128 characters). Will be hashed with argon2id.",
        example="Str0ng!Pass",
    )


class UserOut(UserBase):
    """Serialised user returned by the API — no password hash included."""

    user_id: UUID = Field(..., description="Unique user identifier.")
    kyc_status: str = Field(..., description="KYC verification status: pending | approved | rejected.")
    is_active: bool = Field(..., description="Whether the account is active and can authenticate.")

    class Config:
        orm_mode = True


class UserLogin(BaseModel):
    """Login credentials."""

    email: EmailStr = Field(..., description="Registered email address.", example="alice@example.com")
    password: str = Field(..., description="Account password.", example="Str0ng!Pass")


# ── Account schemas ───────────────────────────────────────────────────────────

class AccountCreate(BaseModel):
    """Payload to open a new brokerage account."""

    account_type: str = Field(
        ...,
        description="Account category, e.g. 'individual', 'ira', 'margin'.",
        example="individual",
    )
    currency: Optional[str] = Field(
        "USD",
        min_length=3,
        max_length=3,
        description="ISO 4217 three-letter currency code.",
        example="USD",
    )


class AccountOut(BaseModel):
    """Serialised account returned by the API."""

    account_id: UUID = Field(..., description="Unique account identifier.")
    account_type: str = Field(..., description="Account category.")
    account_number: str = Field(..., description="Human-readable account reference number.")
    balance: Decimal = Field(..., max_digits=18, decimal_places=2, description="Current cash balance.")
    currency: str = Field(..., description="Account currency (ISO 4217).")
    status: str = Field(..., description="Account status: active | locked | closed.")

    class Config:
        orm_mode = True


# ── Transaction schemas ───────────────────────────────────────────────────────

_VALID_TRANSACTION_TYPES = {"deposit", "withdrawal"}


class TransactionCreate(BaseModel):
    """Payload to create a deposit or withdrawal (P7.4 — field validation added)."""

    account_id: UUID = Field(
        ...,
        description="UUID of the account to credit or debit.",
    )
    transaction_type: Literal["deposit", "withdrawal"] = Field(
        ...,
        description="Transaction direction: 'deposit' (credit) or 'withdrawal' (debit).",
        example="deposit",
    )
    amount: Decimal = Field(
        ...,
        gt=Decimal("0"),
        max_digits=18,
        decimal_places=2,
        description="Transaction amount — must be strictly greater than zero.",
        example="1000.00",
    )
    currency: Optional[str] = Field(
        "USD",
        min_length=3,
        max_length=3,
        description="ISO 4217 currency code (default USD).",
        example="USD",
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional human-readable description for this transaction.",
        example="Monthly deposit",
    )
    reference_number: Optional[str] = Field(
        None,
        max_length=100,
        description="Optional unique external reference (e.g. wire transfer ID).",
    )


class TransactionOut(TransactionCreate):
    """Serialised transaction returned by the API."""

    transaction_id: UUID = Field(..., description="Unique transaction identifier.")
    status: str = Field(..., description="Transaction status: pending | completed | failed.")
    created_at: Optional[str] = Field(None, description="ISO-8601 creation timestamp.")

    class Config:
        orm_mode = True


# ── Token / Auth schemas ──────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    """Authentication response containing the short-lived access token.

    The long-lived refresh token is set as an httpOnly cookie and is NOT
    included in this response body.
    """

    access_token: str = Field(..., description="Signed JWT access token (60-minute lifetime).")
    token_type: str = Field("bearer", description="Token type, always 'bearer'.")
    user_id: Optional[UUID] = Field(None, description="Authenticated user's UUID.")
    email: Optional[str] = Field(None, description="Authenticated user's email.")
    first_name: Optional[str] = Field(None, description="Authenticated user's first name.")
    last_name: Optional[str] = Field(None, description="Authenticated user's last name.")


# ── Portfolio / Holdings schemas ──────────────────────────────────────────────

class HoldingPositionOut(BaseModel):
    """Enriched holding position with live market data."""

    account_id: UUID
    security_id: UUID
    symbol: str = Field(..., description="Ticker symbol, e.g. 'AAPL'.")
    name: str = Field(..., description="Full security name.")
    quantity: Decimal = Field(..., max_digits=18, decimal_places=6, description="Units held.")
    average_cost: Optional[Decimal] = Field(None, description="Average cost basis per unit.")
    current_price: Optional[Decimal] = Field(None, description="Most recent market price.")
    market_value: Decimal = Field(..., max_digits=18, decimal_places=2, description="quantity × current_price.")
    currency: str = Field(..., description="Position currency (ISO 4217).")
    security_type: Optional[str] = Field(None, description="Asset category (stock, etf, crypto, etc.).")


class AccountPortfolioSummary(BaseModel):
    """Portfolio summary for a single account."""

    account_id: UUID
    account_type: str
    currency: str
    cash_balance: Decimal = Field(..., max_digits=18, decimal_places=2)
    positions_value: Decimal = Field(..., max_digits=18, decimal_places=2)
    total_value: Decimal = Field(..., max_digits=18, decimal_places=2)


class PortfolioSummary(BaseModel):
    """Aggregated portfolio summary across all accounts."""

    accounts: list[AccountPortfolioSummary]
    total_portfolio_value: Decimal = Field(..., max_digits=18, decimal_places=2)
    # For now we assume a single primary currency; mixed-currency
    # portfolios can be represented by per-account currencies above.
    currency: str = "USD"


# ── Order schemas ─────────────────────────────────────────────────────────────

class OrderCreate(BaseModel):
    """Payload to place a market or limit order (P7.5 — field validation added)."""

    account_id: UUID = Field(..., description="UUID of the account to place the order against.")
    security_id: UUID = Field(..., description="UUID of the security to trade.")
    order_type: Literal["market", "limit"] = Field(
        ...,
        description="Order execution type: 'market' (immediate) or 'limit' (at specified price).",
        example="market",
    )
    side: Literal["buy", "sell"] = Field(
        ...,
        description="Order direction: 'buy' to purchase or 'sell' to liquidate.",
        example="buy",
    )
    quantity: Decimal = Field(
        ...,
        gt=Decimal("0"),
        max_digits=18,
        decimal_places=6,
        description="Number of units to trade — must be strictly greater than zero.",
        example="10.000000",
    )
    price: Decimal = Field(
        ...,
        gt=Decimal("0"),
        max_digits=18,
        decimal_places=2,
        description="Execution price per unit — must be strictly greater than zero.",
        example="150.00",
    )


class OrderOut(BaseModel):
    """Serialised order returned by the API."""

    order_id: UUID
    account_id: UUID
    security_id: UUID
    order_type: str
    side: str
    quantity: Decimal = Field(..., max_digits=18, decimal_places=6)
    price: Decimal = Field(..., max_digits=18, decimal_places=2)
    status: str = Field(..., description="Order status: pending | filled | cancelled | rejected.")
    filled_quantity: Decimal = Field(..., max_digits=18, decimal_places=6)
    filled_price: Decimal | None = Field(default=None, max_digits=18, decimal_places=2)
    symbol: str | None = Field(None, description="Resolved ticker symbol.")
    placed_at: Optional[str] = Field(None, description="ISO-8601 placement timestamp.")

    class Config:
        orm_mode = True


# ── Password reset schemas ────────────────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    """Request to initiate a password reset flow."""

    email: EmailStr = Field(..., description="Email address associated with the account.", example="alice@example.com")


class ResetPasswordRequest(BaseModel):
    """Payload to consume a reset token and set a new password."""

    token: str = Field(..., description="Raw reset token received via email link.")
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="New plaintext password (8–128 characters).",
        example="NewStr0ng!Pass",
    )


# ── Audit log schema ──────────────────────────────────────────────────────────

class AuditLogOut(BaseModel):
    """Serialised audit log entry for admin review."""

    log_id: int = Field(..., description="Auto-incremented log entry identifier.")
    user_id: Optional[UUID] = Field(None, description="User who performed the action.")
    action: str = Field(..., description="Action name, e.g. 'login_success', 'transaction_create'.")
    table_name: Optional[str] = Field(None, description="Database table affected.")
    record_id: Optional[UUID] = Field(None, description="Primary key of the affected record.")
    old_values: Optional[Dict[str, Any]] = Field(None, description="State before the action.")
    new_values: Optional[Dict[str, Any]] = Field(None, description="State after the action.")
    ip_address: Optional[str] = Field(None, description="Requester IP address.")
    user_agent: Optional[str] = Field(None, description="Requester User-Agent header.")
    created_at: datetime = Field(..., description="ISO-8601 timestamp of the action.")

    class Config:
        orm_mode = True


# ── Portfolio Manager schemas ─────────────────────────────────────────────────

class PortfolioCreate(BaseModel):
    """Payload to create a named portfolio."""

    name: str = Field(..., min_length=1, max_length=128, description="Portfolio name.", example="Tech Portfolio")
    strategy: Optional[str] = Field(None, max_length=2000, description="Optional strategy description.", example="Long-term tech picks")


class PortfolioOut(BaseModel):
    """Serialised portfolio returned by the API."""

    portfolio_id: UUID = Field(..., description="Unique portfolio identifier.")
    name: str
    strategy: Optional[str] = None
    created_at: datetime

    class Config:
        orm_mode = True


class PositionCreate(BaseModel):
    """Payload to add a single position to a portfolio."""

    ticker: str = Field(..., min_length=1, max_length=20, description="Ticker symbol.", example="AAPL")
    name: Optional[str] = Field(None, max_length=256, description="Company/security name.", example="Apple Inc.")
    quantity: Decimal = Field(..., gt=Decimal("0"), max_digits=18, decimal_places=6, description="Number of shares/units.", example="10.0")
    purchase_date: Optional[datetime] = Field(None, description="Date the position was entered.", example="2023-01-15T00:00:00Z")
    purchase_price: Decimal = Field(..., gt=Decimal("0"), max_digits=18, decimal_places=2, description="Break-even price per unit.", example="155.00")
    group_tag: Optional[str] = Field(None, max_length=64, description="Optional group/label for the position.", example="Core")
    asset_type: str = Field("stock", description="Asset type: stock, crypto, etf, or physical.", example="stock")
    physical_type: Optional[str] = Field(None, max_length=20, description="Physical asset sub-type: coin or bar.", example="coin")
    stop_loss: Optional[Decimal] = Field(None, gt=Decimal("0"), max_digits=18, decimal_places=2, description="Stop-loss price trigger.", example="140.00")


class PositionOut(BaseModel):
    """Serialised position returned by the API."""

    position_id: UUID
    portfolio_id: UUID
    ticker: str
    name: Optional[str] = None
    quantity: Decimal = Field(..., max_digits=18, decimal_places=6)
    purchase_date: Optional[datetime] = None
    purchase_price: Decimal = Field(..., max_digits=18, decimal_places=2)
    group_tag: Optional[str] = None
    is_excluded: bool
    asset_type: str = "stock"
    physical_type: Optional[str] = None
    stop_loss: Optional[Decimal] = Field(None, max_digits=18, decimal_places=2)
    created_at: datetime

    class Config:
        orm_mode = True


class PositionUpdate(BaseModel):
    """Payload for partial position update — all fields optional."""

    quantity: Optional[Decimal] = Field(None, gt=Decimal("0"), max_digits=18, decimal_places=6)
    purchase_price: Optional[Decimal] = Field(None, gt=Decimal("0"), max_digits=18, decimal_places=2)
    group_tag: Optional[str] = Field(None, max_length=64)
    is_excluded: Optional[bool] = None
    stop_loss: Optional[Decimal] = Field(None, max_digits=18, decimal_places=2)


class SellRequest(BaseModel):
    """Payload for a partial sell — reduces quantity; deletes if fully sold."""

    quantity: Decimal = Field(..., gt=Decimal("0"), max_digits=18, decimal_places=6, description="Units to sell.")


# ── Chart Template schemas ────────────────────────────────────────────────────

class ChartTemplateCreate(BaseModel):
    """Payload to save a chart template."""

    name: str = Field(..., min_length=1, max_length=128, description="Template name.", example="AAPL Fibonacci Setup")
    symbol: Optional[str] = Field(None, max_length=20, description="Associated ticker symbol (null for universal).")
    interval: Optional[str] = Field(None, max_length=10, description="Chart interval, e.g. '1d', '1h'.")
    drawings_json: List[Dict[str, Any]] = Field(default_factory=list, description="Array of drawing objects.")
    overlays_json: Optional[Dict[str, Any]] = Field(None, description="Overlay configuration (SMA toggles, etc.).")


class ChartTemplateOut(BaseModel):
    """Serialised chart template returned by the API."""

    template_id: UUID
    name: str
    symbol: Optional[str] = None
    interval: Optional[str] = None
    drawings_json: List[Dict[str, Any]] = Field(default_factory=list)
    overlays_json: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class ChartTemplateUpdate(BaseModel):
    """Payload for partial chart template update."""

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    symbol: Optional[str] = Field(None, max_length=20)
    interval: Optional[str] = Field(None, max_length=10)
    drawings_json: Optional[List[Dict[str, Any]]] = None
    overlays_json: Optional[Dict[str, Any]] = None


# ── News schemas ─────────────────────────────────────────────────────────────


class TickerScoreOut(BaseModel):
    """Per-ticker impact score returned alongside a news article."""

    ticker: str = Field(..., description="Stock ticker symbol (e.g. 'NVDA').")
    score: int = Field(
        ...,
        ge=-5,
        le=5,
        description="Ticker-specific impact score (-5 extremely bearish to +5 extremely bullish).",
    )
    reasoning: Optional[str] = Field(
        None,
        description="One-sentence LLM explanation of the impact on this ticker.",
    )


class TickerScoreIngest(BaseModel):
    """Per-ticker score submitted by the LLM worker via the internal API."""

    ticker: str = Field(
        ..., min_length=1, max_length=20, description="Ticker symbol."
    )
    score: int = Field(
        ..., ge=-5, le=5, description="Impact score for this ticker (-5 to +5)."
    )
    reasoning: Optional[str] = Field(
        None, description="One-sentence LLM explanation."
    )


class NewsArticleIngest(BaseModel):
    """Single article submitted by the LLM worker via POST /api/v1/internal/news."""

    url: str = Field(..., description="Full URL to the original article.")
    title: str = Field(..., description="Article headline text.")
    summary: Optional[str] = Field(
        None, max_length=500, description="Short description / first ~200 chars."
    )
    source: str = Field(
        ..., description="Source identifier: 'yahoo', 'google', 'finviz', or 'marketwatch'.",
    )
    published_at: Optional[datetime] = Field(
        None, description="Original publication time (ISO-8601 with timezone)."
    )
    general_score: int = Field(
        ..., ge=-5, le=5, description="General market impact score (-5 to +5)."
    )
    general_reasoning: Optional[str] = Field(
        None, description="One-sentence LLM explanation of the general market impact."
    )
    tickers: List[TickerScoreIngest] = Field(
        default_factory=list,
        description="Per-ticker impact scores identified by the LLM.",
    )


class NewsArticleOut(BaseModel):
    """Serialised news article returned by the news feed endpoints.

    Each article carries a general market impact score from the LLM and
    optionally per-ticker scores.  The ``score`` and ``reasoning`` fields
    reflect the most relevant score: ticker-specific when the article
    matches a user's portfolio, otherwise the general market score.
    """

    title: str = Field(..., description="Article headline text.")
    url: str = Field(..., description="Full URL to the original article.")
    source: str = Field(
        ...,
        description="Source identifier: 'yahoo', 'google', 'finviz', or 'marketwatch'.",
    )
    published_at: Optional[datetime] = Field(
        None, description="UTC publication timestamp, or null if unavailable."
    )
    score: int = Field(
        0,
        ge=-5,
        le=5,
        description="Most relevant impact score: ticker-specific if in portfolio, otherwise general (-5 to +5).",
    )
    reasoning: Optional[str] = Field(
        None,
        description="LLM explanation for the displayed score.",
    )
    ticker_scores: List[TickerScoreOut] = Field(
        default_factory=list,
        description="All per-ticker impact scores for drill-down.",
    )
    in_portfolio: bool = Field(
        False,
        description="True if any associated ticker belongs to the user's portfolios.",
    )
    summary: Optional[str] = Field(
        None,
        max_length=500,
        description="Short description of the article, if available.",
    )


# ── Feedback loop schemas ────────────────────────────────────────────────────


class ScoreOutcomeOut(BaseModel):
    """Serialised score outcome returned by the feedback data endpoint.

    Includes denormalised article fields so the learner can analyse patterns
    without a separate article fetch.
    """

    outcome_id: UUID
    article_id: UUID
    ticker: str = Field(..., description="Ticker symbol, or 'SPY' for general score.")
    score_type: str = Field(..., description="'general' or 'ticker'.")
    predicted_score: int = Field(..., ge=-5, le=5, description="Original LLM score.")
    predicted_reasoning: Optional[str] = None
    price_at_score: Optional[Decimal] = Field(None, description="Close price on scoring day.")
    price_after: Optional[Decimal] = Field(None, description="Close price next trading day.")
    actual_change_pct: Optional[Decimal] = Field(None, description="Actual % change.")
    accuracy_grade: str = Field(..., description="'correct', 'close', 'wrong', or 'opposite'.")
    scored_at: datetime
    checked_at: datetime
    # Denormalised article context for the learner.
    article_title: Optional[str] = None
    article_summary: Optional[str] = None
    article_source: Optional[str] = None

    class Config:
        orm_mode = True


class ScoringRuleCreate(BaseModel):
    """Payload from the learner to submit new calibration rules."""

    rules_text: str = Field(
        ..., min_length=10, description="Scoring rules to inject into the LLM prompt."
    )
    analysis_summary: Optional[str] = Field(
        None, description="Summary of patterns the learner found in the data."
    )
    sample_size: Optional[int] = Field(
        None, ge=0, description="Number of outcome records analysed."
    )
    accuracy_before: Optional[Decimal] = Field(
        None, description="Overall accuracy % before this rule set."
    )


class ScoringRuleOut(BaseModel):
    """Serialised scoring rule returned by the rules endpoint."""

    rule_id: UUID
    rule_version: int
    rules_text: str
    analysis_summary: Optional[str] = None
    sample_size: Optional[int] = None
    accuracy_before: Optional[Decimal] = None
    is_active: bool
    generated_at: datetime

    class Config:
        orm_mode = True


class TrainingPairOut(BaseModel):
    """Export format for future LoRA fine-tuning (Approach 3 migration).

    Each record maps an article input to the original LLM prediction and a
    corrected output derived from actual price movements.
    """

    instruction: str = Field(..., description="System prompt for the model.")
    input_text: str = Field(..., description="Article headline + summary.")
    original_output: Dict[str, Any] = Field(..., description="Original LLM prediction.")
    corrected_output: Dict[str, Any] = Field(..., description="Score derived from actual price data.")
    actual_change_pct: Optional[Decimal] = None
    accuracy_grade: str
