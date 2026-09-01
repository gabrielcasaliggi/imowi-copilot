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


def _borrar_inbox_batan() -> None:
    """Hard delete: deja la org sin conversaciones para poder reseedear demos en tests."""
    from app.estate.models import MensajeCanal, Organization

    Session = get_session_factory()
    with Session() as db:
        batan = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        if not batan:
            return
        ids = list(
            db.scalars(
                select(ConversacionCanal.id).where(
                    ConversacionCanal.organizacion_id == batan.id
                )
            ).all()
        )
        if ids:
            for m in db.scalars(
                select(MensajeCanal).where(MensajeCanal.conversacion_id.in_(ids))
            ).all():
                db.delete(m)
            for c in db.scalars(
                select(ConversacionCanal).where(ConversacionCanal.id.in_(ids))
            ).all():
                db.delete(c)
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


def test_extraer_texto_mensaje_wa():
    from app.api.v1.whatsapp import _extraer_texto_mensaje

    assert _extraer_texto_mensaje({"type": "text", "text": {"body": "hola"}}) == "hola"
    assert (
        _extraer_texto_mensaje(
            {
                "type": "interactive",
                "interactive": {
                    "type": "button_reply",
                    "button_reply": {"id": "1", "title": "Sí"},
                },
            }
        )
        == "Sí"
    )
    assert _extraer_texto_mensaje({"type": "image", "image": {"caption": "foto"}}) == "foto"
    assert _extraer_texto_mensaje({"type": "audio", "audio": {"id": "x"}}) == "[audio]"


def test_normalizar_destino_wa_argentina():
    from app.services.whatsapp_client import normalizar_destino_wa

    assert normalizar_destino_wa("+54 9 223 540-2690") == "5492235402690"
    assert normalizar_destino_wa("542235402690") == "5492235402690"
    assert normalizar_destino_wa("5492235402690") == "5492235402690"
    assert normalizar_destino_wa("") == ""


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


def test_whatsapp_dni_desconocido_deriva_visitante():
    headers = _admin_headers()
    tel = "5492235599988"
    _cerrar_convs_telefono(tel)
    r1 = client.post(
        "/api/v1/inbox/simulate",
        headers=headers,
        json={"telefono": tel, "texto": "Hola", "usar_llama": False},
    )
    assert r1.status_code == 200
    assert r1.json()["estado"] == "bot"
    assert "dni" in (r1.json().get("respuesta") or "").lower()

    r2 = client.post(
        "/api/v1/inbox/simulate",
        headers=headers,
        json={"telefono": tel, "texto": "99887766", "usar_llama": False},
    )
    assert r2.status_code == 200
    data = r2.json()
    assert data["estado"] == "espera_agente"
    assert not data.get("ticket_id")
    assert "agente" in (data.get("respuesta") or "").lower()

    listed = client.get("/api/v1/inbox/conversations", headers=headers)
    sample = next(c for c in listed.json()["conversaciones"] if c["id"] == data["conversacion_id"])
    assert sample.get("es_visitante") is True
    assert sample.get("cola_prioridad") == "baja"


def test_visitante_en_cola_identifica_con_dni_despues():
    """En espera_agente, un DNI válido vincula la cuenta sin repetir «ya derivado»."""
    headers = _admin_headers()
    tel = "5492235599977"
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
        json={"telefono": tel, "texto": "99887766", "usar_llama": False},
    )
    assert r2.status_code == 200
    assert r2.json()["estado"] == "espera_agente"

    r3 = client.post(
        "/api/v1/inbox/simulate",
        headers=headers,
        json={"telefono": tel, "texto": "30111222", "usar_llama": False},
    )
    assert r3.status_code == 200
    data = r3.json()
    assert data["estado"] == "espera_agente"
    resp = (data.get("respuesta") or "").lower()
    assert "ya te identifiqu" in resp or "ya te identifique" in resp
    assert "ya está derivado" not in resp and "ya esta derivado" not in resp
    assert data.get("identificado_en_cola") is True

    listed = client.get("/api/v1/inbox/conversations", headers=headers)
    sample = next(c for c in listed.json()["conversaciones"] if c["id"] == data["conversacion_id"])
    assert sample.get("abonado")
    assert sample.get("cola_prioridad") == "alta"


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
    _borrar_inbox_batan()
    Session = get_session_factory()
    with Session() as db:
        info = seed_inbox_conversaciones(db)
        assert info.get("seeded") is True or info.get("conversaciones", 0) >= 1

    headers = _batan_headers()
    listed = client.get("/api/v1/inbox/conversations", headers=headers)
    assert listed.status_code == 200
    convs = [c for c in listed.json()["conversaciones"] if c["estado"] != "cerrado"]
    assert len(convs) >= 1
    assert all(c.get("canal_display") in ("whatsapp", "WhatsApp", "Web", "App") for c in convs)

    en_cola = next((c for c in convs if c["estado"] == "espera_agente"), convs[0])
    claim = client.post(
        f"/api/v1/inbox/conversations/{en_cola['id']}/claim",
        headers=headers,
    )
    assert claim.status_code == 200
    assert claim.json()["conversacion"]["estado"] == "con_agente"


def test_seed_inbox_no_recrea_si_solo_hay_cerradas():
    """Cerrar todas no debe volver a abrir demos en el próximo seed (restart)."""
    _borrar_inbox_batan()
    Session = get_session_factory()
    with Session() as db:
        assert seed_inbox_conversaciones(db).get("seeded") is True
    _cerrar_todas_batan()
    with Session() as db:
        info = seed_inbox_conversaciones(db)
        assert info.get("seeded") is False
        assert info.get("reason") == "ya_existen"
    headers = _batan_headers()
    listed = client.get("/api/v1/inbox/conversations", headers=headers)
    abiertas = [c for c in listed.json()["conversaciones"] if c["estado"] != "cerrado"]
    assert abiertas == []


def test_claim_ticket_syncs_linked_conversation():
    """POST /tickets/{id}/claim debe tomar la conversación ligada (también ya_asignado)."""
    admin_headers = _admin_headers()
    agent_headers = _batan_headers()
    tel = "5492235560101"
    _cerrar_convs_telefono(tel)
    client.post(
        "/api/v1/inbox/simulate",
        headers=admin_headers,
        json={"telefono": tel, "texto": "Hola", "usar_llama": False},
    )
    r_agente = client.post(
        "/api/v1/inbox/simulate",
        headers=admin_headers,
        json={"telefono": tel, "texto": "*agente*", "usar_llama": False},
    )
    assert r_agente.status_code == 200
    ticket_id = r_agente.json().get("ticket_id")
    assert ticket_id

    listed = client.get("/api/v1/inbox/conversations", headers=admin_headers)
    conv = next(
        c
        for c in listed.json()["conversaciones"]
        if c.get("ticket_id") == ticket_id
    )
    assert conv["estado"] == "espera_agente"

    claim = client.post(f"/api/v1/tickets/{ticket_id}/claim", headers=agent_headers)
    assert claim.status_code == 200
    data = claim.json()
    assert data["conversacion_id"] == conv["id"]
    assert data.get("ya_asignado") is False

    Session = get_session_factory()
    with Session() as db:
        c = db.get(ConversacionCanal, conv["id"])
        assert c.estado == "con_agente"
        assert c.agente_id == "batan@ops-hub.demo"

    claim2 = client.post(f"/api/v1/tickets/{ticket_id}/claim", headers=agent_headers)
    assert claim2.status_code == 200
    assert claim2.json().get("ya_asignado") is True
    assert claim2.json()["conversacion_id"] == conv["id"]

    with Session() as db:
        c = db.get(ConversacionCanal, conv["id"])
        c.estado = "espera_agente"
        c.agente_id = ""
        db.commit()

    claim3 = client.post(f"/api/v1/tickets/{ticket_id}/claim", headers=agent_headers)
    assert claim3.status_code == 200
    assert claim3.json().get("ya_asignado") is True
    assert claim3.json()["conversacion_id"] == conv["id"]

    with Session() as db:
        c = db.get(ConversacionCanal, conv["id"])
        assert c.estado == "con_agente"
        assert c.agente_id == "batan@ops-hub.demo"


def test_abonados_seed():
    headers = _batan_headers()
    r = client.get("/api/v1/inbox/abonados", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["abonados"]) >= 3
