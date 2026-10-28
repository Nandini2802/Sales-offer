"""add session inactivity tracking

Revision ID: 780ea7b95cde
Revises: 16cb7f8514ae
Create Date: 2026-10-20 01:58:07.324278

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '780ea7b95cde'
down_revision: Union[str, Sequence[str], None] = '16cb7f8514ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'sessions',
        sa.Column(
            'last_activity_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        'sessions',
        sa.Column(
            'status',
            sa.String(length=30),
            nullable=False,
            server_default='active',
        ),
    )

    op.execute(
        "UPDATE sessions SET last_activity_at = NOW(), status = 'active' WHERE last_activity_at IS NULL OR status IS NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sessions', 'status')
    op.drop_column('sessions', 'last_activity_at')
