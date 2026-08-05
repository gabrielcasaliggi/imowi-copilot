"""Tests inbox / canal abonado / WhatsApp verify (look producción)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.estate.database import get_session_factory
from app.estate.models import ConversacionCanal
from app.estate.seed import seed_inbox_conversaciones
from main import app

client = TestClient(app)


def _cerrar_convs_telefono(telefono: str) -> None:
    tel = "".join(c for c in telefono if c.isdigit())
    Session = get_session_factory()
    with Session() as db:
        rows2 = list(db.scalars(select(ConversacionCanal)).all())
        suf = tel[-10:] if len(tel) >= 10 else tel
        for c in rows2:
            if c.telefono.endswith(suf) or c.telefono == tel:
                c.estado = "cerrado"
                c.contexto_json = "{}"
                c.ticket_id = ""
                c.agente_id = ""
        db.commit()


def _cerrar_todas_batan() -> None:
    Session = get_session_factory()
    with Session() as db:
        for c in db.scalars(select(ConversacionCanal)).all():
            c.estado = "cerrado"
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


def test_whatsapp_webhook_exige_firma_cuando_hay_secret(monkeypatch):
    import hashlib
    import hmac
    import json

    secret = "meta-test-app-secret"

    def _wa(_db=None):
        return {
            "token": "",
            "phone_number_id": "",
            "verify_token": "ops-hub-wa-verify",
            "app_secret": secret,
            "default_org_slug": "coop-batan",
        }

    monkeypatch.setattr("app.api.v1.whatsapp.resolve_whatsapp", _wa)
    body = {"object": "whatsapp_business_account", "entry": []}
    raw = json.dumps(body).encode("utf-8")

    bad = client.post(
        "/api/v1/whatsapp/webhook",
        content=raw,
        headers={"Content-Type": "application/json"},
    )
    assert bad.status_code == 403

    sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    ok = client.post(
        "/api/v1/whatsapp/webhook",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
        },
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "ok"


def test_batan_no_puede_inyectar():
    headers = _batan_headers()
    r = client.post(
        "/api/v1/inbox/simulate",
        headers=headers,
        json={"telefono": "5492235551234", "texto": "Hola", "usar_llama": False},
    )
    assert r.status_code == 403


def test_admin_inyecta_identifica_y_responde():
    headers = _admin_headers()
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


def test_admin_inyecta_deuda_playbook():
    headers = _admin_headers()
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
    sample = next(
        c
        for c in convs
        if c["telefono"].endswith("5560002") or c["telefono"] == tel
    )
    assert sample.get("canal_display") in ("whatsapp", "WhatsApp")
    cid = sample["id"]
    claim = client.post(f"/api/v1/inbox/conversations/{cid}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json()["conversacion"]["estado"] == "con_agente"


def test_pide_agente_crea_ticket_n2():
    """Handoff humano: 1er pedido sin síntoma → menú; *agente* → ticket."""
    headers = _admin_headers()
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
    assert data.get("estado") == "bot"
    assert not data.get("ticket_id")
    r2 = client.post(
        "/api/v1/inbox/simulate",
        headers=headers,
        json={"telefono": tel, "texto": "*agente*", "usar_llama": False},
    )
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2.get("ticket_id")
    assert data2.get("estado") == "espera_agente"


def test_batan_ve_conversaciones_y_puede_tomar():
    _cerrar_todas_batan()
    Session = get_session_factory()
    with Session() as db:
        info = seed_inbox_conversaciones(db)
        assert info.get("seeded") is True or info.get("conversaciones", 0) >= 1

    headers = _batan_headers()
    listed = client.get("/api/v1/inbox/conversations", headers=headers)
    assert listed.status_code == 200
    convs = [c for c in listed.json()["conversaciones"] if c["estado"] != "cerrado"]
    assert len(convs) >= 1
    assert all(c.get("canal_display") in ("whatsapp", "WhatsApp", "Web") for c in convs)

    en_cola = next((c for c in convs if c["estado"] == "espera_agente"), convs[0])
    claim = client.post(
        f"/api/v1/inbox/conversations/{en_cola['id']}/claim",
        headers=headers,
    )
    assert claim.status_code == 200
    assert claim.json()["conversacion"]["estado"] == "con_agente"


def test_abonados_seed():
    headers = _batan_headers()
    r = client.get("/api/v1/inbox/abonados", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["abonados"]) >= 3
