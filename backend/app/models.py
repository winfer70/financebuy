"""
models.py — SQLAlchemy ORM models for TickerTap.

Defines all database tables: users, accounts, transactions, securities,
holdings, orders, password_reset_tokens, and audit_log.

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
    Numeric,
    String,
    Text,
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
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


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
