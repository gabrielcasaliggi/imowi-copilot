"""Tests métricas LLM (Fase C)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.llm_metrics import record_llm_call, reset_llm_metrics_for_tests, snapshot_llm_metrics
from main import app

client = TestClient(app)


def test_snapshot_llm_metrics_counts():
    reset_llm_metrics_for_tests()
    record_llm_call(ok=True, latency_ms=12.5, model="test-model", total_tokens=10)
    record_llm_call(ok=False, latency_ms=3.0, model="test-model", error="boom")
    snap = snapshot_llm_metrics(recent=5)
    assert snap["calls_ok"] == 1
    assert snap["calls_error"] == 1
    assert snap["calls_total"] == 2
    assert snap["avg_latency_ms_ok"] == 12.5
    assert snap["by_model"]["test-model"] == 2
    assert len(snap["recent"]) == 2


def test_metrics_llm_endpoint_requires_auth():
    reset_llm_metrics_for_tests()
    assert client.get("/api/v1/metrics/llm").status_code == 401
    login = client.post("/api/login", json={"usuario": "admin", "password": "admin"})
    assert login.status_code == 200
    token = login.json()["token"]
    r = client.get("/api/v1/metrics/llm", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "calls_total" in body
