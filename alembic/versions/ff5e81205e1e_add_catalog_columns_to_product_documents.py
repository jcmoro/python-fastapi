"""add catalog columns to product_documents

Revision ID: ff5e81205e1e
Revises: 4aa1b2bf2668
Create Date: 2026-10-27 22:38:12

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'ff5e81205e1e'
down_revision: str | None = '4aa1b2bf2668'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('product_documents', sa.Column('sku', sa.String(length=64), nullable=True))
    op.add_column('product_documents', sa.Column('name', sa.String(length=200), nullable=True))
    op.add_column('product_documents', sa.Column('price_cents', sa.Integer(), nullable=True))
    op.add_column('product_documents', sa.Column('currency', sa.String(length=3), nullable=True))
    op.create_index(op.f('ix_product_documents_sku'), 'product_documents', ['sku'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_product_documents_sku'), table_name='product_documents')
    op.drop_column('product_documents', 'currency')
    op.drop_column('product_documents', 'price_cents')
    op.drop_column('product_documents', 'name')
    op.drop_column('product_documents', 'sku')
