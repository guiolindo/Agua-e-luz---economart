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
        # O gateway do Railway derruba conexões Postgres ociosas: sem isto, a 1ª tela depois de alguns minutos parado
        # pode dar erro ("SSL SYSCALL error: EOF detected"). Três camadas: testa a conexão antes de usar, renova as
        # que têm mais de 3 min e manda keep-alive TCP a cada 30 s para ela não ser vista como ociosa.
        kwargs["pool_pre_ping"] = True
        kwargs["pool_recycle"] = 180
        kwargs["connect_args"] = {"keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10,
                                  "keepalives_count": 5, "connect_timeout": 10}
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
