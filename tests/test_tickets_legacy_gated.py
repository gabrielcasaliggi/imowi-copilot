"""tickets_store queda detrás de ENABLE_LEGACY_API; /api/v1 usa el estate."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from main import app, cargar_persistencia_tickets_legacy


def test_api_v1_no_importa_tickets_store():
    root = Path(__file__).resolve().parents[1] / "app" / "api" / "v1"
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "tickets_store" in text:
            hits.append(str(path.relative_to(root.parent.parent)))
    assert hits == []


def test_frontend_usa_v1_no_api_tickets_json():
    client = Path(__file__).resolve().parents[1] / "frontend" / "src" / "lib" / "api-client.ts"
    text = client.read_text(encoding="utf-8")
    assert "/api/v1/tickets" in text
    assert '"/api/tickets"' not in text
    assert "`/api/tickets" not in text


def test_no_carga_json_si_legacy_off(monkeypatch):
    import main as m

    monkeypatch.setattr(m, "ENABLE_LEGACY_API", False)

    def boom() -> int:
        raise AssertionError("tickets_store no debe cargarse con legacy off")

    monkeypatch.setattr(m.tickets_store, "cargar_tickets_desde_disco", boom)
    assert cargar_persistencia_tickets_legacy() == 0


def test_carga_json_si_legacy_on(monkeypatch):
    import main as m

    monkeypatch.setattr(m, "ENABLE_LEGACY_API", True)
    monkeypatch.setattr(m.tickets_store, "cargar_tickets_desde_disco", lambda: 7)
    assert cargar_persistencia_tickets_legacy() == 7


def test_v1_tickets_sigue_en_el_arbol():
    client = TestClient(app)
    r = client.get("/api/v1/tickets")
    assert r.status_code in (401, 403)
