"""Tests MVP inbox / canal abonado / WhatsApp verify."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.estate.database import get_session_factory
from app.estate.models import ConversacionCanal
from main import app

client = TestClient(app)


def _cerrar_convs_telefono(telefono: str) -> None:
    tel = "".join(c for c in telefono if c.isdigit())
    Session = get_session_factory()
    with Session() as db:
        rows = list(
            db.scalars(
                select(ConversacionCanal).where(ConversacionCanal.telefono == tel)
            ).all()
        )
        # también sufijo sin 54
        suf = tel[-10:] if len(tel) >= 10 else tel
        rows2 = list(db.scalars(select(ConversacionCanal)).all())
        for c in rows2:
            if c.telefono.endswith(suf) or c.telefono == tel:
                c.estado = "cerrado"
                c.contexto_json = "{}"
                c.ticket_id = ""
                c.agente_id = ""
        for c in rows:
            c.estado = "cerrado"
            c.contexto_json = "{}"
            c.ticket_id = ""
            c.agente_id = ""
        db.commit()


def _batan_headers() -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": "batan", "password": "batan"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _admin_headers() -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": "admin", "password": "admin"})
    assert r.status_code == 200
    return {
        "Authorization": f"Bearer {r.json()['token']}",
        "X-Tenant-Slug": "coop-batan",
    }


def test_whatsapp_webhook_verify():
    r = client.get(
        "/api/v1/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "ops-hub-wa-verify",
            "hub.challenge": "12345",
        },
    )
    assert r.status_code == 200
    assert r.text == "12345"


def test_whatsapp_webhook_verify_reject():
    r = client.get(
        "/api/v1/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "1",
        },
    )
    assert r.status_code == 403


def test_simulate_identifica_y_responde():
    headers = _batan_headers()
    tel = "5492235551234"
    _cerrar_convs_telefono(tel)
    r = client.post(
        "/api/v1/inbox/simulate",
        headers=headers,
        json={"telefono": tel, "texto": "Hola", "usar_llama": False},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["conversacion_id"]
    assert "María" in (data.get("respuesta") or "") or "Maria" in (data.get("respuesta") or "")


def test_simulate_deuda_escala_o_playbook():
    headers = _batan_headers()
    tel = "5492235559012"
    _cerrar_convs_telefono(tel)
    r1 = client.post(
        "/api/v1/inbox/simulate",
        headers=headers,
        json={"telefono": tel, "texto": "Hola", "usar_llama": False},
    )
    assert r1.status_code == 200
    r2 = client.post(
        "/api/v1/inbox/simulate",
        headers=headers,
        json={
            "telefono": tel,
            "texto": "No tengo internet, creo que me cortaron",
            "usar_llama": False,
        },
    )
    assert r2.status_code == 200
    assert r2.json()["ok"] is True


def test_inbox_list_and_claim():
    headers = _admin_headers()
    tel = "5492235560002"
    _cerrar_convs_telefono(tel)
    client.post(
        "/api/v1/inbox/simulate",
        headers=headers,
        json={"telefono": tel, "texto": "Hola", "usar_llama": False},
    )
    listed = client.get("/api/v1/inbox/conversations", headers=headers)
    assert listed.status_code == 200
    convs = listed.json()["conversaciones"]
    assert len(convs) >= 1
    cid = next(
        c["id"]
        for c in convs
        if c["telefono"].endswith("5560002") or c["telefono"] == tel
    )
    claim = client.post(f"/api/v1/inbox/conversations/{cid}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json()["conversacion"]["estado"] == "con_agente"


def test_pide_agente_crea_ticket_n2():
    headers = _batan_headers()
    tel = "5492235560099"
    _cerrar_convs_telefono(tel)
    r0 = client.post(
        "/api/v1/inbox/simulate",
        headers=headers,
        json={"telefono": tel, "texto": "Hola", "usar_llama": False},
    )
    assert r0.status_code == 200
    assert "Pedro" in (r0.json().get("respuesta") or "")
    r = client.post(
        "/api/v1/inbox/simulate",
        headers=headers,
        json={
            "telefono": tel,
            "texto": "Quiero hablar con un agente humano",
            "usar_llama": False,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("ticket_id")
    assert data.get("estado") == "espera_agente"


def test_abonados_seed():
    headers = _batan_headers()
    r = client.get("/api/v1/inbox/abonados", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["abonados"]) >= 3
