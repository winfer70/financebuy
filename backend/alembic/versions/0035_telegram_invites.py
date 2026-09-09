"""Per-user Telegram chat linking: telegram_invites table + users columns."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_invites",
        sa.Column("invite_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "used_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("code", name="uq_telegram_invites_code"),
    )
    op.create_index("idx_telegram_invites_code", "telegram_invites", ["code"])

    op.add_column("users", sa.Column("telegram_chat_id", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("telegram_link_code", sa.String(16), nullable=True))
    op.add_column(
        "users", sa.Column("telegram_link_code_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "idx_users_telegram_link_code", "users", ["telegram_link_code"], unique=True,
        postgresql_where=sa.text("telegram_link_code IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_users_telegram_link_code", table_name="users")
    op.drop_column("users", "telegram_link_code_expires_at")
    op.drop_column("users", "telegram_link_code")
    op.drop_column("users", "telegram_chat_id")
    op.drop_index("idx_telegram_invites_code", table_name="telegram_invites")
    op.drop_table("telegram_invites")
