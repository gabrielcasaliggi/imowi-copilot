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


def _portal_identified(dni: str = "30111222") -> dict:
    start = client.post(
        "/api/v1/portal/auth/start",
        json={"dni": dni, "org_slug": "coop-batan"},
    )
    assert start.status_code == 200, start.text
    otp = start.json()["debug_otp"]
    verify = client.post(
        "/api/v1/portal/auth/verify",
        json={"challenge_id": start.json()["challenge_id"], "otp": otp, "org_slug": "coop-batan"},
    )
    assert verify.status_code == 200, verify.text
    return verify.json()


def test_login_batan_es_agente():
    r = client.post("/api/login", json={"usuario": "batan", "password": "batan"})
    assert r.status_code == 200
    assert r.json()["rol"] == "agente"
    assert "Batán" in r.json()["nombre"] or "batan" in r.json()["nombre"].lower()


def test_portal_session_guest():
    r = client.post(
        "/api/v1/portal/session",
        json={"org_slug": "coop-batan"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["portal_token"]
    assert data["abonado_identificado"] is False
    assert data["conversacion"]["canal"] == "web"
    assert data["conversacion"]["canal_display"] == "Web"
    assert len(data["mensajes"]) >= 1


def test_portal_chat_y_agente_ve_cola():
    sess = _portal_identified("30111222")
    token = sess["portal_token"]
    conv_id = sess["conversacion"]["id"]

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
    sess = _portal_identified("26444555")
    token = sess["portal_token"]
    client.post(
        "/api/v1/portal/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"texto": "Quiero hablar con un agente"},
    )
    # Puede escalar o responder; no debe 500
    listed = client.get("/api/v1/inbox/conversations", headers=_batan_headers())
    assert listed.status_code == 200


def test_portal_guest_mensaje_deuda_no_500(monkeypatch):
    """Regresión: invitado + consulta deuda no debe NameError por dni."""
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app)

    def fake_llm(*_a, **_k):
        raise AssertionError("invitado+deuda no debería necesitar LLM")

    r = client.post("/api/v1/portal/session", json={"org_slug": "coop-batan"})
    assert r.status_code == 200
    token = r.json()["portal_token"]

    with patch("app.llm.chat_completion", side_effect=fake_llm):
        msg = client.post(
            "/api/v1/portal/messages",
            headers={"Authorization": f"Bearer {token}"},
            json={"texto": "Necesito saber si tengo deuda"},
        )
    assert msg.status_code == 200, msg.text
    body = msg.json()
    assert body.get("ok") is True
    resp = (body.get("respuesta") or "").lower()
    if not resp:
        bots = [
            m.get("texto", "")
            for m in (body.get("mensajes") or [])
            if m.get("autor") == "bot"
        ]
        resp = (bots[-1] if bots else "").lower()
    assert "dni" in resp
    assert "fiserv" not in resp
    assert "internal server" not in resp
