"""initial

Revision ID: 0001_initial
Revises: 
Create Date: 2026-01-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')

    op.create_table(
        "users",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(100)),
        sa.Column("last_name", sa.String(100)),
        sa.Column("phone", sa.String(20)),
        sa.Column("kyc_status", sa.String(20), server_default='pending'),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text('true')),
    )
    op.create_index("idx_users_email", "users", ["email"])

    op.create_table(
        "accounts",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id")),
        sa.Column("account_type", sa.String(50), nullable=False),
        sa.Column("account_number", sa.String(50), nullable=False, unique=True),
        sa.Column("balance", sa.Numeric(18,2), server_default="0.00"),
        sa.Column("currency", sa.String(3), server_default="'USD'"),
        sa.Column("status", sa.String(20), server_default="'active'"),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index("idx_accounts_user_id", "accounts", ["user_id"])

    op.create_table(
        "transactions",
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.account_id")),
        sa.Column("transaction_type", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(18,2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="'USD'"),
        sa.Column("status", sa.String(20), server_default="'pending'"),
        sa.Column("description", sa.Text()),
        sa.Column("reference_number", sa.String(100), unique=True),
        sa.Column("executed_at", sa.TIMESTAMP()),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index("idx_transactions_account_id", "transactions", ["account_id"])
    op.create_index("idx_transactions_created_at", "transactions", ["created_at"])

    op.create_table(
        "securities",
        sa.Column("security_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column("symbol", sa.String(10), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("security_type", sa.String(50), nullable=False),
        sa.Column("exchange", sa.String(50)),
        sa.Column("currency", sa.String(3), server_default="'USD'"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text('true')),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    op.create_table(
        "holdings",
        sa.Column("holding_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.account_id")),
        sa.Column("security_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("securities.security_id")),
        sa.Column("quantity", sa.Numeric(18,6), nullable=False),
        sa.Column("average_cost", sa.Numeric(18,2)),
        sa.Column("current_price", sa.Numeric(18,2)),
        sa.Column("last_updated", sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index("idx_holdings_account_id", "holdings", ["account_id"])
    op.create_unique_constraint("uq_holdings_account_security", "holdings", ["account_id", "security_id"])

    op.create_table(
        "orders",
        sa.Column("order_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.account_id")),
        sa.Column("security_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("securities.security_id")),
        sa.Column("order_type", sa.String(20), nullable=False),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("quantity", sa.Numeric(18,6), nullable=False),
        sa.Column("price", sa.Numeric(18,2)),
        sa.Column("status", sa.String(20), server_default="'pending'"),
        sa.Column("filled_quantity", sa.Numeric(18,6), server_default="0"),
        sa.Column("filled_price", sa.Numeric(18,2)),
        sa.Column("placed_at", sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column("executed_at", sa.TIMESTAMP()),
        sa.Column("cancelled_at", sa.TIMESTAMP()),
    )
    op.create_index("idx_orders_account_id", "orders", ["account_id"])
    op.create_index("idx_orders_status", "orders", ["status"])

    op.create_table(
        "audit_log",
        sa.Column("log_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id")),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("table_name", sa.String(100)),
        sa.Column("record_id", postgresql.UUID(as_uuid=True)),
        sa.Column("old_values", postgresql.JSONB),
        sa.Column("new_values", postgresql.JSONB),
        sa.Column("ip_address", postgresql.INET),
        sa.Column("user_agent", sa.Text()),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index("idx_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("idx_audit_log_created_at", "audit_log", ["created_at"])

def downgrade():
    op.drop_index("idx_audit_log_created_at", table_name="audit_log")
    op.drop_index("idx_audit_log_user_id", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("idx_orders_status", table_name="orders")
    op.drop_index("idx_orders_account_id", table_name="orders")
    op.drop_table("orders")

    op.drop_constraint("uq_holdings_account_security", "holdings", type_="unique")
    op.drop_index("idx_holdings_account_id", table_name="holdings")
    op.drop_table("holdings")

    op.drop_table("securities")

    op.drop_index("idx_transactions_created_at", table_name="transactions")
    op.drop_index("idx_transactions_account_id", table_name="transactions")
    op.drop_table("transactions")

    op.drop_index("idx_accounts_user_id", table_name="accounts")
    op.drop_table("accounts")

    op.drop_index("idx_users_email", table_name="users")
    op.drop_table("users")
