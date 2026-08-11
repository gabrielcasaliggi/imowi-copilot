"""Fail-fast config producción + endpoint /ready."""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app


def test_ready_ok_con_db():
    client = TestClient(app)
    r = client.get("/ready")
    assert r.status_code == 200
    data = r.json()
    assert data["ready"] is True
    assert data["database_connected"] is True
    assert data["database"] in ("sqlite", "postgresql")


def test_health_incluye_ready_link():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("ready") == "/ready"


def test_errores_config_vacios_en_development(monkeypatch):
    import app.config as cfg

    monkeypatch.setattr(cfg, "APP_ENV", "development")
    assert cfg.errores_config_produccion() == []
    assert cfg.avisos_config_produccion() == []


def test_errores_config_fatales_en_production(monkeypatch):
    import app.config as cfg

    monkeypatch.setattr(cfg, "APP_ENV", "production")
    monkeypatch.setenv("ALLOW_INSECURE_PROD", "")
    monkeypatch.setattr(cfg, "AUTH_SECRET", "corto")
    monkeypatch.setattr(cfg, "PORTAL_AUTH_SECRET", "corto")
    monkeypatch.setattr(cfg, "DATABASE_URL", "sqlite:///./data/x.db")
    monkeypatch.setattr(cfg, "CORS_ORIGINS", ["*"])
    monkeypatch.setattr(cfg, "MOCK_USERS", {"admin": {}})
    monkeypatch.setattr(cfg, "ENABLE_DEMO_RESET", True)
    monkeypatch.setattr(cfg, "DISABLE_DEMO_USERS", False)

    errs = cfg.errores_config_produccion()
    joined = " | ".join(errs)
    assert "AUTH_SECRET" in joined
    assert "PORTAL_AUTH_SECRET" in joined
    assert "PostgreSQL" in joined
    assert "CORS_ORIGINS" in joined
    assert "demo" in joined.lower() or "DEMO" in joined
    assert "ENABLE_DEMO_RESET" in joined


def test_errores_config_ok_production_segura(monkeypatch):
    import app.config as cfg

    monkeypatch.setattr(cfg, "APP_ENV", "production")
    monkeypatch.setenv("ALLOW_INSECURE_PROD", "")
    monkeypatch.setattr(cfg, "AUTH_SECRET", "a" * 32)
    monkeypatch.setattr(cfg, "PORTAL_AUTH_SECRET", "b" * 32)
    monkeypatch.setattr(
        cfg, "DATABASE_URL", "postgresql+psycopg://u:p@localhost/db"
    )
    monkeypatch.setattr(cfg, "CORS_ORIGINS", ["https://ibot.ecolan.com"])
    monkeypatch.setattr(cfg, "MOCK_USERS", {})
    monkeypatch.setattr(cfg, "DISABLE_DEMO_USERS", True)
    monkeypatch.setattr(cfg, "ENABLE_DEMO_RESET", False)
    monkeypatch.setattr(cfg, "demo_users_disabled", lambda: True)

    assert cfg.errores_config_produccion() == []


def test_allow_insecure_prod_salta_fatales(monkeypatch):
    import app.config as cfg

    monkeypatch.setattr(cfg, "APP_ENV", "production")
    monkeypatch.setenv("ALLOW_INSECURE_PROD", "true")
    monkeypatch.setattr(cfg, "AUTH_SECRET", "")
    assert cfg.errores_config_produccion() == []
    avisos = cfg.avisos_config_produccion()
    assert any("ALLOW_INSECURE_PROD" in a for a in avisos)
