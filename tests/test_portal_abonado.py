"""Tests portal abonado + roles agente."""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _batan_headers() -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": "batan", "password": "batan"})
    assert r.status_code == 200
    assert r.json()["rol"] == "agente"
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _admin_headers() -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": "admin", "password": "admin"})
    assert r.status_code == 200
    return {
        "Authorization": f"Bearer {r.json()['token']}",
        "X-Tenant-Slug": "coop-batan",
    }


def test_login_batan_es_agente():
    r = client.post("/api/login", json={"usuario": "batan", "password": "batan"})
    assert r.status_code == 200
    assert r.json()["rol"] == "agente"
    assert "Batán" in r.json()["nombre"] or "batan" in r.json()["nombre"].lower()


def test_portal_session_por_telefono():
    r = client.post(
        "/api/v1/portal/session",
        json={"telefono": "5492235551234", "org_slug": "coop-batan"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["portal_token"]
    assert data["abonado_identificado"] is True
    assert data["conversacion"]["canal"] == "web"
    assert data["conversacion"]["canal_display"] == "Web"
    assert len(data["mensajes"]) >= 1


def test_portal_chat_y_agente_ve_cola():
    sess = client.post(
        "/api/v1/portal/session",
        json={"telefono": "5492235555678", "org_slug": "coop-batan"},
    )
    assert sess.status_code == 200
    token = sess.json()["portal_token"]
    conv_id = sess.json()["conversacion"]["id"]

    msg = client.post(
        "/api/v1/portal/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"texto": "No me anda el internet"},
    )
    assert msg.status_code == 200
    assert msg.json()["ok"] is True

    listed = client.get("/api/v1/inbox/conversations", headers=_batan_headers())
    assert listed.status_code == 200
    ids = [c["id"] for c in listed.json()["conversaciones"]]
    assert conv_id in ids
    sample = next(c for c in listed.json()["conversaciones"] if c["id"] == conv_id)
    assert sample["canal_display"] == "Web"


def test_portal_pide_agente():
    sess = client.post(
        "/api/v1/portal/session",
        json={"telefono": "5492235560099", "org_slug": "coop-batan"},
    )
    token = sess.json()["portal_token"]
    client.post(
        "/api/v1/portal/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"texto": "Hola"},
    )
    r = client.post(
        "/api/v1/portal/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"texto": "Quiero hablar con un agente"},
    )
    assert r.status_code == 200
    assert r.json().get("estado") == "espera_agente"
    assert r.json().get("ticket_id")


def test_portal_invitado_sin_match():
    r = client.post(
        "/api/v1/portal/session",
        json={"telefono": "5492239990000", "org_slug": "coop-batan"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["abonado_identificado"] is False
    assert data["modo_invitado"] is True
    assert data["portal_token"]
    token = data["portal_token"]
    msg = client.post(
        "/api/v1/portal/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"texto": "No me anda el internet por radio"},
    )
    assert msg.status_code == 200
    assert msg.json()["ok"] is True
    assert msg.json().get("intencion") in ("internet_radio", "internet", "general")


def test_portal_invitado_sin_datos():
    r = client.post("/api/v1/portal/session", json={"org_slug": "coop-batan"})
    assert r.status_code == 200
    data = r.json()
    assert data["abonado_identificado"] is False
    assert data["modo_invitado"] is True
    assert data["conversacion"]["telefono"].startswith("guest")


def test_portal_invitado_pide_agente_y_agente_toma():
    """Invitado escribe 'agente' → cola; el agente puede Tomar y responder."""
    sess = client.post(
        "/api/v1/portal/session",
        json={"telefono": "5492238887777", "org_slug": "coop-batan"},
    )
    assert sess.status_code == 200
    assert sess.json()["abonado_identificado"] is False
    token = sess.json()["portal_token"]
    cid = sess.json()["conversacion"]["id"]

    client.post(
        "/api/v1/portal/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"texto": "tengo problemas de wifi"},
    )
    r = client.post(
        "/api/v1/portal/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"texto": "agente"},
    )
    assert r.status_code == 200
    assert r.json().get("estado") == "espera_agente"
    assert r.json().get("ticket_id")

    claim = client.post(
        f"/api/v1/inbox/conversations/{cid}/claim",
        headers=_batan_headers(),
    )
    assert claim.status_code == 200
    assert claim.json()["conversacion"]["estado"] == "con_agente"

    send = client.post(
        f"/api/v1/inbox/conversations/{cid}/messages",
        headers=_batan_headers(),
        json={"texto": "Hola, soy el agente, ¿en qué te ayudo?"},
    )
    assert send.status_code == 200


def test_agente_puede_tomar_chat_en_bot():
    """Tomar funciona también mientras el estado sigue en bot."""
    sess = client.post(
        "/api/v1/portal/session",
        json={"telefono": "5492238886666", "org_slug": "coop-batan"},
    )
    cid = sess.json()["conversacion"]["id"]
    token = sess.json()["portal_token"]
    client.post(
        "/api/v1/portal/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"texto": "consulta por ADSL"},
    )
    # Sigue en bot
    detail = client.get(
        f"/api/v1/inbox/conversations/{cid}",
        headers=_batan_headers(),
    )
    assert detail.json()["conversacion"]["estado"] == "bot"

    claim = client.post(
        f"/api/v1/inbox/conversations/{cid}/claim",
        headers=_batan_headers(),
    )
    assert claim.status_code == 200
    assert claim.json()["conversacion"]["estado"] == "con_agente"

    send = client.post(
        f"/api/v1/inbox/conversations/{cid}/messages",
        headers=_batan_headers(),
        json={"texto": "Te atiendo yo."},
    )
    assert send.status_code == 200


def test_admin_reasigna():
    sess = client.post(
        "/api/v1/portal/session",
        json={"dni": "30111222", "org_slug": "coop-batan"},
    )
    cid = sess.json()["conversacion"]["id"]
    token = sess.json()["portal_token"]
    client.post(
        "/api/v1/portal/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"texto": "Necesito un técnico humano"},
    )
    r = client.post(
        f"/api/v1/inbox/conversations/{cid}/assign",
        headers=_admin_headers(),
        json={"agente_id": "batan@ops-hub.demo", "agente_nombre": "Agente Batán"},
    )
    assert r.status_code == 200
    assert r.json()["conversacion"]["estado"] == "con_agente"
    assert r.json()["conversacion"]["agente_id"] == "batan@ops-hub.demo"
