"""create product_documents table

Revision ID: 4aa1b2bf2668
Revises: 85318a34438d
Create Date: 2026-10-27 18:45:10

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision: str = '4aa1b2bf2668'
down_revision: str | None = '85318a34438d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.create_table('product_documents',
    sa.Column('product_id', sa.Uuid(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('embedding', Vector(384), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('product_id')
    )
    op.create_index(
        'ix_product_documents_embedding',
        'product_documents',
        ['embedding'],
        unique=False,
        postgresql_using='hnsw',
        postgresql_with={'m': 16, 'ef_construction': 64},
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )


def downgrade() -> None:
    op.drop_index('ix_product_documents_embedding', table_name='product_documents')
    op.drop_table('product_documents')
