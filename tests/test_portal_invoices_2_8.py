"""EKO 2.8 — GET /portal/invoices. Sin BillTrack real."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.services.eko_invoice_reader import InvoiceHeader, InvoiceReadResult
from main import app

client = TestClient(app)

_FORBIDDEN = {
    "due_date",
    "period",
    "currency",
    "pdf",
    "line_items",
    "lines",
    "client_number",
    "account_number",
    "invoice_id",
    "id",
    "abonado_id",
    "dni",
}

_PUBLIC = {"invoice_number", "full_type", "amount", "issued_at", "status"}


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


def _header(**kwargs) -> InvoiceHeader:
    defaults = {
        "invoice_id": 99,
        "invoice_number": "0001-00001234",
        "full_type": "FC A",
        "type": "FC",
        "client_number": "200",
        "account_number": "200",
        "amount": "12345.67",
        "issued_at": datetime(2026, 9, 1, tzinfo=UTC),
        "status": "Pendiente",
    }
    defaults.update(kwargs)
    return InvoiceHeader(**defaults)


def _ok(*invoices: InvoiceHeader) -> InvoiceReadResult:
    return InvoiceReadResult(status="ok", invoices=list(invoices), reason_code=None)


def test_invoices_requiere_jwt():
    client.cookies.clear()
    r = client.get("/api/v1/portal/invoices", headers={"X-Canal": "app"})
    assert r.status_code == 401


def test_invoices_jwt_devuelve_cabeceras():
    sess = _portal_identified("30111222")
    inv = _header()
    with patch(
        "app.services.portal_invoices.read_invoices_fc",
        return_value=_ok(inv),
    ) as reader:
        r = client.get(
            "/api/v1/portal/invoices",
            headers=_headers(sess["portal_token"]),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["reason_code"] is None
    assert body["invoices"][0]["invoice_number"] == "0001-00001234"
    assert body["invoices"][0]["amount"] == "12345.67"
    assert reader.call_args.kwargs["client_number"] == "200"
    assert "billtrack" not in reader.call_args.kwargs


def test_invoices_limit_omitido_es_5():
    sess = _portal_identified()
    with patch(
        "app.services.portal_invoices.read_invoices_fc",
        return_value=_ok(_header()),
    ) as reader:
        r = client.get(
            "/api/v1/portal/invoices",
            headers=_headers(sess["portal_token"]),
        )
    assert r.status_code == 200
    assert reader.call_args.kwargs["limit"] == 5


def test_invoices_limit_valido():
    sess = _portal_identified()
    with patch(
        "app.services.portal_invoices.read_invoices_fc",
        return_value=_ok(_header()),
    ) as reader:
        r = client.get(
            "/api/v1/portal/invoices",
            headers=_headers(sess["portal_token"]),
            params={"limit": "3"},
        )
    assert r.status_code == 200
    assert reader.call_args.kwargs["limit"] == 3


def test_invoices_limit_sobre_20_queda_en_20():
    sess = _portal_identified()
    with patch(
        "app.services.portal_invoices.read_invoices_fc",
        return_value=_ok(_header()),
    ) as reader:
        r = client.get(
            "/api/v1/portal/invoices",
            headers=_headers(sess["portal_token"]),
            params={"limit": "50"},
        )
    assert r.status_code == 200
    assert reader.call_args.kwargs["limit"] == 20


def test_invoices_limit_invalido_cae_al_default():
    sess = _portal_identified()
    with patch(
        "app.services.portal_invoices.read_invoices_fc",
        return_value=_ok(_header()),
    ) as reader:
        r = client.get(
            "/api/v1/portal/invoices",
            headers=_headers(sess["portal_token"]),
            params={"limit": "abc"},
        )
    assert r.status_code == 200
    assert reader.call_args.kwargs["limit"] == 5


@pytest.mark.parametrize(
    "param",
    ["client_number", "dni", "account_number", "abonado_id"],
)
def test_invoices_rechaza_selector_de_identidad(param: str):
    sess = _portal_identified()
    with (
        patch("app.services.portal_invoices.read_invoices_fc") as reader,
        patch("app.services.billtrack._billtrack_engine") as engine,
        patch("app.services.portal_customer_summary.evaluar_customer_summary") as summary,
    ):
        r = client.get(
            "/api/v1/portal/invoices",
            headers=_headers(sess["portal_token"]),
            params={param: "otro"},
        )
    assert r.status_code == 400, r.text
    reader.assert_not_called()
    engine.assert_not_called()
    summary.assert_not_called()


def test_invoices_sin_client_number_no_lee_billtrack():
    sess = _portal_identified()
    with (
        patch(
            "app.api.v1.portal._abonado_portal_identificado",
            return_value=SimpleNamespace(client_number=""),
        ),
        patch("app.services.portal_invoices.read_invoices_fc") as reader,
        patch("app.services.billtrack._billtrack_engine") as engine,
    ):
        r = client.get(
            "/api/v1/portal/invoices",
            headers=_headers(sess["portal_token"]),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "unavailable"
    assert body["reason_code"] == "missing_client_number"
    assert body["invoices"] == []
    reader.assert_not_called()
    engine.assert_not_called()


def test_invoices_billtrack_vacio():
    sess = _portal_identified()
    empty = InvoiceReadResult(
        status="empty",
        reason_code="no_fc_invoices",
        message="No encuentro facturas (FC) para tu cuenta en este momento.",
    )
    with patch(
        "app.services.portal_invoices.read_invoices_fc",
        return_value=empty,
    ):
        r = client.get(
            "/api/v1/portal/invoices",
            headers=_headers(sess["portal_token"]),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "empty"
    assert body["reason_code"] == "no_fc_invoices"
    assert body["invoices"] == []


@pytest.mark.parametrize(
    ("read_status", "reason"),
    [
        ("unavailable", "billtrack_unavailable"),
        ("error", "billtrack_query_failed"),
    ],
)
def test_invoices_billtrack_fallo_no_es_success(read_status: str, reason: str):
    sess = _portal_identified()
    failed = InvoiceReadResult(status=read_status, reason_code=reason, message="fallo")
    with patch(
        "app.services.portal_invoices.read_invoices_fc",
        return_value=failed,
    ):
        r = client.get(
            "/api/v1/portal/invoices",
            headers=_headers(sess["portal_token"]),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == read_status
    assert body["reason_code"] == reason
    assert body["invoices"] == []
    assert body["status"] != "ok"


def test_invoices_contrato_sin_campos_prohibidos():
    sess = _portal_identified()
    with patch(
        "app.services.portal_invoices.read_invoices_fc",
        return_value=_ok(_header()),
    ):
        r = client.get(
            "/api/v1/portal/invoices",
            headers=_headers(sess["portal_token"]),
        )
    body = r.json()
    assert set(body) == {"status", "reason_code", "invoices"}
    row = body["invoices"][0]
    assert set(row) == _PUBLIC
    assert _FORBIDDEN.isdisjoint(row)
    assert "99" not in r.text
    assert "due_date" not in r.text
    assert "account_number" not in r.text
    assert "client_number" not in r.text


def test_invoices_ownership_usa_cuenta_del_jwt_no_del_query():
    """El query no elige la cuenta. El reader recibe el client_number del abonado del JWT."""
    sess = _portal_identified("30111222")
    with patch("app.services.portal_invoices.read_invoices_fc") as reader:
        denied = client.get(
            "/api/v1/portal/invoices",
            headers=_headers(sess["portal_token"]),
            params={"client_number": "201"},
        )
    assert denied.status_code == 400
    reader.assert_not_called()

    with (
        patch(
            "app.api.v1.portal._abonado_portal_identificado",
            return_value=SimpleNamespace(client_number="201"),
        ),
        patch(
            "app.services.portal_invoices.read_invoices_fc",
            return_value=_ok(_header(client_number="201", account_number="201")),
        ) as reader,
    ):
        ok = client.get(
            "/api/v1/portal/invoices",
            headers=_headers(sess["portal_token"]),
        )
    assert ok.status_code == 200, ok.text
    assert reader.call_args.kwargs["client_number"] == "201"
    assert reader.call_args.kwargs["client_number"] != "200"
    assert "client_number" not in ok.json()["invoices"][0]
