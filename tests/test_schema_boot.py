"""create_all no corre en production postgres con estate ya creado."""

from __future__ import annotations

from sqlalchemy import create_engine

from alembic import command
from app.estate import migrate as mig
from app.estate.migrate import sincronizar_alembic


class _Dialect:
    name = "postgresql"


class _Engine:
    dialect = _Dialect()


class _Insp:
    def __init__(self, tables: set[str]):
        self.tables = tables

    def has_table(self, name: str) -> bool:
        return name in self.tables


def test_dev_siempre_create_all(monkeypatch):
    monkeypatch.setattr(mig, "es_produccion", lambda: False)
    monkeypatch.setattr(mig, "es_postgres", lambda: False)
    created: list[object] = []
    monkeypatch.setattr(mig.Base.metadata, "create_all", lambda **kw: created.append(kw))
    monkeypatch.setattr(mig, "migrate_schema", lambda engine: ["migrado"])
    monkeypatch.setattr(mig, "sincronizar_alembic", lambda engine: [])

    assert mig.aplicar_schema(_Engine()) == ["migrado"]
    assert created


def test_prod_postgres_con_estate_omite_create_all(monkeypatch):
    monkeypatch.setattr(mig, "es_produccion", lambda: True)
    monkeypatch.setattr(mig, "es_postgres", lambda: True)
    monkeypatch.setattr(mig, "inspect", lambda engine: _Insp({"tickets_estate"}))
    created: list[object] = []
    monkeypatch.setattr(mig.Base.metadata, "create_all", lambda **kw: created.append(kw))
    monkeypatch.setattr(mig, "migrate_schema", lambda engine: [])
    monkeypatch.setattr(mig, "sincronizar_alembic", lambda engine: ["alembic stamp head"])

    assert mig.aplicar_schema(_Engine()) == ["alembic stamp head"]
    assert created == []


def test_prod_postgres_vacio_si_crea_tablas(monkeypatch):
    monkeypatch.setattr(mig, "es_produccion", lambda: True)
    monkeypatch.setattr(mig, "es_postgres", lambda: True)
    monkeypatch.setattr(mig, "inspect", lambda engine: _Insp(set()))
    created: list[object] = []
    monkeypatch.setattr(mig.Base.metadata, "create_all", lambda **kw: created.append(kw))
    monkeypatch.setattr(mig, "migrate_schema", lambda engine: ["audit_events"])
    monkeypatch.setattr(mig, "sincronizar_alembic", lambda engine: [])

    assert mig.aplicar_schema(_Engine()) == ["audit_events"]
    assert created


def test_alembic_sqlite_es_noop():
    engine = create_engine("sqlite:///:memory:")
    assert sincronizar_alembic(engine) == []


def test_alembic_postgres_sin_version_hace_stamp(monkeypatch):
    monkeypatch.setattr(mig, "inspect", lambda engine: _Insp(set()))
    stamped: list[str] = []

    def boom_upgrade(cfg, rev):
        raise AssertionError("upgrade no")

    monkeypatch.setattr(command, "stamp", lambda cfg, rev: stamped.append(rev))
    monkeypatch.setattr(command, "upgrade", boom_upgrade)

    assert mig.sincronizar_alembic(_Engine()) == ["alembic stamp head"]
    assert stamped == ["head"]


def test_alembic_postgres_con_version_hace_upgrade(monkeypatch):
    monkeypatch.setattr(mig, "inspect", lambda engine: _Insp({"alembic_version"}))
    upgraded: list[str] = []

    def boom_stamp(cfg, rev):
        raise AssertionError("stamp no")

    monkeypatch.setattr(command, "stamp", boom_stamp)
    monkeypatch.setattr(command, "upgrade", lambda cfg, rev: upgraded.append(rev))

    assert mig.sincronizar_alembic(_Engine()) == ["alembic upgrade head"]
    assert upgraded == ["head"]


def test_alembic_env_no_desactiva_loggers_existentes():
    from pathlib import Path

    env = Path(__file__).resolve().parents[1] / "alembic" / "env.py"
    text = env.read_text(encoding="utf-8")
    assert "disable_existing_loggers=False" in text


def test_restaurar_logging_app_deja_info():
    import logging

    logging.getLogger("operations_hub").setLevel(logging.WARNING)
    mig.restaurar_logging_app()
    assert logging.getLogger("operations_hub").level == logging.INFO
