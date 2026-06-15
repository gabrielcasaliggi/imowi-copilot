"""Tests API de inteligencia en tickets."""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": "admin", "password": "admin"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_tickets_incluyen_intelligence():
    headers = _admin_headers()
    r = client.get("/api/v1/tickets", headers=headers)
    assert r.status_code == 200
    tickets = r.json()["tickets"]
    if tickets:
        assert "intelligence" in tickets[0]
        assert "priority_score" in tickets[0]["intelligence"]
        assert "next_best_action" in tickets[0]["intelligence"]


def test_prioritized_queue_admin():
    headers = _admin_headers()
    r = client.get("/api/v1/tickets/prioritized", headers=headers)
    assert r.status_code == 200
    assert "cola" in r.json()


def test_executive_analytics_endpoint():
    headers = _admin_headers()
    r = client.get("/api/v1/analytics/executive", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "resumen_ejecutivo" in data
    assert "ranking_riesgo" in data
