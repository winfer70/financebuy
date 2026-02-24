from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.sql import func
import uuid

from .db import Base


class User(Base):
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
    __tablename__ = "accounts"

    account_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    account_type = Column(String(50), nullable=False)
    account_number = Column(String(50), unique=True, nullable=False)
    balance = Column(Numeric(18, 2), server_default="0.00")
    currency = Column(String(3), server_default="USD")
    status = Column(String(20), server_default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.account_id"),
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
    __tablename__ = "holdings"

    holding_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.account_id"),
        nullable=False,
    )
    security_id = Column(
        UUID(as_uuid=True),
        ForeignKey("securities.security_id"),
        nullable=False,
    )
    quantity = Column(Numeric(18, 6), nullable=False)
    average_cost = Column(Numeric(18, 2))
    current_price = Column(Numeric(18, 2))
    last_updated = Column(DateTime(timezone=True), server_default=func.now())


class Order(Base):
    __tablename__ = "orders"

    order_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.account_id"),
        nullable=False,
    )
    security_id = Column(
        UUID(as_uuid=True),
        ForeignKey("securities.security_id"),
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


class AuditLog(Base):
    __tablename__ = "audit_log"

    log_id = Column(
        Numeric(asdecimal=False), primary_key=True, autoincrement=True
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id"),
    )
    action = Column(String(100), nullable=False)
    table_name = Column(String(100))
    record_id = Column(UUID(as_uuid=True))
    old_values = Column(JSONB)
    new_values = Column(JSONB)
    ip_address = Column(INET)
    user_agent = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
