"""IPs públicos da empresa, cadastrados pelo administrador (rede da empresa na auditoria)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-15 18:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "company_networks" in sa.inspect(op.get_bind()).get_table_names():   # banco já criado com o modelo atual
        return
    op.create_table(
        'company_networks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cidr', sa.String(length=64), nullable=False),
        sa.Column('label', sa.String(length=80), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cidr'),
    )


def downgrade() -> None:
    op.drop_table('company_networks')
