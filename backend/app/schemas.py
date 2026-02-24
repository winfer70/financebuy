from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserOut(UserBase):
    user_id: UUID
    kyc_status: str
    is_active: bool

    class Config:
        orm_mode = True


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class AccountCreate(BaseModel):
    account_type: str
    currency: Optional[str] = "USD"


class AccountOut(BaseModel):
    account_id: UUID
    account_type: str
    account_number: str
    balance: Decimal = Field(max_digits=18, decimal_places=2)
    currency: str
    status: str

    class Config:
        orm_mode = True


class TransactionCreate(BaseModel):
    account_id: UUID
    transaction_type: str
    amount: Decimal = Field(max_digits=18, decimal_places=2)
    currency: Optional[str] = "USD"
    description: Optional[str] = None
    reference_number: Optional[str] = None



class TransactionOut(TransactionCreate):
    transaction_id: UUID
    status: str
    created_at: Optional[str]

    class Config:
        orm_mode = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: Optional[UUID] = None
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class HoldingPositionOut(BaseModel):
    account_id: UUID
    security_id: UUID
    symbol: str
    name: str
    quantity: Decimal = Field(max_digits=18, decimal_places=6)
    average_cost: Optional[Decimal] = None
    current_price: Optional[Decimal] = None
    market_value: Decimal = Field(max_digits=18, decimal_places=2)
    currency: str


class AccountPortfolioSummary(BaseModel):
    account_id: UUID
    account_type: str
    currency: str
    cash_balance: Decimal = Field(max_digits=18, decimal_places=2)
    positions_value: Decimal = Field(max_digits=18, decimal_places=2)
    total_value: Decimal = Field(max_digits=18, decimal_places=2)


class PortfolioSummary(BaseModel):
    accounts: list[AccountPortfolioSummary]
    total_portfolio_value: Decimal = Field(max_digits=18, decimal_places=2)
    # For now we assume a single primary currency; mixed-currency
    # portfolios can be represented by per-account currencies above.
    currency: str = "USD"


class OrderCreate(BaseModel):
    account_id: UUID
    security_id: UUID
    order_type: str  # "market" or "limit"
    side: str  # "buy" or "sell"
    quantity: Decimal = Field(max_digits=18, decimal_places=6)
    # For now, callers must provide the execution price even for
    # "market" orders until a real pricing feed is integrated.
    price: Decimal = Field(max_digits=18, decimal_places=2)


class OrderOut(BaseModel):
    order_id: UUID
    account_id: UUID
    security_id: UUID
    order_type: str
    side: str
    quantity: Decimal = Field(max_digits=18, decimal_places=6)
    price: Decimal = Field(max_digits=18, decimal_places=2)
    status: str
    filled_quantity: Decimal = Field(max_digits=18, decimal_places=6)
    filled_price: Decimal | None = Field(default=None, max_digits=18, decimal_places=2)
    symbol: str | None = None
    placed_at: Optional[str] = None

    class Config:
        orm_mode = True


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class AuditLogOut(BaseModel):
    log_id: int
    user_id: Optional[UUID]
    action: str
    table_name: Optional[str]
    record_id: Optional[UUID]
    old_values: Optional[Dict[str, Any]]
    new_values: Optional[Dict[str, Any]]
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime

    class Config:
        orm_mode = True
