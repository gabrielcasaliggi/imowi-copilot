"""Portal GET /connectivity — C2 Home Status."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.services import connectivity_cache as ccache
from main import app

client = TestClient(app)

_FORBIDDEN = (
    "bcm_",
    "uisp_",
    "pppoe_",
    '"login"',
    "nas_shortname",
    "olt",
    "serial",
    "public_ip",
    "device_id",
    "password",
    "rx_dbm",
    "tx_dbm",
    "mac_address",
)


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


def _assert_no_infra_leak(payload: dict) -> None:
    raw = str(payload).lower()
    for needle in _FORBIDDEN:
        assert needle.lower() not in raw, f"leak: {needle} in {payload}"


def _assert_tss_projection(body: dict) -> None:
    """Campos aditivos de TSS; no reinterpretan el diagnóstico."""
    ev = body["evidence"]
    assert set(ev) == {"session_present", "access_link_up", "access_quality"}
    rec = body["recommendation"]
    assert "recommended_action" in rec
    assert isinstance(rec["available_actions"], list)
    assert "change_wifi" not in rec["available_actions"]
    assert rec["recommended_action"] != "change_wifi"
    assert "reboot" not in rec["available_actions"]
    assert body["actions"]["can_open_chat"] is True


def test_connectivity_requiere_jwt():
    r = client.get("/api/v1/portal/connectivity")
    assert r.status_code == 401


def test_connectivity_requiere_identificado():
    """Token sin identified → 403."""
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
    r = client.get("/api/v1/portal/connectivity", headers=_headers(token))
    assert r.status_code == 403


def test_connectivity_service_id_ajeno_404():
    ccache.clear()
    auth = _portal_identified()
    r = client.get(
        "/api/v1/portal/connectivity",
        params={"service_id": "no-existe-xyz"},
        headers=_headers(auth["portal_token"]),
    )
    assert r.status_code == 404


def test_connectivity_single_service_operational_mocked():
    ccache.clear()
    auth = _portal_identified()
    token = auth["portal_token"]

    onu = MagicMock()
    onu.encontrado = True
    onu.online = True
    onu.calidad_optica = "buena"
    onu.error = ""
    onu.rx_dbm = -22.0

    sesion = MagicMock()
    sesion.online = True
    sesion.nas = "NAS-SECRET"
    sesion.uptime = "1d"
    sesion.error = ""
    sesion.public_ip = "1.2.3.4"

    estado = MagicMock()
    estado.sesion = sesion
    estado.error = ""

    with (
        patch(
            "app.services.conexion_bcm.resolve_bcm_client",
            return_value=object(),
        ),
        patch(
            "app.services.conexion_bcm.consultar_onu_bcm_mejor_esfuerzo",
            return_value=onu,
        ),
        patch(
            "app.services.conexion_pppoe.resolve_radius_client",
            return_value=object(),
        ),
        patch(
            "app.services.conexion_pppoe.consultar_conexion_pppoe",
            return_value=estado,
        ),
        patch(
            "app.services.outages.outage_activo_para_nas",
            return_value=None,
        ),
    ):
        r = client.get(
            "/api/v1/portal/connectivity",
            params={"service_id": "svc-1"},
            headers=_headers(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "operational"
    assert body["freshness"] == "live"
    assert body["reason_code"] is None
    assert body["service"]["id"] == "svc-1"
    assert body["needs_service_selection"] is False
    assert "checked_at" in body
    _assert_tss_projection(body)
    assert body["recommendation"]["recommended_action"] == "none"
    assert body["evidence"]["session_present"] is True
    assert body["evidence"]["access_link_up"] is True
    _assert_no_infra_leak(body)
    assert "NAS-SECRET" not in str(body)
    assert "1.2.3.4" not in str(body)


def test_connectivity_cache_hit():
    ccache.clear()
    auth = _portal_identified()
    token = auth["portal_token"]

    onu = MagicMock()
    onu.encontrado = True
    onu.online = True
    onu.calidad_optica = "buena"
    onu.error = ""

    sesion = MagicMock()
    sesion.online = True
    sesion.nas = "N1"
    sesion.uptime = "1h"
    sesion.error = ""
    estado = MagicMock(sesion=sesion, error="")

    with (
        patch("app.services.conexion_bcm.resolve_bcm_client", return_value=object()),
        patch(
            "app.services.conexion_bcm.consultar_onu_bcm_mejor_esfuerzo",
            return_value=onu,
        ) as bcm_mock,
        patch("app.services.conexion_pppoe.resolve_radius_client", return_value=object()),
        patch(
            "app.services.conexion_pppoe.consultar_conexion_pppoe",
            return_value=estado,
        ),
        patch("app.services.outages.outage_activo_para_nas", return_value=None),
    ):
        r1 = client.get(
            "/api/v1/portal/connectivity",
            params={"service_id": "svc-1"},
            headers=_headers(token),
        )
        assert r1.status_code == 200
        assert r1.json()["freshness"] == "live"
        r2 = client.get(
            "/api/v1/portal/connectivity",
            params={"service_id": "svc-1"},
            headers=_headers(token),
        )
        assert r2.status_code == 200
        assert r2.json()["freshness"] == "cached"
        assert r2.json()["status"] == "operational"
        assert bcm_mock.call_count == 1


def test_connectivity_sources_down_200_unknown():
    ccache.clear()
    auth = _portal_identified()
    with (
        patch("app.services.conexion_bcm.resolve_bcm_client", return_value=None),
        patch("app.services.conexion_pppoe.resolve_radius_client", return_value=None),
    ):
        r = client.get(
            "/api/v1/portal/connectivity",
            params={"service_id": "svc-1"},
            headers=_headers(auth["portal_token"]),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "unknown"
    assert body["reason_code"] in ("sources_unavailable", "insufficient_data")
    _assert_tss_projection(body)
    assert body["recommendation"]["recommended_action"] == "retry_or_eko"
    _assert_no_infra_leak(body)


def test_connectivity_ftth_offline_impaired():
    ccache.clear()
    auth = _portal_identified()
    onu = MagicMock()
    onu.encontrado = True
    onu.online = False
    onu.calidad_optica = ""
    onu.error = ""
    estado = MagicMock(sesion=None, error="")

    with (
        patch("app.services.conexion_bcm.resolve_bcm_client", return_value=object()),
        patch(
            "app.services.conexion_bcm.consultar_onu_bcm_mejor_esfuerzo",
            return_value=onu,
        ),
        patch("app.services.conexion_pppoe.resolve_radius_client", return_value=object()),
        patch(
            "app.services.conexion_pppoe.consultar_conexion_pppoe",
            return_value=estado,
        ),
        patch("app.services.outages.outage_activo_para_nas", return_value=None),
    ):
        r = client.get(
            "/api/v1/portal/connectivity",
            params={"service_id": "svc-1"},
            headers=_headers(auth["portal_token"]),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "impaired"
    assert body["reason_code"] == "access_link_down"
    _assert_tss_projection(body)
    assert body["recommendation"]["recommended_action"] == "talk_to_eko_or_ticket"
    assert body["evidence"]["access_link_up"] is False


def test_connectivity_outage_precedence():
    ccache.clear()
    auth = _portal_identified()
    onu = MagicMock(
        encontrado=True, online=True, calidad_optica="buena", error="", rx_dbm=-20
    )
    sesion = MagicMock(online=True, nas="NAS1", uptime="1h", error="")
    estado = MagicMock(sesion=sesion, error="")
    outage = MagicMock(
        id="out-1",
        estado="activo",
        alcance="total",
        mensaje_cliente="Hay una incidencia en tu zona.",
        eta_minutos=30,
        eta_validada="Sí",
        started_at=datetime.now(UTC),
        nas_shortname="NAS1",
    )

    with (
        patch("app.services.conexion_bcm.resolve_bcm_client", return_value=object()),
        patch(
            "app.services.conexion_bcm.consultar_onu_bcm_mejor_esfuerzo",
            return_value=onu,
        ),
        patch("app.services.conexion_pppoe.resolve_radius_client", return_value=object()),
        patch(
            "app.services.conexion_pppoe.consultar_conexion_pppoe",
            return_value=estado,
        ),
        patch("app.services.outages.outage_activo_para_nas", return_value=outage),
    ):
        r = client.get(
            "/api/v1/portal/connectivity",
            params={"service_id": "svc-1"},
            headers=_headers(auth["portal_token"]),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "outage"
    assert body["reason_code"] == "incident_active"
    assert body["incident"] is not None
    assert body["incident"]["id"] == "out-1"
    assert "eta_confirmed" in body["incident"]
    assert "eta_at" in body["incident"]
    assert body["recommendation"]["recommended_action"] == "wait_outage"
    _assert_tss_projection(body)
    assert "NAS1" not in str(body)
    _assert_no_infra_leak(body)


def test_connectivity_multi_service_selection():
    ccache.clear()
    auth = _portal_identified()
    from app.radius.contract import ServicioConectividad

    multi = [
        ServicioConectividad(
            id="svc-a",
            login="a",
            service_type_code="INTFO",
            product="Fibra A",
            service_on=True,
            state="Habilitado",
        ),
        ServicioConectividad(
            id="svc-b",
            login="b",
            service_type_code="INTBA",
            product="Radio B",
            service_type_label="Inalambrico",
            service_on=True,
            state="Habilitado",
        ),
    ]
    with patch(
        "app.services.billtrack.lookup_servicios_conectividad",
        return_value=multi,
    ), patch(
        "app.services.billtrack.lookup_servicios_conectividad_por_dni",
        return_value=multi,
    ):
        r = client.get(
            "/api/v1/portal/connectivity",
            headers=_headers(auth["portal_token"]),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["needs_service_selection"] is True
    assert body["reason_code"] == "service_selection_required"
    assert body["status"] == "unknown"
    assert isinstance(body["services"], list)
    assert len(body["services"]) == 2
    ids = {s["id"] for s in body["services"]}
    assert ids == {"svc-a", "svc-b"}
    _assert_tss_projection(body)
    assert body["recommendation"]["recommended_action"] == "select_service"
    _assert_no_infra_leak(body)


def test_connectivity_does_not_touch_contexto():
    ccache.clear()
    auth = _portal_identified()
    with (
        patch("app.services.conexion_bcm.resolve_bcm_client", return_value=None),
        patch("app.services.conexion_pppoe.resolve_radius_client", return_value=None),
        patch("app.estate.canal_repo.set_contexto") as set_ctx,
    ):
        r = client.get(
            "/api/v1/portal/connectivity",
            params={"service_id": "svc-1"},
            headers=_headers(auth["portal_token"]),
        )
    assert r.status_code == 200
    set_ctx.assert_not_called()


@contextmanager
def _ftth_patches(*, onu, estado, outage=None):
    with (
        patch("app.services.conexion_bcm.resolve_bcm_client", return_value=object()),
        patch(
            "app.services.conexion_bcm.consultar_onu_bcm_mejor_esfuerzo",
            return_value=onu,
        ),
        patch("app.services.conexion_pppoe.resolve_radius_client", return_value=object()),
        patch(
            "app.services.conexion_pppoe.consultar_conexion_pppoe",
            return_value=estado,
        ),
        patch("app.services.outages.outage_activo_para_nas", return_value=outage),
    ):
        yield


def test_connectivity_no_session():
    ccache.clear()
    auth = _portal_identified()
    onu = MagicMock(
        encontrado=True, online=True, calidad_optica="buena", error="", rx_dbm=-20
    )
    estado = MagicMock(sesion=None, error="")
    with _ftth_patches(onu=onu, estado=estado):
        r = client.get(
            "/api/v1/portal/connectivity",
            params={"service_id": "svc-1"},
            headers=_headers(auth["portal_token"]),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "impaired"
    assert body["reason_code"] == "no_session"
    assert body["evidence"]["session_present"] is False
    assert body["evidence"]["access_link_up"] is True
    assert body["recommendation"]["recommended_action"] == "talk_to_eko"
    _assert_tss_projection(body)
    _assert_no_infra_leak(body)


def test_connectivity_link_quality_poor():
    ccache.clear()
    auth = _portal_identified()
    onu = MagicMock(
        encontrado=True,
        online=True,
        calidad_optica="mala",
        error="",
        rx_dbm=-29.0,
    )
    sesion = MagicMock(online=True, nas="NAS-Q", uptime="2h", error="")
    estado = MagicMock(sesion=sesion, error="")
    with _ftth_patches(onu=onu, estado=estado):
        r = client.get(
            "/api/v1/portal/connectivity",
            params={"service_id": "svc-1"},
            headers=_headers(auth["portal_token"]),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "impaired"
    assert body["reason_code"] == "link_quality_poor"
    assert body["evidence"]["access_quality"] == "poor"
    assert body["recommendation"]["recommended_action"] == "talk_to_eko_or_ticket"
    assert "NAS-Q" not in str(body)
    _assert_tss_projection(body)
    _assert_no_infra_leak(body)


def test_connectivity_historical_outage_is_not_incident_active():
    ccache.clear()
    auth = _portal_identified()
    onu = MagicMock(
        encontrado=True, online=True, calidad_optica="buena", error="", rx_dbm=-20
    )
    sesion = MagicMock(online=True, nas="NAS-H", uptime="1h", error="")
    estado = MagicMock(sesion=sesion, error="")
    historical = MagicMock(
        id="out-old",
        estado="resuelto",
        alcance="total",
        mensaje_cliente="Ya se resolvió.",
        eta_minutos=30,
        eta_validada="Sí",
        started_at=datetime.now(UTC),
        nas_shortname="NAS-H",
    )
    with _ftth_patches(onu=onu, estado=estado, outage=historical):
        r = client.get(
            "/api/v1/portal/connectivity",
            params={"service_id": "svc-1"},
            headers=_headers(auth["portal_token"]),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "operational"
    assert body["reason_code"] is None
    assert body["incident"] is None
    _assert_tss_projection(body)
    _assert_no_infra_leak(body)


def test_connectivity_insufficient_data():
    ccache.clear()
    auth = _portal_identified()
    onu = MagicMock(
        encontrado=True, online=True, calidad_optica="buena", error="", rx_dbm=-20
    )
    estado = MagicMock(sesion=None, error="timeout reading session")
    with _ftth_patches(onu=onu, estado=estado):
        r = client.get(
            "/api/v1/portal/connectivity",
            params={"service_id": "svc-1"},
            headers=_headers(auth["portal_token"]),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "unknown"
    assert body["reason_code"] == "insufficient_data"
    assert body["recommendation"]["recommended_action"] == "retry_or_eko"
    _assert_tss_projection(body)
    _assert_no_infra_leak(body)
