"""Health endpoint y verificación de base de datos."""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app


def test_health_sqlite_local():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("ok", "degraded")
    assert data["estate"] is True
    assert data["database"] in ("sqlite", "postgresql")
    assert data["database_connected"] is True
    assert data["api_v1"] == "/api/v1"
    assert data["frontend_recomendado"] == "Next.js"


def test_verificar_database_module():
    from app.estate.health import verificar_database

    info = verificar_database()
    assert info["connected"] is True
    assert info["dialect"] in ("sqlite", "postgresql")
