"""lixeira: contas e lançamentos excluídos ficam guardados para restaurar

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-14 18:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "trash_items" in sa.inspect(op.get_bind()).get_table_names():   # banco já criado com o modelo atual
        return
    op.create_table(
        'trash_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=30), nullable=False),
        sa.Column('original_id', sa.Integer(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=True),
        sa.Column('summary', sa.String(length=300), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('deleted_by', sa.Integer(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('restored_by', sa.Integer(), nullable=True),
        sa.Column('restored_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['deleted_by'], ['users.id']),
        sa.ForeignKeyConstraint(['restored_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_trash_items_kind', 'trash_items', ['kind'])
    op.create_index('ix_trash_items_store_id', 'trash_items', ['store_id'])
    op.create_index('ix_trash_items_deleted_by', 'trash_items', ['deleted_by'])
    op.create_index('ix_trash_items_deleted_at', 'trash_items', ['deleted_at'])


def downgrade() -> None:
    op.drop_table('trash_items')
