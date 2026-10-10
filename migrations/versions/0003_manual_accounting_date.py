"""revisão 0003 (sem alterações no esquema)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-10 00:22:47.301163

Esta revisão já foi aplicada em bancos de produção (criava a coluna
manual_records.accounting_date, depois abandonada). Ela permanece na cadeia,
vazia, para que esses bancos continuem reconhecidos. A coluna que ficou nesses
bancos é nula e não é usada pelo sistema.
"""

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
