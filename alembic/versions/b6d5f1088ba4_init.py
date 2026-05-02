"""init

Revision ID: b6d5f1088ba4
Revises: 
Create Date: 2026-05-02 19:57:56.876420

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'b6d5f1088ba4'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
