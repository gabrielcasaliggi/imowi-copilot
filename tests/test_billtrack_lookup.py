"""Tests de lookup BillTrack (api_person / mapeo DNI-CUIT)."""

from __future__ import annotations

from types import SimpleNamespace

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
    assert hit["client_number"] == "200"
    assert hit["partner_number"] == "100"


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
    assert hit.get("client_number") == "200"


def test_ensure_local_abonado_persiste_client_number():
    """Al identificar, BillTrack client_number queda en la réplica local (BCM `numero`)."""
    from app.estate.database import get_session_factory
    from app.estate.repository import get_org_by_slug
    from app.services.billtrack import ensure_local_abonado

    Session = get_session_factory()
    with Session() as db:
        org = get_org_by_slug(db, "coop-batan")
        assert org is not None
        abo = ensure_local_abonado(
            db,
            org.id,
            {
                "dni": "30111222",
                "nombre": "María González",
                "telefono": "5492235551234",
                "activo": True,
                "deuda": "0",
                "client_number": "200",
                "fuente": "billtrack",
            },
        )
        assert abo.client_number == "200"


def test_resolver_bcm_usa_client_number_sin_reconsultar(monkeypatch):
    from app.services import billtrack as bt
    from app.services import conexion_bcm as cb

    def _boom(*_a, **_k):
        raise AssertionError("no debe reconsultar BillTrack si ya hay client_number")

    monkeypatch.setattr(bt, "lookup_abonado_por_dni", _boom)
    nro = cb.resolver_numero_cliente_bcm(
        SimpleNamespace(dni="30111222", client_number="200"), db=None
    )
    assert nro == "200"


def test_resolver_bcm_cae_a_billtrack_por_dni(monkeypatch):
    from app.services import billtrack as bt
    from app.services import conexion_bcm as cb

    monkeypatch.setattr(
        bt, "lookup_abonado_por_dni", lambda dni, db=None, **_k: {"client_number": "200"}
    )
    nro = cb.resolver_numero_cliente_bcm(
        SimpleNamespace(dni="30111222", client_number=""), db=None
    )
    assert nro == "200"


def test_clasificar_servicios_cuenta_internet_y_movil():
    from app.radius.contract import ServicioConectividad
    from app.services.billtrack import clasificar_servicios_cuenta

    fibra = ServicioConectividad(
        login="1",
        service_type_code="INTFO",
        service_type_label="Fibra Optica",
        product="Fibra 100",
    )
    movil = ServicioConectividad(
        login="",
        service_type_code="IMOWI",
        service_type_label="Móvil IMOWI",
        product="Móvil 5GB",
    )
    assert clasificar_servicios_cuenta([fibra]) == "internet"
    assert clasificar_servicios_cuenta([movil]) == "movil"
    assert clasificar_servicios_cuenta([fibra, movil]) == "ambos"
    assert clasificar_servicios_cuenta([]) == ""
