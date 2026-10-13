"""última atividade do usuário (quem está on-line)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-13 15:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}
    if "last_seen_at" not in have:                       # banco já criado com o modelo atual: nada a fazer
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.add_column(sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('last_seen_at')
