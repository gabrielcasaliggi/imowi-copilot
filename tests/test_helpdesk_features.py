"""Tests de features helpdesk adaptadas a NOC telco."""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": "admin", "password": "admin"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _coop_headers() -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": "batan", "password": "batan"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_response_templates():
    headers = _admin_headers()
    r = client.get("/api/v1/response-templates", headers=headers)
    assert r.status_code == 200
    plantillas = r.json()["plantillas"]
    assert len(plantillas) >= 5
    assert any(p["id"] == "escalamiento_carrier_sms" for p in plantillas)


def test_tickets_filtro_solo_abiertos():
    headers = _admin_headers()
    r = client.get("/api/v1/tickets?solo_abiertos=true", headers=headers)
    assert r.status_code == 200
    tickets = r.json()["tickets"]
    assert all(t["estado"] != "Cerrado" for t in tickets)


def test_ticket_nota_interna_y_timeline():
    headers = _admin_headers()
    listed = client.get("/api/v1/tickets?solo_abiertos=true", headers=headers)
    tickets = listed.json()["tickets"]
    if not tickets:
        return
    tid = tickets[0]["id"]
    r = client.post(
        f"/api/v1/tickets/{tid}/events",
        headers=headers,
        json={"detalle": "Verificación JSC OK, pendiente carrier.", "interno": True},
    )
    assert r.status_code == 200
    ev = r.json()["evento"]
    assert ev["visible_cliente"] == "No"
    detail = client.get(f"/api/v1/tickets/{tid}", headers=headers)
    assert detail.status_code == 200
    tipos = [e["titulo"] for e in detail.json()["timeline"]]
    assert "Nota interna" in tipos


def test_kb_draft_desde_ticket():
    headers = _admin_headers()
    listed = client.get("/api/v1/tickets", headers=headers)
    tickets = listed.json()["tickets"]
    if not tickets:
        return
    tid = tickets[0]["id"]
    r = client.get(f"/api/v1/tickets/{tid}/kb-draft", headers=headers)
    assert r.status_code == 200
    borrador = r.json()["borrador"]
    assert borrador["titulo"]
    assert borrador["contenido"]
    assert tid in borrador["contenido"] or borrador.get("ticket_id") == tid


def test_stats_backlog_incluye_estado_sla():
    headers = _admin_headers()
    r = client.get("/api/v1/analytics/tickets", headers=headers)
    assert r.status_code == 200
    backlog = r.json().get("backlog") or []
    for item in backlog:
        assert "estado_sla" in item


def test_coop_puede_agregar_nota():
    headers = _coop_headers()
    listed = client.get("/api/v1/tickets", headers=headers)
    if listed.status_code != 200:
        return
    tickets = listed.json().get("tickets") or []
    if not tickets:
        return
    tid = tickets[0]["id"]
    r = client.post(
        f"/api/v1/tickets/{tid}/events",
        headers=headers,
        json={"detalle": "Cliente confirma persistencia.", "interno": False},
    )
    assert r.status_code == 200
    assert r.json()["evento"]["visible_cliente"] == "Sí"
