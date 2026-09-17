"""Portal GET /services — catálogo tipado administrativo (G1)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.radius.contract import ServicioConectividad
from app.services.portal_services import canonical_service_type
from main import app

client = TestClient(app)


def _portal_identified(dni: str = "30111222") -> dict:
    start = client.post(
        "/api/v1/portal/auth/start",
        json={"dni": dni, "org_slug": "coop-batan"},
    )
    assert start.status_code == 200, start.text
    otp = start.json()["debug_otp"]
    verify = client.post(
        "/api/v1/portal/auth/verify",
        json={
            "challenge_id": start.json()["challenge_id"],
            "otp": otp,
            "org_slug": "coop-batan",
        },
    )
    assert verify.status_code == 200, verify.text
    return verify.json()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Canal": "app"}


def _svc(**kwargs) -> ServicioConectividad:
    defaults = {
        "login": "",
        "service_type_code": "",
        "service_type_label": "",
        "product": "",
        "label": "",
        "state": "Habilitado",
        "service_on": True,
        "base_account_number": "200",
        "id": "svc-x",
    }
    defaults.update(kwargs)
    return ServicioConectividad(**defaults)


def test_canonical_mapping_codes():
    assert canonical_service_type(_svc(service_type_code="INTFO")) == "internet"
    assert canonical_service_type(_svc(service_type_code="INTBA")) == "internet"
    assert canonical_service_type(_svc(service_type_code="INTINA")) == "internet"
    assert canonical_service_type(_svc(service_type_code="SENSA")) == "tv"
    assert canonical_service_type(_svc(service_type_code="OTT")) == "tv"
    assert canonical_service_type(_svc(service_type_code="IMOWI")) == "movil"
    assert canonical_service_type(_svc(service_type_code="CEL")) == "movil"
    assert canonical_service_type(_svc(service_type_code="XYZ99", label="Pack raro")) == "other"


def test_services_requiere_jwt():
    client.cookies.clear()
    r = client.get("/api/v1/portal/services", headers={"X-Canal": "app"})
    assert r.status_code == 401


def test_services_requiere_identificado():
    from app.api.v1 import portal as portal_mod

    token = portal_mod._crear_portal_token(
        org_id="org-x",
        org_slug="coop-batan",
        conversacion_id="c1",
        telefono="",
        dni="30111222",
        identified=False,
        abonado_id="",
    )
    r = client.get("/api/v1/portal/services", headers=_headers(token))
    assert r.status_code == 403


def test_services_internet_y_movil_mock_default():
    """DNI demo 30111222: mock BillTrack con INTFO + IMOWI."""
    auth = _portal_identified("30111222")
    r = client.get("/api/v1/portal/services", headers=_headers(auth["portal_token"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["services"], list)
    types = {s["type"] for s in body["services"]}
    assert "internet" in types
    assert "movil" in types
    for s in body["services"]:
        assert s["id"]
        assert s["type"] in ("internet", "tv", "movil", "telefonia", "other")
        assert "label" in s
        assert "product" in s
        assert isinstance(s["active"], bool)
        # No filtrar contrato de producto desde tokens libres.
        assert "abonado.servicio" not in str(s)
        assert "login" not in s
        assert "service_type_code" not in s


def test_services_multiples_tipados():
    auth = _portal_identified("30111222")
    catalog = [
        _svc(
            id="i1",
            service_type_code="INTFO",
            label="Internet Fibra",
            product="Fibra 300M",
        ),
        _svc(
            id="t1",
            service_type_code="SENSA",
            label="TV OTT",
            product="Sensa",
        ),
        _svc(
            id="m1",
            service_type_code="IMOWI",
            label="Móvil",
            product="",
        ),
        _svc(
            id="o1",
            service_type_code="FOOBAR",
            label="Pack legado",
            product=None,
        ),
    ]
    # product=None not valid on dataclass — empty string maps to null
    catalog[3] = _svc(id="o1", service_type_code="FOOBAR", label="Pack legado", product="")

    with patch(
        "app.services.billtrack.lookup_servicios_cuenta_por_dni",
        return_value=(catalog, True),
    ):
        r = client.get(
            "/api/v1/portal/services",
            headers=_headers(auth["portal_token"]),
        )
    assert r.status_code == 200, r.text
    by_id = {s["id"]: s for s in r.json()["services"]}
    assert by_id["i1"]["type"] == "internet"
    assert by_id["i1"]["product"] == "Fibra 300M"
    assert by_id["t1"]["type"] == "tv"
    assert by_id["t1"]["product"] == "Sensa"
    assert by_id["m1"]["type"] == "movil"
    assert by_id["m1"]["product"] is None
    assert by_id["o1"]["type"] == "other"
    assert by_id["o1"]["product"] is None


def test_services_tv_sin_estado_operativo():
    auth = _portal_identified("30111222")
    catalog = [
        _svc(id="tv1", service_type_code="SENSA", label="Sensa", product="Sensa Básico"),
    ]
    with patch(
        "app.services.billtrack.lookup_servicios_cuenta_por_dni",
        return_value=(catalog, True),
    ):
        r = client.get(
            "/api/v1/portal/services",
            headers=_headers(auth["portal_token"]),
        )
    assert r.status_code == 200
    s = r.json()["services"][0]
    assert s["type"] == "tv"
    assert s["active"] is True
    raw = str(r.json()).lower()
    assert "operational" not in raw
    assert "online" not in raw
    assert "bcm" not in raw


def test_services_product_null_si_falta():
    auth = _portal_identified("30111222")
    catalog = [
        _svc(id="i2", service_type_code="INTBA", label="Internet radio", product=""),
    ]
    with patch(
        "app.services.billtrack.lookup_servicios_cuenta_por_dni",
        return_value=(catalog, True),
    ):
        r = client.get(
            "/api/v1/portal/services",
            headers=_headers(auth["portal_token"]),
        )
    assert r.json()["services"][0]["product"] is None


def test_services_no_acepta_client_id_ajeno():
    """Query params arbitrarios no cambian el abonado del JWT."""
    auth = _portal_identified("30111222")
    with patch(
        "app.services.billtrack.lookup_servicios_cuenta_por_dni",
        return_value=(
            [_svc(id="own", service_type_code="INTFO", label="Mio", product="P")],
            True,
        ),
    ) as mocked:
        r = client.get(
            "/api/v1/portal/services",
            params={
                "client_id": "999",
                "abonado_id": "otro",
                "dni": "26444555",
                "client_number": "999",
            },
            headers=_headers(auth["portal_token"]),
        )
    assert r.status_code == 200
    assert r.json()["services"][0]["id"] == "own"
    # Lookup se hizo con el DNI del JWT, no con el query.
    assert mocked.call_args.kwargs["dni"] == "30111222"


def test_services_source_unavailable():
    auth = _portal_identified("30111222")
    with patch(
        "app.services.billtrack.lookup_servicios_cuenta_por_dni",
        return_value=([], False),
    ):
        r = client.get(
            "/api/v1/portal/services",
            headers=_headers(auth["portal_token"]),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "unavailable"
    assert body["services"] == []
    assert body["reason_code"] == "source_unavailable"


def test_services_omite_sin_id_estable():
    auth = _portal_identified("30111222")
    catalog = [
        _svc(id="", service_type_code="INTFO", label="Sin id"),
        _svc(id="ok", service_type_code="INTFO", label="Con id", product="X"),
    ]
    with patch(
        "app.services.billtrack.lookup_servicios_cuenta_por_dni",
        return_value=(catalog, True),
    ):
        r = client.get(
            "/api/v1/portal/services",
            headers=_headers(auth["portal_token"]),
        )
    ids = [s["id"] for s in r.json()["services"]]
    assert ids == ["ok"]


def test_services_omite_historicos_y_dedupe_por_tipo():
    """Bajas no salen; varias réplicas del mismo tipo → una (preferir activo)."""
    auth = _portal_identified("30111222")
    catalog = [
        _svc(
            id="i-old",
            service_type_code="INTFO",
            label="Internet Fibra",
            product="Fibra 100",
            state="Baja",
            service_on=False,
        ),
        _svc(
            id="i-dup",
            service_type_code="INTFO",
            label="Internet",
            product="Fibra 300",
            state="Habilitado",
        ),
        _svc(
            id="i-ok",
            service_type_code="INTBA",
            label="Internet radio",
            product="BAI 20",
            state="Habilitado",
        ),
        _svc(
            id="t-old",
            service_type_code="SENSA",
            label="TV",
            product="Sensa",
            state="de baja",
            service_on=False,
        ),
        _svc(
            id="t-ok",
            service_type_code="OTT",
            label="TV OTT",
            product="Sensa Plus",
            state="Habilitado",
        ),
        _svc(
            id="m1",
            service_type_code="IMOWI",
            label="Móvil",
            product="",
            state="Habilitado",
        ),
        _svc(
            id="m2",
            service_type_code="CEL",
            label="Celular",
            product="IMOWI",
            state="Habilitado",
        ),
    ]
    with patch(
        "app.services.billtrack.lookup_servicios_cuenta_por_dni",
        return_value=(catalog, True),
    ):
        r = client.get(
            "/api/v1/portal/services",
            headers=_headers(auth["portal_token"]),
        )
    assert r.status_code == 200, r.text
    services = r.json()["services"]
    types = [s["type"] for s in services]
    assert types.count("internet") == 1
    assert types.count("tv") == 1
    assert types.count("movil") == 1
    ids = {s["id"] for s in services}
    assert "i-old" not in ids
    assert "t-old" not in ids
    # Preferencia: primer activo visto tras filtro (BillTrack ordena vigentes primero).
    by_type = {s["type"]: s["id"] for s in services}
    assert by_type["internet"] == "i-dup"
    assert by_type["tv"] == "t-ok"
    assert by_type["movil"] == "m1"


def test_es_historico_service_on_falso_sin_estado_vivo():
    from app.services.portal_services import es_historico_catalogo

    assert es_historico_catalogo(_svc(state="Baja", service_on=False)) is True
    assert es_historico_catalogo(_svc(state="de baja", service_on=True)) is True
    assert es_historico_catalogo(_svc(state="", service_on=False)) is True
    assert es_historico_catalogo(_svc(state="Habilitado", service_on=True)) is False
    assert es_historico_catalogo(_svc(state="Suspendido", service_on=True)) is False
