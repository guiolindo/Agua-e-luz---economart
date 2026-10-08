"""Ambiente do Alembic: usa os modelos do app e o mesmo DATABASE_URL."""
from alembic import context

from app import database, models  # noqa: F401  (models registra as tabelas no metadata)

target_metadata = database.Base.metadata


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True,
                      render_as_batch=connection.dialect.name == "sqlite")
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = context.config.attributes.get("connection")
    if connection is not None:                       # chamado pelo app/testes com conexão pronta
        _run(connection)
        return
    with database.engine.connect() as conn:
        _run(conn)
        conn.commit()


if context.is_offline_mode():
    raise SystemExit("Modo offline não é suportado: rode com acesso ao banco.")
run_migrations_online()
