"""use clock timestamp for messages

Revision ID: 16cb7f8514ae
Revises: 7ee9424261b8
Create Date: 2026-10-12 17:08:49.669747

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '16cb7f8514ae'
down_revision: Union[str, Sequence[str], None] = '7ee9424261b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "messages",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        server_default=sa.text("clock_timestamp()"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "messages",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        server_default=sa.text("now()"),
    )
