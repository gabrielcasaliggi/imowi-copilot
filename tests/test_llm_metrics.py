"""Tests métricas LLM (live + persistencia)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.estate.database import get_session_factory
from app.estate.models import LlmCall
from app.llm_metrics import (
    history_llm_metrics,
    record_llm_call,
    reset_llm_metrics_for_tests,
    snapshot_llm_metrics,
)
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


def test_record_llm_call_persists():
    reset_llm_metrics_for_tests()
    record_llm_call(
        ok=True,
        latency_ms=40,
        model="persist-model",
        total_tokens=22,
        actor="test",
    )
    Session = get_session_factory()
    with Session() as db:
        row = db.scalar(
            select(LlmCall)
            .where(LlmCall.model == "persist-model")
            .order_by(LlmCall.created_at.desc())
        )
        assert row is not None
        assert row.ok == 1
        assert row.total_tokens == 22
        assert row.actor == "test"

    hist = history_llm_metrics(recent=50)
    assert hist["calls_total"] >= 1
    assert "persist-model" in hist["by_model"]


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
    assert "live" in body
    assert "history" in body
    assert "calls_total" in body["history"]
