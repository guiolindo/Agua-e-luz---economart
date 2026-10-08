from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None):
    url = url or get_settings().database_url
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_pre_ping"] = True
    return create_engine(url, **kwargs)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def ensure_columns(target=None) -> None:
    """Completa colunas novas (anuláveis) em tabelas já existentes. Aceita engine ou conexão.
    Só é usada para adotar bancos criados antes do Alembic; mudanças de esquema agora são migrações."""
    from sqlalchemy import inspect, text
    from sqlalchemy.engine import Connection

    target = target or engine

    def run(conn) -> None:
        insp = inspect(conn)
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in have and col.nullable:
                    ddl = col.type.compile(dialect=conn.dialect)
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl}'))

    if isinstance(target, Connection):
        run(target)
    else:
        with target.begin() as conn:
            run(conn)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
