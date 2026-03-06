"""
0011_user_preferences — Add JSONB preferences column to users table.

Stores user settings (currency, language) as a flexible JSON object.
Default is an empty object so existing users have no preferences
until they explicitly set them.

Revision: 0011_user_preferences
Revises:  0010_score_feedback
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# Revision identifiers
revision = "0011_user_preferences"
down_revision = "0010_score_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add preferences JSONB column to users table."""
    op.add_column(
        "users",
        sa.Column(
            "preferences",
            JSONB,
            server_default="{}",
            nullable=True,
            comment="User preferences JSON: currency, language, etc.",
        ),
    )


def downgrade() -> None:
    """Remove preferences column from users table."""
    op.drop_column("users", "preferences")
