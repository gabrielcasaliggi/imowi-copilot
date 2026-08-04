"""Tests de lookup BillTrack (api_person / mapeo DNI-CUIT)."""

from __future__ import annotations

from app.services.billtrack import DEFAULT_LOOKUP_SQL, lookup_sql, map_lookup_row


def test_default_sql_usa_api_person():
    sql = lookup_sql().lower()
    assert "api_person" in sql
    assert "api_person_email" in sql
    assert "api_person_phone" in sql
    assert ":dni" in lookup_sql()
    assert "doc_cuit" in sql
    assert DEFAULT_LOOKUP_SQL.strip().lower().startswith("select")


def test_lookup_billtrack_falla_en_prod_no_tira(monkeypatch):
    """En producción un fallo de red/SQL no debe propagarse (evita 500 en login-pin)."""
    from app.services import billtrack as bt

    monkeypatch.setattr(bt, "resolve_connection", lambda db=None: {
        "enabled": True,
        "url": "postgresql+psycopg://u:p@127.0.0.1:1/db",
        "sslmode": "disable",
    })
    monkeypatch.setenv("BILLTRACK_LOOKUP_READY", "1")
    import app.config as cfg

    monkeypatch.setattr(cfg, "BILLTRACK_ENABLED", True)
    monkeypatch.setattr(cfg, "es_produccion", lambda: True)

    class Boom:
        def connect(self):
            raise OSError("billtrack down")

        def dispose(self):
            return None

    import sqlalchemy

    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *a, **k: Boom())

    hit = bt.lookup_abonado_por_dni("11350542", org_slug="coop-batan", db=None)
    assert hit is None

    hit = map_lookup_row(
        {
            "ref": "9",
            "nombre": "Cliente Baja",
            "email": "baja@coop.test",
            "telefono": "5492231112222",
            "activo": "de baja",
            "deuda": "0",
        },
        dni_n="13920806",
    )
    assert hit["activo"] is False
    assert "baja" in hit["estado_padron"]
    assert hit["dni"] == "13920806"


def test_map_lookup_row_activo_y_aliases():
    row = {
        "ref": "42",
        "nombre": "María González",
        "email": "maria@coop.test",
        "telefono": "5492235551234",
        "activo": "Activo",
        "deuda": "1500.00",
        "doc_cuit": "20301112223",
        "partner_number": "100",
        "client_number": "200",
    }
    hit = map_lookup_row(row, dni_n="30111222")
    assert hit["ref"] == "42"
    assert hit["activo"] is True
    assert hit["email"] == "maria@coop.test"
    assert hit["dni"] == "30111222"
    assert hit["fuente"] == "billtrack"


def test_map_lookup_row_inactivo():
    hit = map_lookup_row(
        {"ref": "1", "nombre": "X", "email": "x@y.com", "telefono": "", "activo": "baja"},
        dni_n="28555666",
    )
    assert hit["activo"] is False


def test_mock_lookup_dev_sin_billtrack():
    from app.services.billtrack import lookup_abonado_por_dni

    hit = lookup_abonado_por_dni("30111222", org_slug="coop-batan", db=None)
    assert hit is not None
    assert hit["email"]
    assert hit.get("fuente") in ("mock", "mock_local", None) or hit["nombre"]
