"""Flujo de propuestas KB con revisión admin."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.estate import repository as repo
from app.estate.learning_loop import (
    cierre_positivo,
    crear_propuesta_kb_desde_ticket,
    procesar_cierre_ticket,
)
from main import app
from tests.conftest import add_ticket

client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": "admin", "password": "admin"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _coop_headers() -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": "batan", "password": "batan"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_cierre_positivo_requiere_resolucion(db):
    session, org_id = db
    t = add_ticket(session, org_id, estado="Cerrado", id="TK-KB-001")
    assert cierre_positivo(t) is False
    t.resolucion_tecnica = "Se reinició APN y recuperó datos."
    session.commit()
    session.refresh(t)
    assert cierre_positivo(t) is True


def test_procesar_cierre_crea_propuesta_pendiente(db):
    session, org_id = db
    t = add_ticket(
        session,
        org_id,
        id="TK-KB-002",
        estado="Cerrado",
        categoria="Datos",
    )
    t.resolucion_tecnica = "APN corregido; cliente confirma OK."
    t.nivel = "N1"
    session.commit()
    session.refresh(t)

    result = procesar_cierre_ticket(session, org_id, t, org_name="Coop Test")
    assert result["contribucion_kb"] is not None
    assert result["contribucion_kb"]["estado"] == "pendiente"

    pendientes = repo.list_kb_contributions(session, org_id, estado="pendiente")
    assert len(pendientes) == 1
    assert pendientes[0].ticket_id == "TK-KB-002"
    assert repo.list_kb(session, org_id) == []

    # No duplica si ya hay pendiente
    result2 = procesar_cierre_ticket(session, org_id, t, org_name="Coop Test")
    assert result2["contribucion_kb"]["id"] == result["contribucion_kb"]["id"]
    assert len(repo.list_kb_contributions(session, org_id, estado="pendiente")) == 1


def test_aprobar_y_rechazar_contribucion(db):
    session, org_id = db
    t = add_ticket(session, org_id, id="TK-KB-003", estado="Cerrado")
    t.resolucion_tecnica = "Roaming habilitado en JSC."
    t.nivel = "N2"
    session.commit()
    session.refresh(t)

    contrib = crear_propuesta_kb_desde_ticket(
        session,
        org_id,
        t,
        org_name="Coop Test",
        propuesto_por="agente@ops-hub.demo",
        origen="agente",
    )
    assert contrib is not None
    assert contrib.estado == "pendiente"

    approved, art = repo.approve_kb_contribution(
        session,
        contrib,
        revisado_por="admin@ops-hub.demo",
        motivo_revision="Útil para N1",
    )
    assert approved.estado == "aprobada"
    assert approved.articulo_id == art.id
    assert art.titulo == contrib.titulo
    assert len(repo.list_kb(session, org_id)) == 1

    t2 = add_ticket(session, org_id, id="TK-KB-004", estado="Cerrado")
    t2.resolucion_tecnica = "Caso atípico no generalizable."
    session.commit()
    session.refresh(t2)
    c2 = crear_propuesta_kb_desde_ticket(session, org_id, t2, propuesto_por="noc")
    rejected = repo.reject_kb_contribution(
        session,
        c2,
        revisado_por="admin@ops-hub.demo",
        motivo_revision="Demasiado específico",
    )
    assert rejected.estado == "rechazada"
    assert len(repo.list_kb(session, org_id)) == 1


def test_api_bandeja_aprobar_contribucion():
    headers = _admin_headers()
    listed = client.get("/api/v1/tickets?solo_abiertos=true", headers=headers)
    assert listed.status_code == 200
    tickets = listed.json()["tickets"]
    if not tickets:
        return
    tid = tickets[0]["id"]

    # Cierre positivo → propuesta automática
    upd = client.put(
        f"/api/v1/tickets/{tid}",
        headers=headers,
        json={
            "estado": "Cerrado",
            "resolucion_tecnica": "Procedimiento N1 validado: reinicio de radio y OK cliente.",
        },
    )
    assert upd.status_code == 200

    bandeja = client.get("/api/v1/kb/contributions?estado=pendiente", headers=headers)
    assert bandeja.status_code == 200
    contribs = bandeja.json()["contribuciones"]
    match = [c for c in contribs if c.get("ticket_id") == tid]
    assert match, "Se esperaba propuesta KB pendiente tras cierre positivo"
    cid = match[0]["id"]

    # Cooperativa puede listar pero no aprobar
    coop = _coop_headers()
    ban_coop = client.get("/api/v1/kb/contributions?estado=pendiente", headers=coop)
    assert ban_coop.status_code == 200
    deny = client.post(f"/api/v1/kb/contributions/{cid}/approve", headers=coop, json={})
    assert deny.status_code == 403

    approve = client.post(
        f"/api/v1/kb/contributions/{cid}/approve",
        headers=headers,
        json={"motivo_revision": "Aprobado para automatización N1"},
    )
    assert approve.status_code == 200
    body = approve.json()
    assert body["contribucion"]["estado"] == "aprobada"
    assert body["articulo"]["id"]
    assert body["contribucion"]["articulo_id"] == body["articulo"]["id"]

    detail = client.get(f"/api/v1/kb/contributions/{cid}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["contribucion"]["estado"] == "aprobada"


def test_api_publish_kb_crea_propuesta_no_articulo():
    headers = _admin_headers()
    listed = client.get("/api/v1/tickets", headers=headers)
    tickets = listed.json()["tickets"]
    if not tickets:
        return
    tid = tickets[0]["id"]
    before = client.get("/api/v1/kb", headers=headers).json()["articulos"]
    r = client.post(
        f"/api/v1/tickets/{tid}/publish-kb",
        headers=headers,
        json={
            "titulo": "Propuesta manual test",
            "categoria": "General",
            "contenido": "Pasos reproducibles para N1.",
        },
    )
    assert r.status_code == 200
    assert r.json().get("pendiente_revision") is True
    assert r.json()["contribucion"]["estado"] == "pendiente"
    after = client.get("/api/v1/kb", headers=headers).json()["articulos"]
    assert len(after) == len(before)
