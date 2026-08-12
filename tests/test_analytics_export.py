"""Export CSV de analytics (reports.export)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _headers(user: str, password: str) -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": user, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_export_executive_requiere_reports_export():
    # Agente Batán: sin reports.export → 403
    h = _headers("batan", "batan")
    r = client.get("/api/v1/analytics/export?kind=executive", headers=h)
    assert r.status_code == 403

    # Ejecutivo / supervisor / admin tienen reports.export
    h2 = _headers("ejecutivo", "ejecutivo")
    r2 = client.get("/api/v1/analytics/export?kind=executive", headers=h2)
    assert r2.status_code == 200
    assert "text/csv" in r2.headers.get("content-type", "")
    body = r2.text
    assert "metric" in body
    assert "executive" in body or "resumen" in body or "tenant" in body


def test_export_ops_csv():
    h = _headers("supervisor", "supervisor")
    r = client.get("/api/v1/analytics/export?kind=ops", headers=h)
    assert r.status_code == 200
    assert "attachment" in (r.headers.get("content-disposition") or "")
