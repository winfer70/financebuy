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
from typing import Any, Dict, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


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
