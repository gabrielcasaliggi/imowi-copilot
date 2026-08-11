"""Cierre masivo de tickets abiertos (limpieza operativa)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.estate import repository as repo
from main import app
from tests.conftest import add_ticket

client = TestClient(app)


def test_cerrar_tickets_abiertos_repo(db):
    session, org_id = db
    add_ticket(session, org_id, id="TK-OPEN-1", estado="Abierto")
    add_ticket(session, org_id, id="TK-OPEN-2", estado="En progreso")
    add_ticket(session, org_id, id="TK-DONE-1", estado="Cerrado")

    preview = repo.cerrar_tickets_abiertos(
        session,
        org_id,
        resolucion_tecnica="preview",
        dry_run=True,
    )
    assert preview["dry_run"] is True
    assert preview["tickets_abiertos"] == 2
    assert preview["tickets_cerrados"] == 0

    out = repo.cerrar_tickets_abiertos(
        session,
        org_id,
        resolucion_tecnica="Limpieza operativa test",
        actor="test",
        dry_run=False,
    )
    assert out["tickets_cerrados"] == 2
    abiertos = repo.list_tickets_abiertos(session, org_id)
    assert abiertos == []
    done = repo.get_ticket(session, org_id, "TK-OPEN-1")
    assert done is not None
    assert done.estado == "Cerrado"
    assert "Limpieza" in done.resolucion_tecnica


def test_bulk_close_api_dry_run_y_requiere_confirmacion():
    r = client.post("/api/login", json={"usuario": "admin", "password": "admin"})
    assert r.status_code == 200
    headers = {
        "Authorization": f"Bearer {r.json()['token']}",
        "X-Tenant-Slug": "coop-batan",
    }

    preview = client.post(
        "/api/v1/tickets/bulk-close",
        headers=headers,
        json={"dry_run": True},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["dry_run"] is True
    assert "tickets_abiertos" in body

    bad = client.post(
        "/api/v1/tickets/bulk-close",
        headers=headers,
        json={"dry_run": False, "confirmar": False},
    )
    assert bad.status_code == 400


def test_bulk_close_bloquea_vista_global_imowi():
    r = client.post("/api/login", json={"usuario": "admin", "password": "admin"})
    assert r.status_code == 200
    headers = {
        "Authorization": f"Bearer {r.json()['token']}",
        "X-Tenant-Slug": "imowi",
    }
    resp = client.post(
        "/api/v1/tickets/bulk-close",
        headers=headers,
        json={"dry_run": True},
    )
    assert resp.status_code == 400
    assert "cooperativa" in resp.json()["detail"].lower()
