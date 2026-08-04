"""Cierre de ticket → cierra canal; reingreso abre conversación nueva."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.estate.database import get_session_factory
from app.estate.models import Ticket
from app.estate import canal_repo as crepo
from app.estate import repository as repo
from main import app
from tests.conftest import add_ticket

client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": "admin", "password": "admin"})
    assert r.status_code == 200
    return {
        "Authorization": f"Bearer {r.json()['token']}",
        "X-Tenant-Slug": "coop-batan",
    }


def _portal_identified(dni: str = "30111222") -> dict:
    start = client.post(
        "/api/v1/portal/auth/start",
        json={"dni": dni, "org_slug": "coop-batan"},
    )
    assert start.status_code == 200, start.text
    otp = start.json()["debug_otp"]
    verify = client.post(
        "/api/v1/portal/auth/verify",
        json={
            "challenge_id": start.json()["challenge_id"],
            "otp": otp,
            "org_slug": "coop-batan",
        },
    )
    assert verify.status_code == 200, verify.text
    return verify.json()


def test_cerrar_ticket_cierra_conversacion_y_reingreso_es_nuevo():
    sess = _portal_identified("30111222")
    token = sess["portal_token"]
    conv_id = sess["conversacion"]["id"]

    # Derivar a agente → crea ticket N2
    msg = client.post(
        "/api/v1/portal/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"texto": "*agente*"},
    )
    assert msg.status_code == 200, msg.text
    ticket_id = msg.json().get("ticket_id") or ""
    assert ticket_id, msg.json()

    # Cerrar ticket (como admin)
    h = _admin_headers()
    up = client.put(
        f"/api/v1/tickets/{ticket_id}",
        headers=h,
        json={"estado": "Cerrado", "resolucion_tecnica": "Resuelto en test"},
    )
    assert up.status_code == 200, up.text

    Session = get_session_factory()
    with Session() as db:
        conv = crepo.get_conversacion(db, repo.get_org_by_slug(db, "coop-batan").id, conv_id)
        assert conv is not None
        assert conv.estado == "cerrado"
        t = db.get(Ticket, ticket_id)
        assert t is not None
        assert t.estado == "Cerrado"

    # Reingreso con mismo DNI → conversación distinta (bot)
    sess2 = _portal_identified("30111222")
    assert sess2["conversacion"]["id"] != conv_id
    assert sess2["conversacion"]["estado"] == "bot"
    assert not (sess2["conversacion"].get("ticket_id") or "")


def test_get_or_create_ignora_hilo_con_ticket_cerrado():
    Session = get_session_factory()
    with Session() as db:
        org = repo.get_org_by_slug(db, "coop-batan")
        assert org
        tel = "5492235999888"
        # Limpia
        for c in crepo.list_conversaciones(db, org.id, limit=200):
            if c.telefono.endswith("998888") or c.telefono == tel:
                c.estado = "cerrado"
        db.commit()

        t = add_ticket(
            db,
            org.id,
            id="TK-CANAL-CLOSE-1",
            linea=tel,
            descripcion_falla="test cierre canal",
            estado="Abierto",
            nivel="N2",
        )
        conv = crepo.get_or_create_conversacion(db, org.id, telefono=tel, canal="web", wa_id=tel)
        conv.ticket_id = t.id
        conv.estado = "con_agente"
        db.commit()
        old_id = conv.id

        t.estado = "Cerrado"
        db.commit()

        conv2 = crepo.get_or_create_conversacion(db, org.id, telefono=tel, canal="web", wa_id=tel)
        assert conv2.id != old_id
        assert conv2.estado == "bot"
        assert not (conv2.ticket_id or "")

        stale = crepo.get_conversacion(db, org.id, old_id)
        assert stale is not None
        assert stale.estado == "cerrado"
