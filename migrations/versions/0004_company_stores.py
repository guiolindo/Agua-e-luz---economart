"""lista oficial de lojas da empresa

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-13 12:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

COLUMNS = [
    sa.Column('official', sa.Boolean(), nullable=True),
    sa.Column('cnpj', sa.String(length=20), nullable=True),
    sa.Column('company', sa.String(length=60), nullable=True),
    sa.Column('group_name', sa.String(length=120), nullable=True),
    sa.Column('details', sa.JSON(), nullable=True),
]


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("stores")}
    missing = [c for c in COLUMNS if c.name not in have]       # banco já criado com o modelo atual: nada a fazer
    if missing:
        with op.batch_alter_table('stores', schema=None) as batch_op:
            for col in missing:
                batch_op.add_column(col)
    indexes = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("stores")}
    if "ix_stores_cnpj" not in indexes:
        with op.batch_alter_table('stores', schema=None) as batch_op:
            batch_op.create_index('ix_stores_cnpj', ['cnpj'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('stores', schema=None) as batch_op:
        batch_op.drop_index('ix_stores_cnpj')
        for col in reversed(COLUMNS):
            batch_op.drop_column(col.name)
