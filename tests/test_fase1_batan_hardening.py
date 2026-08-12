"""Fase 1 Batán — demo/reset bloqueado y health flags."""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": "admin", "password": "admin"})
    assert r.status_code == 200
    return {
        "Authorization": f"Bearer {r.json()['token']}",
        "X-Tenant-Slug": "coop-batan",
    }


def test_health_incluye_flags_fase1():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert "demo_reset_enabled" in data
    assert "sentry_configured" in data
    assert "sentry_risk_accepted" in data
    assert isinstance(data["demo_reset_enabled"], bool)
    assert isinstance(data["sentry_risk_accepted"], bool)


def test_demo_reset_bloqueado_cuando_flag_off(monkeypatch):
    monkeypatch.setattr("app.api.v1.demo.ENABLE_DEMO_RESET", False)
    r = client.post(
        "/api/v1/demo/reset",
        headers=_admin_headers(),
        json={"incluir_tickets": False},
    )
    assert r.status_code == 403
    assert "deshabilitado" in r.json()["detail"].lower() or "ENABLE_DEMO_RESET" in r.json()["detail"]


def test_demo_reset_exige_rol_elevado(monkeypatch):
    monkeypatch.setattr("app.api.v1.demo.ENABLE_DEMO_RESET", True)
    monkeypatch.setattr("app.api.v1.demo.es_produccion", lambda: False)
    # Agente (batan) no debería poder
    login = client.post("/api/login", json={"usuario": "batan", "password": "batan"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['token']}"}
    r = client.post(
        "/api/v1/demo/reset",
        headers=headers,
        json={"incluir_tickets": False},
    )
    assert r.status_code == 403


def test_demo_reset_admin_ok_fuera_de_prod(monkeypatch):
    monkeypatch.setattr("app.api.v1.demo.ENABLE_DEMO_RESET", True)
    monkeypatch.setattr("app.api.v1.demo.es_produccion", lambda: False)
    r = client.post(
        "/api/v1/demo/reset",
        headers=_admin_headers(),
        json={"incluir_tickets": False},
    )
    assert r.status_code == 200
    assert r.json().get("status") == "ok"
