"""Add professional credential-review account state.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("valid_user_status", "users", type_="check")
    op.create_check_constraint(
        "valid_user_status",
        "users",
        "status IN ('pending_verification','pending_review','active','suspended','disabled')",
    )


def downgrade() -> None:
    op.execute("UPDATE users SET status = 'pending_verification' WHERE status = 'pending_review'")
    op.drop_constraint("valid_user_status", "users", type_="check")
    op.create_check_constraint(
        "valid_user_status",
        "users",
        "status IN ('pending_verification','active','suspended','disabled')",
    )
