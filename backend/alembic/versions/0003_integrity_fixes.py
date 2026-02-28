"""integrity fixes

Fix malformed server_defaults (nested quotes), add CASCADE deletes,
CHECK constraints, NOT NULL constraints, and composite indexes.

Revision ID: 0003_integrity_fixes
Revises: 0002_password_reset_tokens
Create Date: 2026-02-28 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_integrity_fixes"
down_revision = "0002_password_reset_tokens"
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------------------------------------------ #
    # accounts                                                             #
    # ------------------------------------------------------------------ #
    # Fix malformed server_default values — previously stored as "'USD'"
    # and "'active'" (with embedded single quotes), causing literal strings
    # like 'USD' (with quotes) to appear in the DB.
    op.alter_column(
        "accounts",
        "currency",
        existing_type=sa.String(3),
        server_default="USD",
    )
    op.alter_column(
        "accounts",
        "status",
        existing_type=sa.String(20),
        server_default="active",
    )

    # Enforce user_id NOT NULL (accounts must always belong to a user)
    op.alter_column(
        "accounts",
        "user_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
    )

    # Cascade deletes: removing a user removes their accounts
    op.drop_constraint("accounts_user_id_fkey", "accounts", type_="foreignkey")
    op.create_foreign_key(
        "fk_accounts_user_id",
        "accounts",
        "users",
        ["user_id"],
        ["user_id"],
        ondelete="CASCADE",
    )

    # Balance must never be negative
    op.create_check_constraint("ck_accounts_balance_non_negative", "accounts", "balance >= 0")

    # ------------------------------------------------------------------ #
    # transactions                                                         #
    # ------------------------------------------------------------------ #
    # Fix malformed server_default
    op.alter_column(
        "transactions",
        "currency",
        existing_type=sa.String(3),
        server_default="USD",
    )
    op.alter_column(
        "transactions",
        "status",
        existing_type=sa.String(20),
        server_default="pending",
    )

    # Transactions must have a positive amount
    op.create_check_constraint("ck_transactions_amount_positive", "transactions", "amount > 0")

    # Cascade deletes: removing an account removes its transactions
    op.drop_constraint("transactions_account_id_fkey", "transactions", type_="foreignkey")
    op.create_foreign_key(
        "fk_transactions_account_id",
        "transactions",
        "accounts",
        ["account_id"],
        ["account_id"],
        ondelete="CASCADE",
    )

    # Composite index for the most common query pattern: fetch all
    # transactions for an account ordered by date
    op.create_index(
        "idx_transactions_account_created",
        "transactions",
        ["account_id", "created_at"],
    )

    # ------------------------------------------------------------------ #
    # securities                                                           #
    # ------------------------------------------------------------------ #
    # Fix malformed server_default
    op.alter_column(
        "securities",
        "currency",
        existing_type=sa.String(3),
        server_default="USD",
    )

    # ------------------------------------------------------------------ #
    # holdings                                                             #
    # ------------------------------------------------------------------ #
    # Holdings quantity must be positive
    op.create_check_constraint("ck_holdings_quantity_positive", "holdings", "quantity > 0")

    # Cascade from account; restrict from security (prevent orphaned holds)
    op.drop_constraint("holdings_account_id_fkey", "holdings", type_="foreignkey")
    op.create_foreign_key(
        "fk_holdings_account_id",
        "holdings",
        "accounts",
        ["account_id"],
        ["account_id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("holdings_security_id_fkey", "holdings", type_="foreignkey")
    op.create_foreign_key(
        "fk_holdings_security_id",
        "holdings",
        "securities",
        ["security_id"],
        ["security_id"],
        ondelete="RESTRICT",
    )

    # ------------------------------------------------------------------ #
    # orders                                                               #
    # ------------------------------------------------------------------ #
    # Fix malformed server_default
    op.alter_column(
        "orders",
        "status",
        existing_type=sa.String(20),
        server_default="pending",
    )

    # Orders quantity must be positive
    op.create_check_constraint("ck_orders_quantity_positive", "orders", "quantity > 0")

    # Cascade from account; restrict from security
    op.drop_constraint("orders_account_id_fkey", "orders", type_="foreignkey")
    op.create_foreign_key(
        "fk_orders_account_id",
        "orders",
        "accounts",
        ["account_id"],
        ["account_id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("orders_security_id_fkey", "orders", type_="foreignkey")
    op.create_foreign_key(
        "fk_orders_security_id",
        "orders",
        "securities",
        ["security_id"],
        ["security_id"],
        ondelete="RESTRICT",
    )

    # Composite index: fetch open orders for an account efficiently
    op.create_index(
        "idx_orders_account_status",
        "orders",
        ["account_id", "status"],
    )

    # ------------------------------------------------------------------ #
    # audit_log                                                            #
    # ------------------------------------------------------------------ #
    # Preserve audit trail when a user is deleted (SET NULL instead of
    # cascade, so we keep the log row but lose the user reference)
    op.drop_constraint("audit_log_user_id_fkey", "audit_log", type_="foreignkey")
    op.create_foreign_key(
        "fk_audit_log_user_id",
        "audit_log",
        "users",
        ["user_id"],
        ["user_id"],
        ondelete="SET NULL",
    )


def downgrade():
    # ------------------------------------------------------------------ #
    # audit_log                                                            #
    # ------------------------------------------------------------------ #
    op.drop_constraint("fk_audit_log_user_id", "audit_log", type_="foreignkey")
    op.create_foreign_key(
        "audit_log_user_id_fkey", "audit_log", "users", ["user_id"], ["user_id"]
    )

    # ------------------------------------------------------------------ #
    # orders                                                               #
    # ------------------------------------------------------------------ #
    op.drop_index("idx_orders_account_status", table_name="orders")
    op.drop_constraint("fk_orders_security_id", "orders", type_="foreignkey")
    op.create_foreign_key(
        "orders_security_id_fkey", "orders", "securities", ["security_id"], ["security_id"]
    )
    op.drop_constraint("fk_orders_account_id", "orders", type_="foreignkey")
    op.create_foreign_key(
        "orders_account_id_fkey", "orders", "accounts", ["account_id"], ["account_id"]
    )
    op.drop_constraint("ck_orders_quantity_positive", "orders", type_="check")
    op.alter_column("orders", "status", server_default="'pending'")

    # ------------------------------------------------------------------ #
    # holdings                                                             #
    # ------------------------------------------------------------------ #
    op.drop_constraint("fk_holdings_security_id", "holdings", type_="foreignkey")
    op.create_foreign_key(
        "holdings_security_id_fkey", "holdings", "securities", ["security_id"], ["security_id"]
    )
    op.drop_constraint("fk_holdings_account_id", "holdings", type_="foreignkey")
    op.create_foreign_key(
        "holdings_account_id_fkey", "holdings", "accounts", ["account_id"], ["account_id"]
    )
    op.drop_constraint("ck_holdings_quantity_positive", "holdings", type_="check")

    # ------------------------------------------------------------------ #
    # securities                                                           #
    # ------------------------------------------------------------------ #
    op.alter_column("securities", "currency", server_default="'USD'")

    # ------------------------------------------------------------------ #
    # transactions                                                         #
    # ------------------------------------------------------------------ #
    op.drop_index("idx_transactions_account_created", table_name="transactions")
    op.drop_constraint("fk_transactions_account_id", "transactions", type_="foreignkey")
    op.create_foreign_key(
        "transactions_account_id_fkey", "transactions", "accounts", ["account_id"], ["account_id"]
    )
    op.drop_constraint("ck_transactions_amount_positive", "transactions", type_="check")
    op.alter_column("transactions", "currency", server_default="'USD'")
    op.alter_column("transactions", "status", server_default="'pending'")

    # ------------------------------------------------------------------ #
    # accounts                                                             #
    # ------------------------------------------------------------------ #
    op.drop_constraint("ck_accounts_balance_non_negative", "accounts", type_="check")
    op.drop_constraint("fk_accounts_user_id", "accounts", type_="foreignkey")
    op.create_foreign_key(
        "accounts_user_id_fkey", "accounts", "users", ["user_id"], ["user_id"]
    )
    op.alter_column("accounts", "user_id", nullable=True)
    op.alter_column("accounts", "currency", server_default="'USD'")
    op.alter_column("accounts", "status", server_default="'active'")
