"""Migrações do banco (Alembic) com adoção segura de bancos que já existiam antes dele.

- Banco novo/vazio: `upgrade head` cria tudo.
- Banco antigo (tem tabelas do sistema, mas não `alembic_version`): primeiro completa colunas que faltem
  (`ensure_columns`, o mecanismo anterior), carimba como a revisão baseline (0001, sem alterar nada) e só então aplica
  as migrações posteriores.
Mudanças de esquema daqui em diante: `alembic revision --autogenerate -m "descrição"` e commitar o arquivo gerado.
"""
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app import database

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
BASELINE = "0001"


def _config(connection) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.attributes["connection"] = connection
    return cfg


def upgrade(engine=None) -> None:
    engine = engine or database.engine
    with engine.begin() as conn:
        tables = set(inspect(conn).get_table_names())
        cfg = _config(conn)
        if "alembic_version" not in tables and "users" in tables:
            # Banco criado antes do Alembic (create_all + ensure_columns). Traz-o ao esquema atual sem tocar nos dados;
            # se ficar idêntico aos modelos, carimba o fim da fila; senão carimba a base e deixa as migrações fecharem.
            log.warning("Banco anterior ao Alembic: completando tabelas/colunas e carimbando a revisão.")
            database.Base.metadata.create_all(conn)
            database.ensure_columns(conn)
            command.stamp(cfg, "head" if not _drift(conn) else BASELINE)
        command.upgrade(cfg, "head")


def _drift(conn) -> list:
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    ctx = MigrationContext.configure(conn, opts={"compare_type": True, "render_as_batch": conn.dialect.name == "sqlite"})
    return compare_metadata(ctx, database.Base.metadata)


def drift(engine=None) -> list:
    """Diferenças entre os modelos e o banco real (lista vazia = em dia). Útil no CI e após restaurar backup."""
    engine = engine or database.engine
    with engine.connect() as conn:
        return _drift(conn)
