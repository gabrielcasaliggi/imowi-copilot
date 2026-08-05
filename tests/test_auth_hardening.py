"""Tests hardening auth consola + portal (doble identidad)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.services import email as email_svc
from main import app

client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": "admin", "password": "admin"})
    assert r.status_code == 200
    return {
        "Authorization": f"Bearer {r.json()['token']}",
        "X-Tenant-Slug": "coop-batan",
    }


def test_demo_login_ok_en_development():
    r = client.post("/api/login", json={"usuario": "admin", "password": "admin"})
    assert r.status_code == 200
    data = r.json()
    assert data["token"]
    # Token consola debe decodificar con typ console (vía /me)
    me = client.get("/api/me", headers={"Authorization": f"Bearer {data['token']}"})
    assert me.status_code == 200


def test_password_policy_reject():
    from app.estate.security import password_policy_errors, valid_password

    assert not valid_password("corta")
    assert password_policy_errors("Password1") == [] or valid_password("Password1a")
    assert valid_password("Password1ab")


def test_invite_flow():
    email_svc.clear_outbox()
    headers = _admin_headers()
    import uuid

    email = f"nuevo.op.{uuid.uuid4().hex[:8]}@test.local"
    r = client.post(
        "/api/v1/auth/invites",
        headers=headers,
        json={"email": email, "nombre": "Nuevo Op", "rol": "agente"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == email
    token = body.get("token")
    assert token

    peek = client.get(f"/api/v1/auth/invite/{token}")
    assert peek.status_code == 200
    assert peek.json()["email"] == email

    acc = client.post(
        "/api/v1/auth/invite/accept",
        json={"token": token, "password": "SeguraPass12", "nombre": "Nuevo Op"},
    )
    assert acc.status_code == 200, acc.text

    login = client.post(
        "/api/login",
        json={"usuario": email, "password": "SeguraPass12"},
    )
    assert login.status_code == 200


def test_legacy_tickets_require_auth():
    r = client.get("/api/listar-tickets")
    assert r.status_code == 401
    r2 = client.patch("/api/cerrar-ticket/TKT-NOEXISTE")
    assert r2.status_code == 401


def test_portal_guest_no_identifica_por_dni():
    r = client.post(
        "/api/v1/portal/session",
        json={"dni": "30111222", "org_slug": "coop-batan"},
    )
    assert r.status_code == 200
    assert r.json()["abonado_identificado"] is False
    assert r.json()["modo_invitado"] is True


def test_portal_guest_bloqueado_cuando_allow_guest_false(monkeypatch):
    monkeypatch.setattr("app.api.v1.portal.PORTAL_ALLOW_GUEST", False)
    r = client.post(
        "/api/v1/portal/session",
        json={"org_slug": "coop-batan"},
    )
    assert r.status_code == 401


def test_portal_otp_flow_and_cross_token():
    email_svc.clear_outbox()
    start = client.post(
        "/api/v1/portal/auth/start",
        json={"dni": "30111222", "org_slug": "coop-batan"},
    )
    assert start.status_code == 200, start.text
    data = start.json()
    assert data["challenge_id"]
    assert data["contact_masked"]
    otp = data.get("debug_otp")
    assert otp

    verify = client.post(
        "/api/v1/portal/auth/verify",
        json={"challenge_id": data["challenge_id"], "otp": otp, "org_slug": "coop-batan"},
    )
    assert verify.status_code == 200, verify.text
    portal_token = verify.json()["portal_token"]
    assert verify.json()["abonado_identificado"] is True

    # Token portal no abre /api/me consola
    me = client.get("/api/me", headers={"Authorization": f"Bearer {portal_token}"})
    assert me.status_code == 401

    # Token consola no abre portal messages
    console = client.post("/api/login", json={"usuario": "admin", "password": "admin"}).json()["token"]
    msg = client.post(
        "/api/v1/portal/messages",
        headers={"Authorization": f"Bearer {console}"},
        json={"texto": "hola"},
    )
    assert msg.status_code == 401

    # Portal token sí puede enviar
    ok = client.post(
        "/api/v1/portal/messages",
        headers={"Authorization": f"Bearer {portal_token}"},
        json={"texto": "Hola, no me anda el internet"},
    )
    assert ok.status_code == 200


def test_portal_anti_enum():
    """DNIs inexistentes deben fallar con el mismo mensaje genérico (sin filtrar existencia)."""
    r1 = client.post(
        "/api/v1/portal/auth/start",
        json={"dni": "00000001", "org_slug": "coop-batan"},
    )
    r2 = client.post(
        "/api/v1/portal/auth/start",
        json={"dni": "00000002", "org_slug": "coop-batan"},
    )
    assert r1.status_code == 400
    assert r2.status_code == 400
    assert r1.json()["detail"] == r2.json()["detail"]


def test_portal_set_pin_and_login():
    email_svc.clear_outbox()
    start = client.post(
        "/api/v1/portal/auth/start",
        json={"dni": "28555666", "org_slug": "coop-batan"},
    )
    otp = start.json()["debug_otp"]
    verify = client.post(
        "/api/v1/portal/auth/verify",
        json={"challenge_id": start.json()["challenge_id"], "otp": otp},
    )
    token = verify.json()["portal_token"]
    pin_set = client.post(
        "/api/v1/portal/auth/set-pin",
        headers={"Authorization": f"Bearer {token}"},
        json={"pin": "123456"},
    )
    assert pin_set.status_code == 200

    login = client.post(
        "/api/v1/portal/auth/login-pin",
        json={"dni": "28555666", "pin": "123456", "org_slug": "coop-batan"},
    )
    assert login.status_code == 200
    assert login.json()["abonado_identificado"] is True
