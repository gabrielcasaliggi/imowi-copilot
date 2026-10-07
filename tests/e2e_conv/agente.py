"""Acciones de un agente humano en el panel, para usar como elemento de ``converse(script=[...])``.

Llaman a los endpoints reales (con sus hooks: cierre del hilo y calificación CSAT), no escriben en la base."""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

_client = TestClient(app)


def _headers() -> dict[str, str]:
    r = _client.post("/api/login", json={"usuario": "admin", "password": "admin"})  # credenciales de demo (README)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}", "X-Tenant-Slug": "coop-batan"}


def cierra_el_ticket_desde_el_panel(h) -> None:
    """tickets.py: ``PUT /tickets/{id}`` con estado Cerrado (cierra el hilo y pide la calificación)."""
    assert h.ticket_id, "la conversación vigente no tiene ticket"
    r = _client.put(f"/api/v1/tickets/{h.ticket_id}", headers=_headers(), json={"estado": "Cerrado", "resolucion_tecnica": "Resuelto por el agente"})
    assert r.status_code == 200, r.text


def cierra_la_conversacion_desde_la_bandeja(h) -> None:
    """inbox.py: ``POST /inbox/conversations/{id}/close`` (cierra el hilo y pide la calificación)."""
    r = _client.post(f"/api/v1/inbox/conversations/{h.conv_id}/close", headers=_headers(), json={"nota": "Resuelto por el agente"})
    assert r.status_code == 200, r.text
