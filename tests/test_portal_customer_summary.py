"""Portal GET /customer-summary — facade Customer Summary (Fase 2D)."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.estate.database import get_session_factory
from app.estate.models import ConversacionCanal
from main import app
from tests.conftest import add_ticket

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


# --- Auth / identity ---


def test_customer_summary_requiere_jwt():
    client.cookies.clear()
    r = client.get("/api/v1/portal/customer-summary", headers={"X-Canal": "app"})
    assert r.status_code == 401


def test_customer_summary_requiere_identificado():
    from app.api.v1 import portal as portal_mod

    token = portal_mod._crear_portal_token(
        org_id="org-x",
        org_slug="coop-batan",
        conversacion_id="c1",
        telefono="",
        dni="30111222",
        identified=False,
        canal="app",
    )
    r = client.get(
        "/api/v1/portal/customer-summary",
        headers=_headers(token),
    )
    assert r.status_code == 403


def test_customer_summary_identidad_jwt():
    sess = _portal_identified("30111222")
    abo_id = (sess.get("conversacion") or {}).get("abonado", {}).get("id")
    assert abo_id
    r = client.get(
        "/api/v1/portal/customer-summary",
        headers=_headers(sess["portal_token"]),
        params={"abonado_id": "otro-id", "dni": "99999999", "client_number": "999"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["customer"]["status"] == "ok"
    assert body["customer"]["data"]["id"] == abo_id
    assert "dni" not in body["customer"]["data"]
    assert "email" not in body["customer"]["data"]
    assert "telefono" not in (body["customer"]["data"] or {})


def test_customer_summary_include_invalido_422():
    sess = _portal_identified()
    r = client.get(
        "/api/v1/portal/customer-summary",
        headers=_headers(sess["portal_token"]),
        params={"include": "customer,foo"},
    )
    assert r.status_code == 422


def test_customer_summary_refresh_invalido_422():
    sess = _portal_identified()
    r = client.get(
        "/api/v1/portal/customer-summary",
        headers=_headers(sess["portal_token"]),
        params={"refresh": "services"},
    )
    assert r.status_code == 422


def test_customer_summary_connectivity_invalido_422():
    sess = _portal_identified()
    r = client.get(
        "/api/v1/portal/customer-summary",
        headers=_headers(sess["portal_token"]),
        params={"connectivity": "full"},
    )
    assert r.status_code == 422


# --- Default: no probes ---


def test_customer_summary_default_sin_probes_tecnicos():
    sess = _portal_identified()
    with (
        patch("app.services.conexion_bcm.resolve_bcm_client") as bcm,
        patch("app.services.conexion_uisp.resolve_uisp_client") as uisp,
        patch("app.services.conexion_pppoe.resolve_radius_client") as radius,
        patch(
            "app.services.portal_connectivity.evaluar_conectividad_portal"
        ) as probe,
    ):
        r = client.get(
            "/api/v1/portal/customer-summary",
            headers=_headers(sess["portal_token"]),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["connectivity"]["status"] == "omitted"
        assert body["connectivity"]["data"] is None
        bcm.assert_not_called()
        uisp.assert_not_called()
        radius.assert_not_called()
        probe.assert_not_called()

        assert body["account"]["status"] == "stale"
        assert body["account"]["reason_code"] == "stale_snapshot"
        assert "status" in body["account"]["data"]
        assert body["billing"]["status"] == "stale"
        assert body["billing"]["data"]["balance"]["as_of"] is None
        assert body["billing"]["data"]["balance"]["currency"] == "ARS"
        assert "ov" in body["billing"]["data"]
        assert body["meta"]["refresh_applied"] == []
        assert "customer" in body["meta"]["include"]


def test_customer_summary_connectivity_summary_sin_probes():
    sess = _portal_identified()
    from app.services.connectivity_evidence import ServiceRef

    ref = ServiceRef(
        id="i1",
        label="Fibra 100",
        type_code="INTFO",
        type_label="Fibra",
        login="user1",
        base_account_number="200",
        product="",
    )
    with (
        patch(
            "app.services.portal_connectivity._load_catalog",
            return_value=[ref],
        ),
        patch("app.services.conexion_bcm.resolve_bcm_client") as bcm,
        patch("app.services.conexion_uisp.resolve_uisp_client") as uisp,
        patch("app.services.conexion_pppoe.resolve_radius_client") as radius,
        patch(
            "app.services.portal_connectivity.evaluar_conectividad_portal"
        ) as probe,
    ):
        r = client.get(
            "/api/v1/portal/customer-summary",
            headers=_headers(sess["portal_token"]),
            params={"connectivity": "summary", "include": "customer"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["connectivity"]["status"] == "ok"
        assert body["connectivity"]["data"]["count"] == 1
        assert body["connectivity"]["data"]["needs_service_selection"] is False
        bcm.assert_not_called()
        uisp.assert_not_called()
        radius.assert_not_called()
        probe.assert_not_called()
        assert body["services"]["status"] == "omitted"


def test_customer_summary_connectivity_probe_invoca_evaluator():
    sess = _portal_identified()
    fake = {
        "status": "operational",
        "freshness": "live",
        "checked_at": "2026-01-01T00:00:00+00:00",
        "message": "ok",
        "access_technology": "ftth",
        "service": {"id": "i1", "label": "Fibra"},
        "incident": None,
        "actions": {"can_open_chat": True},
        "needs_service_selection": False,
        "services": None,
        "reason_code": None,
        "evidence": {"session_present": True},
        "recommendation": {"recommended_action": "none"},
    }
    from app.services.connectivity_evidence import ServiceRef

    ref = ServiceRef(
        id="i1",
        label="Fibra",
        type_code="INTFO",
        type_label="",
        login="u1",
        base_account_number="200",
        product="",
    )
    with (
        patch(
            "app.services.portal_connectivity._load_catalog",
            return_value=[ref],
        ),
        patch(
            "app.services.portal_connectivity.evaluar_conectividad_portal",
            return_value=fake,
        ) as probe,
    ):
        r = client.get(
            "/api/v1/portal/customer-summary",
            headers=_headers(sess["portal_token"]),
            params={"connectivity": "probe", "service_id": "i1", "include": "customer"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["connectivity"]["status"] == "ok"
        assert body["connectivity"]["data"]["status"] == "operational"
        assert "evidence" not in body["connectivity"]["data"]
        assert "recommendation" not in body["connectivity"]["data"]
        probe.assert_called_once()


def test_customer_summary_service_id_ajeno_422():
    sess = _portal_identified()
    from app.services.connectivity_evidence import ServiceRef

    ref = ServiceRef(
        id="mine",
        label="Fibra",
        type_code="INTFO",
        type_label="",
        login="u1",
        base_account_number="200",
        product="",
    )
    with (
        patch(
            "app.services.portal_connectivity._load_catalog",
            return_value=[ref],
        ),
        patch(
            "app.services.portal_connectivity.evaluar_conectividad_portal"
        ) as probe,
    ):
        r = client.get(
            "/api/v1/portal/customer-summary",
            headers=_headers(sess["portal_token"]),
            params={
                "connectivity": "probe",
                "service_id": "ajeno-999",
                "include": "customer",
            },
        )
        assert r.status_code == 422
        probe.assert_not_called()


# --- Services ---


def test_customer_summary_services_empty():
    sess = _portal_identified()
    with patch(
        "app.services.portal_services.evaluar_servicios_portal",
        return_value={
            "status": "ok",
            "checked_at": "t",
            "services": [],
            "reason_code": None,
        },
    ):
        r = client.get(
            "/api/v1/portal/customer-summary",
            headers=_headers(sess["portal_token"]),
            params={"include": "services"},
        )
    assert r.status_code == 200
    assert r.json()["services"]["status"] == "empty"
    assert r.json()["services"]["data"]["items"] == []


def test_customer_summary_services_unavailable_vs_empty():
    sess = _portal_identified()
    with patch(
        "app.services.portal_services.evaluar_servicios_portal",
        return_value={
            "status": "unavailable",
            "checked_at": "t",
            "services": [],
            "reason_code": "source_unavailable",
        },
    ):
        r = client.get(
            "/api/v1/portal/customer-summary",
            headers=_headers(sess["portal_token"]),
            params={"include": "services"},
        )
    assert r.status_code == 200
    assert r.json()["services"]["status"] == "unavailable"
    assert r.json()["services"]["reason_code"] == "source_unavailable"


def test_customer_summary_services_multi_internet():
    sess = _portal_identified()
    items = [
        {
            "id": "a",
            "type": "internet",
            "label": "Fibra A",
            "product": None,
            "active": True,
            "line_msisdn": None,
        },
        {
            "id": "b",
            "type": "internet",
            "label": "Fibra B",
            "product": None,
            "active": True,
            "line_msisdn": None,
        },
    ]
    with patch(
        "app.services.portal_services.evaluar_servicios_portal",
        return_value={
            "status": "ok",
            "checked_at": "t",
            "services": items,
            "reason_code": None,
        },
    ):
        r = client.get(
            "/api/v1/portal/customer-summary",
            headers=_headers(sess["portal_token"]),
            params={"include": "services"},
        )
    assert r.status_code == 200
    body = r.json()["services"]
    assert body["status"] == "ok"
    assert len(body["data"]["items"]) == 2
    assert all("login" not in it for it in body["data"]["items"])


# --- Billing ---


def test_customer_summary_billing_snapshot_as_of_null():
    sess = _portal_identified()
    r = client.get(
        "/api/v1/portal/customer-summary",
        headers=_headers(sess["portal_token"]),
        params={"include": "billing"},
    )
    assert r.status_code == 200
    bal = r.json()["billing"]["data"]["balance"]
    assert bal["as_of"] is None
    assert bal["freshness"] == "snapshot"
    assert isinstance(bal["amount"], str)
    assert "ov" not in r.json()["billing"]["data"]


def test_customer_summary_billing_refresh_success():
    sess = _portal_identified()
    hit = {
        "dni": "30111222",
        "nombre": "María González",
        "activo": True,
        "deuda": "1234.50",
        "client_number": "200",
        "telefono": "5492235551234",
    }
    with patch(
        "app.services.billtrack.lookup_abonado_por_dni",
        return_value=hit,
    ):
        r = client.get(
            "/api/v1/portal/customer-summary",
            headers=_headers(sess["portal_token"]),
            params={"include": "billing,account", "refresh": "billing"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["billing"]["status"] == "ok"
    assert body["billing"]["data"]["balance"]["amount"] == "1234.50"
    assert body["billing"]["data"]["balance"]["as_of"] == body["meta"]["generated_at"]
    assert "billing" in body["meta"]["refresh_applied"]
    assert body["account"]["status"] == "ok"


def test_customer_summary_billing_refresh_failure_preserva_snapshot():
    sess = _portal_identified()
    # baseline amount from mock catalog
    before = client.get(
        "/api/v1/portal/customer-summary",
        headers=_headers(sess["portal_token"]),
        params={"include": "billing"},
    )
    prev_amount = before.json()["billing"]["data"]["balance"]["amount"]

    with patch(
        "app.services.billtrack.lookup_abonado_por_dni",
        return_value=None,
    ):
        r = client.get(
            "/api/v1/portal/customer-summary",
            headers=_headers(sess["portal_token"]),
            params={"include": "billing", "refresh": "billing"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["billing"]["status"] == "unavailable"
    assert body["billing"]["reason_code"] == "source_unavailable"
    assert body["billing"]["data"]["balance"]["amount"] == prev_amount
    assert body["billing"]["data"]["balance"]["amount"] != ""  # no wipe
    assert body["meta"]["refresh_applied"] == []


def test_customer_summary_billing_zero_string():
    sess = _portal_identified("30111222")
    hit = {
        "dni": "30111222",
        "nombre": "María González",
        "activo": True,
        "deuda": "0",
        "client_number": "200",
    }
    with patch(
        "app.services.billtrack.lookup_abonado_por_dni",
        return_value=hit,
    ):
        r = client.get(
            "/api/v1/portal/customer-summary",
            headers=_headers(sess["portal_token"]),
            params={"include": "billing", "refresh": "billing"},
        )
    assert r.status_code == 200
    assert r.json()["billing"]["data"]["balance"]["amount"] == "0"


# --- OV ---


def test_customer_summary_ov_links_ids():
    sess = _portal_identified()
    r = client.get(
        "/api/v1/portal/customer-summary",
        headers=_headers(sess["portal_token"]),
        params={"include": "ov"},
    )
    assert r.status_code == 200, r.text
    ov = r.json()["billing"]["data"]["ov"]
    ids = {x["id"] for x in ov["links"]}
    assert ids == {"pay", "invoice", "payment_slip"}
    assert "payment_notice" not in ids
    for link in ov["links"]:
        assert set(link.keys()) >= {"id", "label", "url", "available"}


# --- Tickets ---


def test_customer_summary_tickets_vacios():
    sess = _portal_identified("30111222")
    r = client.get(
        "/api/v1/portal/customer-summary",
        headers=_headers(sess["portal_token"]),
        params={"include": "tickets"},
    )
    assert r.status_code == 200
    # puede haber tickets de otros tests en la misma DB; solo chequear shape
    assert "items" in r.json()["tickets"]["data"]
    assert r.json()["tickets"]["status"] in ("ok", "empty")


def test_customer_summary_tickets_propios_no_eventos():
    sess = _portal_identified("30111222")
    token = sess["portal_token"]
    conv = sess["conversacion"]
    tid = f"TK-CS-{uuid.uuid4().hex[:10]}"

    db = get_session_factory()()
    try:
        c = db.get(ConversacionCanal, conv["id"])
        assert c is not None
        t = add_ticket(
            db,
            c.organizacion_id,
            id=tid,
            estado="Abierto",
            categoria="Internet",
            linea=(c.telefono or "2235550000"),
            descripcion_falla="summary test",
        )
        c.ticket_id = t.id
        db.commit()
    finally:
        db.close()

    r = client.get(
        "/api/v1/portal/customer-summary",
        headers=_headers(token),
        params={"include": "tickets"},
    )
    assert r.status_code == 200
    items = r.json()["tickets"]["data"]["items"]
    mine = next(i for i in items if i["id"] == tid)
    assert mine["estado"] == "Abierto"
    assert "eventos" not in mine
    assert "asignado_a" not in mine


def test_customer_summary_tickets_no_ajenos():
    sess_a = _portal_identified("30111222")
    sess_b = _portal_identified("26444555")
    tid = f"TK-CS-X-{uuid.uuid4().hex[:10]}"
    conv_a = sess_a["conversacion"]

    db = get_session_factory()()
    try:
        c = db.get(ConversacionCanal, conv_a["id"])
        assert c is not None
        t = add_ticket(
            db,
            c.organizacion_id,
            id=tid,
            estado="Abierto",
            categoria="Internet",
            linea=(c.telefono or "2235550000"),
        )
        c.ticket_id = t.id
        db.commit()
    finally:
        db.close()

    r = client.get(
        "/api/v1/portal/customer-summary",
        headers=_headers(sess_b["portal_token"]),
        params={"include": "tickets"},
    )
    assert r.status_code == 200
    ids = {i["id"] for i in r.json()["tickets"]["data"]["items"]}
    assert tid not in ids


# --- Compat endpoints existentes ---


def test_customer_summary_no_rompe_services_endpoint():
    sess = _portal_identified()
    r = client.get(
        "/api/v1/portal/services",
        headers=_headers(sess["portal_token"]),
    )
    assert r.status_code == 200
    assert "services" in r.json()


def test_customer_summary_no_rompe_ov_links_endpoint():
    sess = _portal_identified()
    r = client.get(
        "/api/v1/portal/ov-links",
        headers=_headers(sess["portal_token"]),
    )
    assert r.status_code == 200
    assert "links" in r.json()
