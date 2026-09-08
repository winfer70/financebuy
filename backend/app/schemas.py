"""
schemas.py — Pydantic request/response schemas for TickerTap API.

All schemas include field-level validation constraints and descriptions
so that the auto-generated OpenAPI docs are meaningful to API consumers.

Conventions:
  - *Create schemas: input validation (strict types, ranges, enums)
  - *Out schemas: output serialisation (orm_mode = True)
  - Sensitive fields (password_hash, raw tokens) are never included in *Out
"""

from datetime import date, datetime
from decimal import Decimal
import re
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, condecimal, EmailStr, Field, validator, root_validator


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

    @validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        """Enforce at least 1 uppercase, 1 lowercase, 1 digit, and 1 special character."""
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit.")
        if not re.search(r"[^A-Za-z0-9]", v):
            raise ValueError("Password must contain at least one special character.")
        return v

    telegram_invite_code: Optional[str] = Field(
        None,
        max_length=32,
        description="One-time invite code that unlocks Telegram notification linking. "
        "Only present when the register page was opened via an invite link.",
    )


class UserOut(UserBase):
    """Serialised user returned by the API — no password hash included."""

    user_id: UUID = Field(..., description="Unique user identifier.")
    kyc_status: str = Field(..., description="KYC verification status: pending | approved | rejected.")
    is_active: bool = Field(..., description="Whether the account is active and can authenticate.")
    telegram_link_code: Optional[str] = Field(
        None,
        description="One-time code to send the bot as '/link <code>' to connect Telegram. "
        "Only set when registration used a valid Telegram invite.",
    )
    telegram_bot_username: Optional[str] = Field(
        None, description="Public @username of the notification bot, if telegram_link_code is set."
    )

    class Config:
        orm_mode = True


class UserLogin(BaseModel):
    """Login credentials."""

    email: EmailStr = Field(..., description="Registered email address.", example="alice@example.com")
    password: str = Field(..., description="Account password.", example="Str0ng!Pass")


# ── Supported currencies and languages ────────────────────────────────────────
SUPPORTED_CURRENCIES = {"USD", "EUR", "GBP", "PLN", "CHF", "JPY", "CAD", "AUD"}
SUPPORTED_LANGUAGES = {"en", "pl", "de", "zh", "es", "pt", "fr", "ja", "it"}


class UserPreferences(BaseModel):
    """User preference values stored as JSON in the preferences column.

    Attributes:
        currency: ISO 4217 currency code for display conversion.
        language: ISO 639-1 language code for UI translations.
        sidebar_collapsed: Whether the sidebar is collapsed by default.
        tutorial_done: Whether the onboarding tutorial has been completed or
            skipped — either way it should not be shown again.
    """
    currency: str = Field("USD", description="Display currency code.")
    language: str = Field("en", description="UI language code.")
    sidebar_collapsed: bool = Field(False, description="Whether sidebar is collapsed.")
    tutorial_done: bool = Field(False, description="Onboarding tutorial completed or skipped.")


class UserPreferencesUpdate(BaseModel):
    """Partial update payload for user preferences. All fields optional.

    Attributes:
        currency: New currency code (must be in SUPPORTED_CURRENCIES).
        language: New language code (must be in SUPPORTED_LANGUAGES).
        sidebar_collapsed: Whether the sidebar is collapsed by default.
        tutorial_done: Mark the onboarding tutorial completed or skipped.
    """
    currency: Optional[str] = Field(None, description="Display currency code.")
    language: Optional[str] = Field(None, description="UI language code.")
    sidebar_collapsed: Optional[bool] = Field(None, description="Whether sidebar is collapsed.")
    tutorial_done: Optional[bool] = Field(None, description="Onboarding tutorial completed or skipped.")


class UserProfileOut(UserBase):
    """Full user profile including preferences, returned by GET /auth/me.

    Attributes:
        user_id: Unique user identifier.
        kyc_status: KYC verification status.
        is_active: Whether the account is active.
        preferences: User preferences (currency, language).
    """
    user_id: UUID = Field(..., description="Unique user identifier.")
    kyc_status: str = Field(..., description="KYC verification status.")
    is_active: bool = Field(..., description="Whether the account is active.")
    preferences: UserPreferences = Field(default_factory=UserPreferences)

    class Config:
        orm_mode = True


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
    preferences: Optional[Dict[str, Any]] = Field(None, description="User preferences (currency, language).")
    account_deactivated: Optional[bool] = Field(None, description="True if account is deactivated.")
    deletion_scheduled_at: Optional[str] = Field(None, description="ISO-8601 timestamp when account will be purged.")


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

    @validator("new_password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        """Enforce at least 1 uppercase, 1 lowercase, 1 digit, and 1 special character."""
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit.")
        if not re.search(r"[^A-Za-z0-9]", v):
            raise ValueError("Password must contain at least one special character.")
        return v


# ── Profile / Account management schemas ────────────────────────────────────

class ProfileUpdateRequest(BaseModel):
    """Payload to update user profile fields (name only)."""

    first_name: Optional[str] = Field(None, max_length=100, description="Updated first name.")
    last_name: Optional[str] = Field(None, max_length=100, description="Updated last name.")


class EmailChangeRequest(BaseModel):
    """Payload to request an email address change."""

    new_email: EmailStr = Field(..., description="New email address to switch to.")
    password: str = Field(..., description="Current password for verification.")


class AccountDeleteRequest(BaseModel):
    """Payload to request account deletion."""

    mode: Literal["permanent", "soft"] = Field(
        ..., description="Deletion mode: 'permanent' (immediate) or 'soft' (30-day grace period)."
    )
    password: str = Field(..., description="Current password for verification.")


class DeactivateRequest(BaseModel):
    """Payload to deactivate an account."""

    password: str = Field(..., description="Current password for verification.")


class TokenActionRequest(BaseModel):
    """Payload for token-based actions (verify email, reactivate, etc.)."""

    token: str = Field(..., description="Raw one-time token received via email link.")


class ResendVerificationRequest(BaseModel):
    """Payload to request a new verification email."""

    email: EmailStr = Field(..., description="Email address to resend verification to.")


class ReactivationRequest(BaseModel):
    """Payload to request an account reactivation email."""

    email: EmailStr = Field(..., description="Email address of the deactivated account.")


# ── User Report schemas ─────────────────────────────────────────────────────

class UserReportCreate(BaseModel):
    """Payload to submit a bug report or improvement suggestion."""

    report_type: Literal["bug", "suggestion", "activation_bug"] = Field(
        ..., description="Report type: bug, suggestion, or activation_bug."
    )
    category: Optional[str] = Field(
        None, max_length=50,
        description="Bug category: UI, Data, Performance, Authentication, Other."
    )
    subject: str = Field(..., min_length=1, max_length=200, description="Report subject line.")
    body: str = Field(..., min_length=1, max_length=5000, description="Detailed description.")
    reporter_email: Optional[EmailStr] = Field(
        None, description="Email for unauthenticated reports (activation bugs only)."
    )
    website: Optional[str] = Field(
        None, max_length=200,
        description="Honeypot field for bot detection — must be left empty by real users.",
    )


class UserReportOut(BaseModel):
    """Serialised user report returned by the API."""

    report_id: UUID
    report_type: str
    category: Optional[str] = None
    subject: str
    body: str
    status: str
    created_at: datetime

    class Config:
        orm_mode = True


class UserReportAdminUpdate(BaseModel):
    """Admin payload to update a report's status and notes."""

    status: Optional[Literal["new", "reviewed", "resolved", "dismissed"]] = None
    admin_notes: Optional[str] = Field(None, max_length=5000)


# ── Admin dashboard schemas ───────────────────────────────────────────────────

class UserAdminOut(BaseModel):
    """Extended user info for admin dashboard.

    Includes fields not exposed in the standard UserOut — security-relevant
    metadata (failed logins, lock status, deactivation timestamp) needed by
    administrators to triage account issues.
    """

    user_id: UUID
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    kyc_status: str
    is_active: bool
    email_verified: bool
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None
    deactivated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class ReportAdminOut(BaseModel):
    """Full report info for admin dashboard.

    Unlike UserReportOut (end-user facing), this schema exposes admin_notes,
    reporter identity, and resolved_at so administrators can manage the
    full lifecycle of user-submitted reports.
    """

    report_id: UUID
    user_id: Optional[UUID] = None
    reporter_email: str
    report_type: str
    category: Optional[str] = None
    subject: str
    body: str
    status: str
    admin_notes: Optional[str] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None

    class Config:
        orm_mode = True


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

    # PostgreSQL INET type returns a non-str object; coerce to plain string.
    @validator("ip_address", pre=True)
    def _coerce_ip(cls, v):
        return str(v) if v is not None else None

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
    cash_balance: float = 0

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
    hard_stop_loss: Optional[Decimal] = Field(None, gt=Decimal("0"), max_digits=18, decimal_places=2, description="Hard stop-loss (DeGiro standing order).", example="140.00")
    soft_stop_loss: Optional[Decimal] = Field(None, gt=Decimal("0"), max_digits=18, decimal_places=2, description="Soft stop-loss — triggers Telegram alert when price reaches this.", example="145.00")
    profit_taking: Optional[Decimal] = Field(None, gt=Decimal("0"), max_digits=18, decimal_places=2, description="Profit-taking target price.", example="200.00")
    deduct_cash: bool = Field(False, description="Deduct cost from portfolio cash balance when adding this position.")


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
    hard_stop_loss: Optional[Decimal] = Field(None, max_digits=18, decimal_places=2)
    soft_stop_loss: Optional[Decimal] = Field(None, max_digits=18, decimal_places=2)
    profit_taking: Optional[Decimal] = Field(None, max_digits=18, decimal_places=2)
    soft_stop_intraday_on: Optional[date] = None
    soft_stop_eod_on: Optional[date] = None
    created_at: datetime

    class Config:
        orm_mode = True


class PositionUpdate(BaseModel):
    """Payload for partial position update — all fields optional."""

    quantity: Optional[Decimal] = Field(None, gt=Decimal("0"), max_digits=18, decimal_places=6)
    purchase_price: Optional[Decimal] = Field(None, gt=Decimal("0"), max_digits=18, decimal_places=2)
    group_tag: Optional[str] = Field(None, max_length=64)
    is_excluded: Optional[bool] = None
    hard_stop_loss: Optional[Decimal] = Field(None, max_digits=18, decimal_places=2)
    soft_stop_loss: Optional[Decimal] = Field(None, max_digits=18, decimal_places=2)
    profit_taking: Optional[Decimal] = Field(None, max_digits=18, decimal_places=2)


class SellRequest(BaseModel):
    """Payload for a partial sell — reduces quantity; deletes if fully sold."""

    quantity: Decimal = Field(..., gt=Decimal("0"), max_digits=18, decimal_places=6, description="Units to sell.")
    credit_cash: bool = Field(True, description="Credit sale proceeds to portfolio cash balance.")
    # Sell price per unit. When provided, overrides the position's purchase price for
    # proceeds calculation. Allows recording actual market price at time of sale.
    sell_price: Optional[Decimal] = Field(None, gt=Decimal("0"), max_digits=18, decimal_places=6, description="Sell price per unit. Defaults to purchase price if omitted.")


class PortfolioTradeOut(BaseModel):
    """Serialised portfolio trade record returned by the API."""

    trade_id: UUID
    portfolio_id: UUID
    trade_type: str
    ticker: str
    quantity: float
    price: float
    # Average cost per unit at sell time; None for BUY trades.
    # realized_pnl = (price - cost_basis) * quantity for SELL trades.
    cost_basis: Optional[float] = None
    total_value: float
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        orm_mode = True


class CashAdjustmentRequest(BaseModel):
    """Payload to manually adjust a portfolio's cash balance."""

    amount: float = Field(..., description="Amount to add (positive) or subtract (negative) from the cash balance.")
    notes: Optional[str] = Field(None, max_length=500, description="Optional note describing the adjustment.")


# ── Market Event schemas ─────────────────────────────────────────────────────

class EventItem(BaseModel):
    """A single financial event (earnings, dividend, split) for a symbol."""

    date: str = Field(..., description="Event date in YYYY-MM-DD format.")
    type: str = Field(..., description="Event type: 'earnings', 'dividend', or 'split'.")
    value: Optional[float] = Field(None, description="Dividend amount, split ratio, or EPS.")
    label: Optional[str] = Field(None, description="Human-readable label, e.g. '$0.24 dividend'.")


class EventsResponse(BaseModel):
    """Response from the market events endpoint."""

    symbol: str
    events: List[EventItem] = Field(default_factory=list)
    target_mean: Optional[float] = Field(None, description="Analyst mean target price.")
    target_high: Optional[float] = Field(None, description="Analyst high target price.")
    target_low: Optional[float] = Field(None, description="Analyst low target price.")


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


class PaginatedNewsResponse(BaseModel):
    """Paginated wrapper for news feed responses.

    Wraps a page of NewsArticleOut objects alongside pagination metadata
    so the frontend can render page controls and display totals.

    Fields:
        articles: The current page of scored news articles.
        total:    Total number of articles matching the query (before pagination).
        limit:    Number of articles requested per page.
        offset:   Number of articles skipped (0-indexed).
    """

    articles: List[NewsArticleOut] = Field(
        default_factory=list,
        description="Current page of news articles.",
    )
    total: int = Field(
        0,
        description="Total number of articles matching the query.",
    )
    limit: int = Field(
        25,
        description="Page size used for this response.",
    )
    offset: int = Field(
        0,
        description="Offset (number of articles skipped).",
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
    """Export format for future LoRA fine-tuning (AppREDACTED 3 migration).

    Each record maps an article input to the original LLM prediction and a
    corrected output derived from actual price movements.
    """

    instruction: str = Field(..., description="System prompt for the model.")
    input_text: str = Field(..., description="Article headline + summary.")
    original_output: Dict[str, Any] = Field(..., description="Original LLM prediction.")
    corrected_output: Dict[str, Any] = Field(..., description="Score derived from actual price data.")
    actual_change_pct: Optional[Decimal] = None
    accuracy_grade: str


# ── Watchlist schemas ────────────────────────────────────────────────────────


class WatchlistCreate(BaseModel):
    """Create a new watchlist."""

    name: str = Field(..., min_length=1, max_length=128, description="Watchlist name.")


class WatchlistUpdate(BaseModel):
    """Rename a watchlist."""

    name: str = Field(..., min_length=1, max_length=128, description="New watchlist name.")


class WatchlistItemOut(BaseModel):
    """Serialised watchlist item."""

    item_id: UUID
    symbol: str
    asset_type: str
    notes: Optional[str] = None
    position_order: int = 0
    price_when_added: Optional[float] = None
    added_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class WatchlistOut(BaseModel):
    """Serialised watchlist (without items)."""

    watchlist_id: UUID
    name: str
    item_count: int = 0
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class WatchlistDetailOut(BaseModel):
    """Serialised watchlist with items."""

    watchlist_id: UUID
    name: str
    items: List[WatchlistItemOut] = Field(default_factory=list)
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class WatchlistItemCreate(BaseModel):
    """Add an item to a watchlist."""

    symbol: str = Field(..., min_length=1, max_length=20, description="Ticker symbol.")
    asset_type: str = Field(
        "stock", max_length=20, description="Asset type: stock, crypto, etf, physical."
    )
    notes: Optional[str] = Field(None, max_length=500, description="Optional note.")
    price_when_added: Optional[float] = Field(
        None, description="Snapshot price at time of adding."
    )


class WatchlistItemUpdate(BaseModel):
    """Update a watchlist item."""

    notes: Optional[str] = Field(None, max_length=500)
    position_order: Optional[int] = Field(None, ge=0)


class WatchlistBuyRequest(BaseModel):
    """Buy an asset from watchlist into a portfolio."""

    portfolio_id: UUID = Field(..., description="Target portfolio ID.")
    purchase_date: Optional[datetime] = Field(None, description="Purchase date.")
    quantity: float = Field(..., gt=0, description="Quantity to buy.")
    purchase_price: float = Field(..., gt=0, description="Purchase price per unit.")
    name: Optional[str] = Field(None, max_length=256, description="Asset display name.")


# ── Portfolio performance schemas ────────────────────────────────────────────

class PerformancePointOut(BaseModel):
    """Single data point in a portfolio performance time series.

    Attributes:
        date:  ISO date string (YYYY-MM-DD).
        value: Total portfolio value on that date.
    """

    date: str = Field(..., description="Date in YYYY-MM-DD format.")
    value: float = Field(..., description="Total portfolio value on this date.")


# ── Trading AI schemas ────────────────────────────────────────────────────


class StrategyCreate(BaseModel):
    """Create a new trading strategy."""

    name: str = Field(..., min_length=1, max_length=128, description="Strategy display name.")
    description: Optional[str] = Field(None, description="User-facing description.")
    strategy_type: Literal["builtin", "learned", "pinescript", "composed", "ml"] = Field(
        ..., description="Strategy type."
    )
    category: Optional[Literal[
        "trend_following", "mean_reversion", "momentum",
        "breakout", "volatility", "ml_based", "hybrid",
    ]] = Field(None, description="Strategy category.")
    timeframe: Optional[Literal[
        "scalping", "day_trading", "swing", "position",
    ]] = Field(None, description="Target timeframe.")
    asset_class: Optional[Literal[
        "stocks", "etfs", "futures", "crypto",
    ]] = Field(None, description="Target asset class.")
    definition_json: Dict = Field(..., description="Full strategy definition (parameters, logic, source).")
    is_public: bool = Field(False, description="Make visible in the marketplace.")


class StrategyOut(BaseModel):
    """Serialised strategy for API responses."""

    strategy_id: UUID
    name: str
    description: Optional[str]
    strategy_type: str
    category: Optional[str]
    timeframe: Optional[str]
    asset_class: Optional[str]
    definition_json: Dict
    is_public: bool
    is_system: bool
    version: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        orm_mode = True


class StrategyUpdate(BaseModel):
    """Partial update payload for a strategy."""

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = None
    definition_json: Optional[Dict] = None
    is_public: Optional[bool] = None
    category: Optional[Literal[
        "trend_following", "mean_reversion", "momentum",
        "breakout", "volatility", "ml_based", "hybrid",
    ]] = None
    timeframe: Optional[Literal[
        "scalping", "day_trading", "swing", "position",
    ]] = None
    asset_class: Optional[Literal[
        "stocks", "etfs", "futures", "crypto",
    ]] = None


class BacktestRequest(BaseModel):
    """Queue a backtest job.

    Accepts either ``strategy_id`` (UUID) or ``strategy_slug`` (string).
    When *strategy_slug* is provided, the route looks up the matching
    system strategy by its ``definition_json.strategy_slug``.
    """

    strategy_id: Optional[UUID] = Field(None, description="Strategy UUID (optional if slug provided).")
    strategy_slug: Optional[str] = Field(None, max_length=50, description="Strategy engine slug (e.g. sma_crossover).")
    symbol: str = Field(..., min_length=1, max_length=20, description="Ticker symbol.")
    interval: str = Field("1d", max_length=10, description="Bar interval (e.g. 1d, 1h).")
    start_date: Optional[str] = Field(None, description="Backtest start date (YYYY-MM-DD or ISO).")
    end_date: Optional[str] = Field(None, description="Backtest end date (YYYY-MM-DD or ISO).")
    parameters_json: Optional[Dict] = Field(None, description="Strategy parameter overrides.")
    params: Optional[Dict] = Field(None, description="Alias for parameters_json (frontend compat).")
    commission_per_trade: Optional[Decimal] = Field(
        None, max_digits=10, decimal_places=4, description="Commission per trade."
    )
    slippage_pct: Optional[Decimal] = Field(
        None, max_digits=6, decimal_places=4, description="Slippage percentage (e.g. 0.0005 = 0.05%)."
    )

    @root_validator
    def _require_id_or_slug(cls, values):
        if not values.get("strategy_id") and not values.get("strategy_slug"):
            raise ValueError("Either strategy_id or strategy_slug is required.")
        return values


class MetricsOut(BaseModel):
    """Performance metrics from a completed backtest."""

    total_return: float = Field(..., description="Total return percentage.")
    annualized_return: float = Field(..., description="CAGR.")
    sharpe_ratio: float = Field(..., description="Sharpe ratio (risk-free = 0).")
    sortino_ratio: float = Field(..., description="Sortino ratio.")
    max_drawdown: float = Field(..., description="Maximum drawdown percentage.")
    max_drawdown_duration: int = Field(..., description="Max drawdown duration in bars.")
    win_rate: float = Field(..., description="Winning trade percentage.")
    profit_factor: float = Field(..., description="Gross profit / gross loss.")
    total_trades: int = Field(..., description="Total number of trades.")
    avg_win: float = Field(..., description="Average winning trade return.")
    avg_loss: float = Field(..., description="Average losing trade return.")
    expectancy: float = Field(..., description="Expected return per trade.")
    calmar_ratio: float = Field(..., description="Annualized return / max drawdown.")


class BacktestResultOut(BaseModel):
    """Serialised backtest result for API responses."""

    result_id: UUID
    strategy_id: Optional[UUID]
    symbol: str
    interval: str
    start_date: datetime
    end_date: datetime
    parameters_json: Optional[Dict]
    results_json: Optional[Dict]
    metrics_json: Optional[Dict]
    benchmark_json: Optional[Dict]
    overfit_warning: bool
    status: str
    error_message: Optional[str]
    created_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        orm_mode = True


class TradingSignalOut(BaseModel):
    """Serialised trading signal for API responses."""

    signal_id: UUID
    strategy_id: UUID
    symbol: str
    signal_type: str
    direction: str
    price: Decimal
    confidence: Optional[Decimal]
    reasoning: Optional[str]
    is_active: bool
    triggered_at: Optional[datetime]
    expires_at: Optional[datetime]
    created_at: Optional[datetime]

    class Config:
        orm_mode = True


# ── Marketplace / Social schemas ────────────────────────────────────────


class RatingCreate(BaseModel):
    """Create or update a strategy rating."""

    stars: int = Field(..., ge=1, le=5, description="Star rating (1-5).")
    review: Optional[str] = Field(None, max_length=2000, description="Optional review text.")


class RatingOut(BaseModel):
    """Serialised strategy rating for API responses."""

    rating_id: UUID
    strategy_id: UUID
    user_id: UUID
    author_name: str = ""
    stars: int
    review: Optional[str]
    created_at: Optional[datetime]

    class Config:
        orm_mode = True


class StrategyStatsOut(BaseModel):
    """Aggregate statistics for a strategy."""

    clone_count: int = 0
    avg_rating: Optional[float] = None
    rating_count: int = 0
    backtest_count: int = 0


class MarketplaceStrategyOut(BaseModel):
    """Strategy listing for the marketplace browse endpoint."""

    strategy_id: UUID
    name: str
    description: Optional[str]
    strategy_type: str
    category: Optional[str]
    timeframe: Optional[str]
    asset_class: Optional[str]
    is_public: bool
    is_system: bool
    version: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    author_name: str = "Anonymous"
    avg_rating: Optional[float] = None
    rating_count: int = 0
    clone_count: int = 0


class BatchBacktestRequest(BaseModel):
    """Queue backtests for multiple symbols."""

    strategy_id: Optional[UUID] = None
    strategy_slug: Optional[str] = None
    symbols: List[str] = Field(..., min_items=1, max_items=20, description="Symbols to backtest.")
    interval: str = "1d"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    parameters: Optional[Dict] = None
    commission: float = Field(1.0, ge=0)
    slippage: float = Field(0.05, ge=0)
    initial_capital: float = Field(10000, gt=0)


# ── Notification schemas ─────────────────────────────────────────────────


class NotificationOut(BaseModel):
    """Serialised in-app notification."""

    notification_id: UUID
    event_type: str
    title: str
    body: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
    is_read: bool
    created_at: datetime

    class Config:
        orm_mode = True


class NotificationMarkRead(BaseModel):
    """Payload to mark one or more notifications as read."""

    notification_ids: List[UUID] = Field(..., min_items=1, description="UUIDs of notifications to mark read.")


class PaginatedNotificationsResponse(BaseModel):
    """Paginated notifications wrapper."""

    notifications: List[NotificationOut] = Field(default_factory=list)
    total: int = 0
    unread_count: int = 0
    limit: int = 25
    offset: int = 0


# ── Webhook schemas ──────────────────────────────────────────────────────


class WebhookCreate(BaseModel):
    """Payload to register a new webhook URL."""

    url: str = Field(..., min_length=10, max_length=2048, description="Webhook endpoint URL (https).")
    events: List[str] = Field(
        default_factory=list,
        description="Event types to subscribe to (e.g. signal_entry, backtest_complete).",
    )


class WebhookOut(BaseModel):
    """Serialised webhook returned by the API."""

    webhook_id: UUID
    url: str
    events: List[str] = Field(default_factory=list)
    is_active: bool
    created_at: datetime

    class Config:
        orm_mode = True


class WebhookUpdate(BaseModel):
    """Partial update payload for a webhook."""

    url: Optional[str] = Field(None, min_length=10, max_length=2048)
    events: Optional[List[str]] = None
    is_active: Optional[bool] = None


# ── Price Alerts ─────────────────────────────────────────────────────


class PriceAlertCreate(BaseModel):
    """Payload to create a new price alert."""

    symbol: str = Field(..., min_length=1, max_length=20, description="Ticker symbol")
    condition: str = Field(..., description="Trigger condition: above, below, or crosses")
    target_price: float = Field(..., gt=0, description="Target price to trigger the alert")
    note: Optional[str] = Field(None, max_length=500, description="Optional user note")

    @validator("condition")
    def validate_condition(cls, v):
        allowed = {"above", "below", "crosses"}
        if v not in allowed:
            raise ValueError(f"condition must be one of {allowed}")
        return v


class PriceAlertOut(BaseModel):
    """Serialised price alert."""

    alert_id: UUID
    symbol: str
    condition: str
    target_price: float
    note: Optional[str] = None
    is_active: bool
    triggered_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        orm_mode = True


class PriceAlertUpdate(BaseModel):
    """Payload to update an existing price alert."""

    target_price: Optional[float] = Field(None, gt=0)
    condition: Optional[str] = None
    note: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None
    triggered_at: Optional[datetime] = None

    @validator("condition")
    def validate_condition(cls, v):
        if v is not None:
            allowed = {"above", "below", "crosses"}
            if v not in allowed:
                raise ValueError(f"condition must be one of {allowed}")
        return v


# ── Market Regime schemas ─────────────────────────────────────────────────

class RegimeRequest(BaseModel):
    """Input for the market regime detection endpoint."""

    symbol: str = Field(..., min_length=1, max_length=10, description="Ticker symbol")
    interval: str = Field("1d", description="Bar interval (1d, 1h, etc.)")
    period_days: int = Field(180, ge=60, le=1825, description="Lookback period in days")


class RegimeResponse(BaseModel):
    """Market regime detection result."""

    symbol: str
    regime: str = Field(..., description="trending_up | trending_down | mean_reverting | high_volatility")
    confidence: float = Field(..., ge=0, le=1)
    volatility_percentile: float
    trend_strength: float


# ── PineScript & Strategy Composition schemas (Phase 4) ─────────────────


class PineScriptValidateRequest(BaseModel):
    """PineScript syntax validation request."""

    source_code: str = Field(
        ..., min_length=10, max_length=50000,
        description="Raw PineScript source code to validate.",
    )


class PineScriptValidateResponse(BaseModel):
    """PineScript syntax validation result."""

    valid: bool = Field(..., description="True if the script is syntactically valid.")
    errors: List[Dict] = Field(default_factory=list, description="Syntax error details.")


class PineScriptTranspileRequest(BaseModel):
    """PineScript transpilation request — creates a strategy from PineScript code."""

    source_code: str = Field(
        ..., min_length=10, max_length=50000,
        description="Raw PineScript source code.",
    )
    name: str = Field(..., min_length=1, max_length=128, description="Strategy display name.")
    description: Optional[str] = Field(None, description="Strategy description.")
    use_llm_fallback: bool = Field(
        False, description="Use Ollama LLM translation if deterministic parse fails.",
    )


class PineScriptTranspileResponse(BaseModel):
    """Transpilation result with compiled IR and strategy metadata."""

    success: bool = Field(..., description="True if transpilation succeeded.")
    strategy_id: Optional[UUID] = Field(None, description="Created strategy UUID.")
    transpile_method: Optional[str] = Field(None, description="'lark' or 'llm'.")
    definition_json: Optional[Dict] = Field(None, description="Full compiled definition.")
    errors: List[str] = Field(default_factory=list, description="Error messages.")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal warnings.")


class StrategyVersionOut(BaseModel):
    """A single version in the strategy version history."""

    version_id: UUID
    strategy_id: UUID
    version_number: int
    definition_json: Dict
    created_at: Optional[datetime]

    class Config:
        orm_mode = True


class CompositionRequest(BaseModel):
    """Create a composed strategy from indicator nodes and expressions."""

    name: str = Field(..., min_length=1, max_length=128, description="Strategy display name.")
    description: Optional[str] = Field(None, description="Strategy description.")
    composition_json: Dict = Field(
        ..., description="Composition definition: indicators, entry_expr, exit_expr, stop_loss, params, param_schema.",
    )


# ─── Paper Trading ──────────────────────────────────────────────────────────


class PaperTradeCreate(BaseModel):
    """Start a new paper trade."""
    strategy_id: Optional[UUID] = Field(None, description="Strategy UUID.")
    strategy_slug: Optional[str] = Field(None, max_length=50, description="Strategy engine slug.")
    symbol: str = Field(..., min_length=1, max_length=20, description="Ticker symbol.")
    initial_capital: Decimal = Field(default=Decimal("10000.00"), max_digits=18, decimal_places=2, description="Starting virtual balance.")
    parameters: Optional[Dict] = Field(None, description="Strategy parameter overrides.")


class PaperTradeUpdate(BaseModel):
    """Fields allowed for paper trade edits (capital and strategy parameters)."""
    initial_capital: Optional[Decimal] = Field(None, gt=0, le=1000000, description="New initial capital (resets current_equity when changed).")
    parameters: Optional[Dict[str, Any]] = None


class PaperTradeOut(BaseModel):
    """Serialised paper trade."""
    paper_trade_id: UUID
    user_id: UUID
    strategy_id: Optional[UUID] = None
    strategy_name: Optional[str] = None
    strategy_slug: Optional[str] = None
    symbol: str
    initial_capital: Decimal
    current_equity: Decimal
    status: str
    parameters_json: Optional[Dict[str, Any]] = None
    created_at: datetime
    stopped_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class PaperTradePositionOut(BaseModel):
    """Serialised paper trade position."""
    position_id: UUID
    paper_trade_id: UUID
    side: str
    entry_price: Decimal
    entry_date: datetime
    exit_price: Optional[Decimal] = None
    exit_date: Optional[datetime] = None
    quantity: Decimal
    pnl: Optional[Decimal] = None
    status: str

    class Config:
        orm_mode = True


class PaperTradeEquitySnapshotOut(BaseModel):
    """Serialised equity snapshot."""
    snapshot_id: UUID
    paper_trade_id: UUID
    equity: Decimal
    timestamp: datetime

    class Config:
        orm_mode = True


# ── Portfolio scoring schemas ────────────────────────────────────────────


class PortfolioItem(BaseModel):
    """Single portfolio position passed to the extended portfolio score endpoint.

    Attributes:
        ticker:         Ticker symbol.
        quantity:       Number of units held.
        purchase_price: Cost basis (break-even price) per unit.
        stop_loss:      Optional stop-loss price for status evaluation.
        profit_taking:  Optional profit-taking target price.
    """

    ticker: str
    quantity: float
    purchase_price: float
    hard_stop_loss: Optional[float] = None
    profit_taking: Optional[float] = None


class PortfolioScoreRequest(BaseModel):
    """Request to score a set of positions.

    The caller supplies up to 30 ticker symbols and receives per-position
    analysis (trend, RSI, volatility, signal) plus an overall portfolio score.
    Optionally supply ``positions`` for extended P&L and stop-loss evaluation.
    """

    symbols: List[str] = Field(
        ...,
        min_items=1,
        max_items=30,
        description="Ticker symbols to analyze (max 30).",
    )
    positions: Optional[List[PortfolioItem]] = Field(
        None,
        description="Optional position details for extended P&L scoring.",
    )


class PositionScore(BaseModel):
    """Analysis result for a single position.

    Combines technical indicators (trend, RSI, volatility) with the best
    signal from the top three built-in strategies to produce a composite
    1-100 score and a human-readable suggestion.
    """

    symbol: str = Field(..., description="Ticker symbol.")
    current_price: float = Field(..., description="Latest closing price.")
    trend: str = Field(
        ..., description='Trend classification: "bullish", "bearish", or "neutral".'
    )
    rsi: float = Field(..., description="Latest 14-period RSI value (0-100).")
    volatility: float = Field(
        ..., description="ATR(14) expressed as a percentage of the current price."
    )
    signal: str = Field(
        ..., description='Best strategy signal: "BUY", "SELL", or "HOLD".'
    )
    signal_strategy: str = Field(
        ..., description="Slug of the strategy that generated the signal."
    )
    suggestion: str = Field(
        ..., description="Human-readable actionable suggestion."
    )
    score: int = Field(..., ge=0, le=100, description="Composite score 1-100.")
    # Extended fields — populated when position detail is provided
    cost_basis: Optional[float] = Field(None, description="Total cost basis (purchase_price × quantity).")
    unrealized_pnl: Optional[float] = Field(None, description="Unrealised profit/loss in dollars.")
    unrealized_pnl_pct: Optional[float] = Field(None, description="Unrealised profit/loss as a percentage.")
    stop_loss_recommendation: Optional[str] = Field(None, description="Stop-loss status: OK, WARNING, TRIGGERED, or note.")


class PortfolioScoreResponse(BaseModel):
    """Aggregated portfolio scoring response.

    Contains per-position analysis and an overall portfolio-level score
    derived from the average of individual position scores.
    """

    positions: List[PositionScore] = Field(
        default_factory=list, description="Per-symbol analysis results."
    )
    overall_score: int = Field(
        ..., ge=0, le=100, description="Average score across all positions."
    )
    top_suggestion: str = Field(
        ..., description="Most important recommendation (from the lowest-scored position)."
    )


# ── Market fundamentals schema ─────────────────────────────────────────────


class FundamentalsResponse(BaseModel):
    """Fundamental data for a single security.

    Aggregates company info, valuation multiples, financial health metrics,
    dividend data, analyst targets, earnings, and trading statistics sourced
    from the yfinance ``Ticker.info`` dict.  All numeric fields are Optional
    because coverage varies by security type and exchange.
    """

    # Company info
    symbol: str
    name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None
    country: Optional[str] = None
    employees: Optional[int] = None
    exchange: Optional[str] = None
    currency: Optional[str] = None

    # Current price (for analyst target range visualisation)
    current_price: Optional[float] = None

    # Valuation
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    peg_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    ps_ratio: Optional[float] = None
    ev_to_ebitda: Optional[float] = None

    # Financial health
    revenue: Optional[float] = None
    net_income: Optional[float] = None
    profit_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    free_cash_flow: Optional[float] = None

    # Dividends
    dividend_yield: Optional[float] = None
    dividend_rate: Optional[float] = None
    payout_ratio: Optional[float] = None
    ex_dividend_date: Optional[str] = None

    # Analyst targets
    target_low: Optional[float] = None
    target_mean: Optional[float] = None
    target_high: Optional[float] = None
    target_median: Optional[float] = None
    recommendation: Optional[str] = None
    num_analysts: Optional[int] = None

    # Earnings
    eps_trailing: Optional[float] = None
    eps_forward: Optional[float] = None
    earnings_date: Optional[str] = None

    # Trading info
    beta: Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None
    fifty_day_avg: Optional[float] = None
    two_hundred_day_avg: Optional[float] = None
    avg_volume: Optional[float] = None
    shares_outstanding: Optional[float] = None
    float_shares: Optional[float] = None
    short_ratio: Optional[float] = None
    short_pct: Optional[float] = None


# ── Exit Analysis schemas ────────────────────────────────────────────────────

class ExitAnalysisRequest(BaseModel):
    """Request for exit point analysis on a single symbol."""

    symbol: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Ticker symbol to analyse (e.g. 'AAPL').",
        example="AAPL",
    )
    period_days: int = Field(
        365,
        ge=30,
        le=730,
        description="Historical data window in calendar days (30–730).",
        example=365,
    )


class ExitLevel(BaseModel):
    """Single price level with type and rationale."""

    level_type: str = Field(
        ...,
        description='Category: "stop_loss", "take_profit", "support", "resistance", or "fibonacci".',
        example="stop_loss",
    )
    price: float = Field(..., description="Price value of this level.", example=168.50)
    label: str = Field(
        ...,
        description='Human-readable label, e.g. "ATR Stop (-2x ATR)".',
        example="ATR Stop (-2x ATR)",
    )
    rationale: str = Field(
        ...,
        description="Short explanation of why this level matters.",
        example="2x ATR below current price — standard volatility-based stop.",
    )


class ExitAnalysisResponse(BaseModel):
    """Comprehensive exit analysis for a symbol."""

    symbol: str = Field(..., description="Ticker symbol.", example="AAPL")
    current_price: float = Field(..., description="Most recent close price.", example=175.50)
    levels: List[ExitLevel] = Field(default_factory=list, description="All computed exit levels.")
    atr_value: float = Field(..., description="Current ATR(14) value.", example=3.42)
    atr_pct: float = Field(..., description="ATR as a percentage of the current price.", example=1.95)
    trend: str = Field(
        ...,
        description='Market trend: "bullish", "bearish", or "neutral".',
        example="bullish",
    )
    rsi: float = Field(..., description="Current RSI(14) reading (0–100).", example=58.2)
    support_zone: Optional[float] = Field(
        None,
        description="Highest support level below the current price.",
        example=168.00,
    )
    resistance_zone: Optional[float] = Field(
        None,
        description="Lowest resistance level above the current price.",
        example=182.00,
    )


# ── Sector & Screener ────────────────────────────────────────────────────

class SectorItem(BaseModel):
    """Single sector ETF performance snapshot.

    Attributes:
        symbol:     ETF ticker symbol (e.g. "XLK").
        name:       Human-readable sector name (e.g. "Technology").
        price:      Current ETF price.
        change_pct: Daily price change as a percentage.
        ytd_pct:    Year-to-date performance percentage.
        month_pct:  One-month performance percentage.
    """
    symbol: str
    name: str
    price: float
    change_pct: float
    ytd_pct: Optional[float] = None
    month_pct: Optional[float] = None


class SectorResponse(BaseModel):
    """Sector performance overview — list of sector ETF snapshots."""
    sectors: List[SectorItem] = Field(default_factory=list)


class ScreenerItem(BaseModel):
    """Single stock in screener results.

    Attributes:
        symbol:     Ticker symbol (e.g. "NVDA").
        name:       Company display name.
        price:      Current price.
        change:     Absolute daily price change.
        change_pct: Daily change as a percentage.
        volume:     Trading volume.
        market_cap: Market capitalisation (may be None for some tickers).
        sector:     GICS sector name (may be None).
    """
    symbol: str
    name: str
    price: float
    change: float
    change_pct: float
    volume: int
    market_cap: Optional[float] = None
    sector: Optional[str] = None
    sma50: Optional[float] = Field(None, description="50-day simple moving average.")


class ScreenerResponse(BaseModel):
    """Stock screener results with filter metadata."""
    results: List[ScreenerItem] = Field(default_factory=list)
    total_matched: int = 0
    filters_applied: Dict[str, Any] = Field(default_factory=dict)


# ── Volume Flow Scanner ───────────────────────────────────────────────────────

class ScanRunRequest(BaseModel):
    """Request to start a Volume Flow Scan.

    Attributes:
        portfolio_value_usd: Portfolio size in USD used for Phase 5 position sizing.
        mode:                Scan mode: "auto" (default), "live", or "prev-day".
    """

    portfolio_value_usd: float = 10000.0
    mode: Optional[str] = "auto"  # auto | live | prev-day

    @validator("portfolio_value_usd")
    def must_be_positive(cls, v: float) -> float:
        """Reject non-positive portfolio values."""
        if v <= 0:
            raise ValueError("portfolio_value_usd must be positive")
        return v

    @validator("mode")
    def must_be_valid_mode(cls, v: Optional[str]) -> Optional[str]:
        """Allow only known mode values."""
        allowed = {"auto", "live", "prev-day"}
        if v not in allowed:
            raise ValueError(f"mode must be one of: {', '.join(sorted(allowed))}")
        return v


class ScanResultOut(BaseModel):
    """Serialized scan result returned by the API.

    Attributes:
        result_id:       UUID of the scan result.
        status:          Current state: pending/running/complete/error.
        phase_reached:   Last phase completed (1-3).
        parameters_json: Input parameters used for this scan.
        results_json:    Full scan output (active sectors, industries, candidates).
        error_message:   Error detail if status=error.
        started_at:      When the worker picked up the job.
        completed_at:    When the worker finished.
        created_at:      When the job was created.
    """

    result_id:       UUID
    status:          str
    phase_reached:   Optional[int]
    parameters_json: Optional[dict]
    results_json:    Optional[dict]
    error_message:   Optional[str]
    started_at:      Optional[datetime]
    completed_at:    Optional[datetime]
    created_at:      datetime
    mode:            str = "auto"

    class Config:
        orm_mode = True


# ── Portfolio Rules ──────────────────────────────────────────────────────────


class RuleAlertResponse(BaseModel):
    """RuleAlert response schema — serialised portfolio rule alert.

    Attributes:
        id:              Auto-incremented alert primary key.
        user_id:         Owner's UUID.
        position_id:     Associated portfolio position (null for portfolio-level alerts).
        portfolio_id:    Associated portfolio (null for position-level alerts).
        rule_type:       Engine rule that produced this alert (e.g. 'house_money').
        severity:        Alert severity: info | warning | critical.
        title:           Short human-readable alert title.
        body:            Longer explanatory message.
        triggered_value: The numeric value that triggered the rule (e.g. ratio, price).
        state:           Alert lifecycle state: active | snoozed | actioned | expired.
        snoozed_until:   UTC timestamp until which the alert is silenced.
        expires_at:      UTC timestamp after which the alert is auto-expired.
        created_at:      UTC timestamp when the alert was created.
    """

    id: int
    user_id: UUID
    position_id: Optional[int]
    portfolio_id: Optional[int]
    rule_type: str
    severity: str  # info | warning | critical
    title: Optional[str]
    body: Optional[str]
    triggered_value: Optional[Decimal]
    state: str  # active | snoozed | actioned | expired
    snoozed_until: Optional[datetime]
    expires_at: Optional[datetime]
    created_at: datetime

    class Config:
        orm_mode = True


class RuleAlertPatch(BaseModel):
    """Patch request for snoozing or actioning a portfolio rule alert.

    Attributes:
        state:         New lifecycle state: snoozed | actioned | expired.
        snoozed_until: Required when state='snoozed'; UTC timestamp to snooze until.
    """

    state: Optional[str] = None  # snoozed | actioned | expired
    snoozed_until: Optional[datetime] = None

    @validator("state")
    def valid_state(cls, v: Optional[str]) -> Optional[str]:
        """Reject state values outside the allowed set."""
        allowed = {"snoozed", "actioned", "expired"}
        if v is not None and v not in allowed:
            raise ValueError(f"state must be one of {allowed}")
        return v


class PortfolioRulesRunRequest(BaseModel):
    """Request to trigger the rules engine job.

    Attributes:
        schedule: Execution context hint: on_demand | market_hours | end_of_day.
                  Defaults to 'on_demand' for manual API invocations.
    """

    schedule: Optional[str] = "on_demand"  # on_demand | market_hours | end_of_day

    @validator("schedule")
    def valid_schedule(cls, v: Optional[str]) -> Optional[str]:
        """Reject schedule values outside the allowed set."""
        allowed = {"on_demand", "market_hours", "end_of_day"}
        if v is not None and v not in allowed:
            raise ValueError(f"schedule must be one of {allowed}")
        return v


class PortfolioRulesRunResponse(BaseModel):
    """Response returned after queuing a portfolio rules engine run.

    Attributes:
        job_id: arq job identifier that can be polled for completion.
        status: Immediate disposition: queued | already_running.
    """

    job_id: str
    status: str  # queued | already_running


class PortfolioRulesConfig(BaseModel):
    """Rule thresholds and flags stored in users.preferences_json.portfolio_rules.

    All numeric thresholds have project-standard defaults; users may override
    via the preferences API.  The ``enabled_rules`` list controls which rules
    the engine evaluates on each run.

    Attributes:
        house_money_multiple:        Multiple of cost-basis at which position is
                                     fully funded by gains (fire critical alert).
        house_money_warn_at:         Warn multiple (appREDACTEDing house-money status).
        house_money_info_at:         Info multiple (early-stage house-money signal).
        stop_proximity_pct:          Fraction of current price within which a stop
                                     triggers a warning (e.g. 0.07 = 7%).
        semi_cap:                    Maximum single-position weight before a
                                     concentration warning fires.
        bucket_1_target:             Target weight for the first allocation bucket.
        bucket_2_target:             Target weight for the second allocation bucket.
        bucket_3_target:             Target weight for the third allocation bucket.
        time_stop_warn_sessions:     Trading sessions without progress before a
                                     time-stop warning.
        time_stop_critical_sessions: Sessions before a critical time-stop alert.
        analyst_flag_pct:            Analyst consensus threshold below which a
                                     bearish flag is raised (fraction, e.g. 0.50).
        de_ratio_warn:               Debt/equity ratio that triggers a warning.
        de_ratio_critical:           Debt/equity ratio that triggers a critical alert.
        margin_compression_warn_pct: Operating-margin contraction % that fires a warn.
        enabled_rules:               List of rule slugs the engine will evaluate.
        run_schedule:                Default schedule for automated runs.
    """

    house_money_multiple: float = 2.0
    house_money_warn_at: float = 1.75
    house_money_info_at: float = 1.50
    stop_proximity_pct: float = 0.07
    semi_cap: float = 0.35
    bucket_1_target: float = 0.35
    bucket_2_target: float = 0.35
    bucket_3_target: float = 0.30
    time_stop_warn_sessions: int = 10
    time_stop_critical_sessions: int = 21
    analyst_flag_pct: float = 0.50
    de_ratio_warn: float = 200.0
    de_ratio_critical: float = 500.0
    margin_compression_warn_pct: float = 30.0
    enabled_rules: List[str] = [
        "house_money", "stop_proximity", "semi_cap",
        "bucket", "time_stop", "analyst_consensus",
        "fundamentals", "pre_earnings",
    ]
    run_schedule: str = "on_demand"
