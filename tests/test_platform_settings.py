"""Tests de configuración de plataforma (admin)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.estate.database import get_session_factory
from app.services.platform_settings import get_merged_settings, resolve_ai, save_settings
from main import app

client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": "admin", "password": "admin"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _batan_headers() -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": "batan", "password": "batan"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_settings_requiere_admin():
    r = client.get("/api/v1/admin/settings", headers=_batan_headers())
    assert r.status_code == 403


def test_get_settings_admin():
    r = client.get("/api/v1/admin/settings", headers=_admin_headers())
    assert r.status_code == 200
    body = r.json()
    assert "settings" in body
    assert "ai" in body["settings"]
    assert "whatsapp" in body["settings"]
    assert "playbooks" in body["settings"]
    assert "database" in body["settings"]
    assert "knowledge" in body["settings"]


def test_put_settings_ai_y_playbook():
    h = _admin_headers()
    r = client.put(
        "/api/v1/admin/settings",
        headers=h,
        json={
            "settings": {
                "ai": {"model": "llama-test-cfg", "base_url": "http://127.0.0.1:11434/v1"},
                "playbooks": {
                    "internet": [
                        {"id": "paso_custom", "pregunta": "¿Probaste reiniciar el módem custom?"}
                    ]
                },
            }
        },
    )
    assert r.status_code == 200
    assert r.json()["settings"]["ai"]["model"] == "llama-test-cfg"
    assert r.json()["settings"]["playbooks"]["internet"][0]["id"] == "paso_custom"

    Session = get_session_factory()
    with Session() as db:
        ai = resolve_ai(db)
        assert ai["model"] == "llama-test-cfg"
        merged = get_merged_settings(db)
        assert merged["playbooks"]["internet"][0]["pregunta"].startswith("¿Probaste")


def test_secret_enmascarado_no_pisa():
    h = _admin_headers()
    Session = get_session_factory()
    with Session() as db:
        save_settings(db, {"ai": {"api_key": "secret-real-key-xyz"}}, actor="test")

    r = client.put(
        "/api/v1/admin/settings",
        headers=h,
        json={"settings": {"ai": {"api_key": "sec***xyz"}}},
    )
    assert r.status_code == 200
    with Session() as db:
        assert resolve_ai(db)["api_key"] == "secret-real-key-xyz"


def test_test_whatsapp_endpoint():
    r = client.post("/api/v1/admin/settings/test-whatsapp", headers=_admin_headers())
    assert r.status_code == 200
    assert "ok" in r.json()


def test_test_database_endpoint_sqlite_activa():
    r = client.post(
        "/api/v1/admin/settings/test-database",
        headers=_admin_headers(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["connected"] is True
    assert body["scope"] == "data_estate"
    assert body["dialect"] in ("sqlite", "postgresql")
    assert "url_masked" in body


def test_test_billtrack_sin_url():
    r = client.post(
        "/api/v1/admin/settings/test-billtrack",
        headers=_admin_headers(),
        json={},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["scope"] == "billtrack"
    assert "sin URL" in (body.get("error") or "").lower() or "URL" in (body.get("error") or "")


def test_put_billtrack_settings():
    h = _admin_headers()
    r = client.put(
        "/api/v1/admin/settings",
        headers=h,
        json={
            "settings": {
                "billtrack": {
                    "enabled": True,
                    "url": "postgresql://billtrack_reader:secret@127.0.0.1:5432/demo",
                    "sslmode": "prefer",
                }
            }
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["billtrack_configured"] is True
    assert body["billtrack_enabled"] is True
    assert "***" in body["billtrack_url_masked"]
    assert "secret" not in body["billtrack_url_masked"]
    assert body["settings"]["billtrack"]["enabled"] is True


def test_probar_conexion_database_helper():
    from app.estate.health import probar_conexion_database

    info = probar_conexion_database()
    assert info["ok"] is True
    assert info["connected"] is True
    assert info["latency_ms"] is not None
    assert info["latency_ms"] >= 0