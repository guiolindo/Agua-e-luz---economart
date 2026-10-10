"""Migrações (Alembic): banco novo, banco antigo adotado sem perder dados e ausência de divergência com os modelos."""
from sqlalchemy import inspect, text

from app import database, db_migrate


def _engine(tmp_path, name="m.db"):
    return database.make_engine(f"sqlite:///{tmp_path}/{name}")


def _head() -> str:
    from alembic.script import ScriptDirectory

    from app.db_migrate import _config

    return ScriptDirectory.from_config(_config(None)).get_current_head()


def _version(eng) -> str:
    with eng.connect() as c:
        return c.execute(text("SELECT version_num FROM alembic_version")).scalar()


def test_fresh_database_is_created_by_migrations_and_matches_the_models(tmp_path):
    eng = _engine(tmp_path)
    db_migrate.upgrade(eng)
    tables = set(inspect(eng).get_table_names())
    assert tables == {t.name for t in database.Base.metadata.sorted_tables} | {"alembic_version"}
    assert db_migrate.drift(eng) == []        # se alguém mudar um modelo sem criar migração, este teste quebra


def test_upgrade_is_idempotent(tmp_path):
    eng = _engine(tmp_path)
    db_migrate.upgrade(eng)
    first = _version(eng)
    db_migrate.upgrade(eng)
    assert _version(eng) == first


def test_pre_alembic_database_is_adopted_without_losing_data(tmp_path):
    eng = _engine(tmp_path, "legacy.db")
    database.Base.metadata.create_all(eng)                       # como era em produção antes do Alembic
    with eng.begin() as c:
        c.execute(text("INSERT INTO users (username, password_hash, role, active, created_at, updated_at) "
                       "VALUES ('maria', 'x', 'operator', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
        c.execute(text("ALTER TABLE users DROP COLUMN totp_secret"))      # banco de antes do 2FA
        c.execute(text("ALTER TABLE audit_log DROP COLUMN row_hash"))     # e de antes da auditoria selada
    assert "alembic_version" not in inspect(eng).get_table_names()
    db_migrate.upgrade(eng)
    cols = {c["name"] for c in inspect(eng).get_columns("users")}
    assert "totp_secret" in cols and "row_hash" in {c["name"] for c in inspect(eng).get_columns("audit_log")}
    with eng.connect() as c:
        assert c.execute(text("SELECT username FROM users")).scalar() == "maria"          # dados intactos
    assert _version(eng) == _head()                      # carimbou 0001 e aplicou as migrações seguintes
    assert "alert_acks" in inspect(eng).get_table_names()
    assert db_migrate.drift(eng) == []


def test_pre_alembic_database_missing_a_newer_table_is_completed_too(tmp_path):
    eng = _engine(tmp_path, "older.db")
    database.Base.metadata.create_all(eng)
    with eng.begin() as c:
        c.execute(text("DROP TABLE alert_acks"))                 # banco de antes dos alertas
    db_migrate.upgrade(eng)
    assert "alert_acks" in inspect(eng).get_table_names() and _version(eng) == _head()
    assert db_migrate.drift(eng) == []


def test_revisions_already_applied_in_production_stay_in_the_chain():
    """Um banco carimbado em 0003 (aplicada em produção) precisa continuar reconhecido; remover a revisão impede o start."""
    from alembic.script import ScriptDirectory

    from app.db_migrate import _config

    ids = {s.revision for s in ScriptDirectory.from_config(_config(None)).walk_revisions()}
    assert {"0001", "0002", "0003"} <= ids
