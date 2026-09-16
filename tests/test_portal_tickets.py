"""Portal — mis tickets del abonado autenticado."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.estate.database import get_session_factory
from app.estate.models import ConversacionCanal
from main import app
from tests.conftest import add_ticket

client = TestClient(app)


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


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Canal": "app"}


def test_portal_tickets_requiere_jwt():
    r = client.get("/api/v1/portal/tickets", headers={"X-Canal": "app"})
    assert r.status_code == 401


def test_portal_tickets_vacio_sin_tickets():
    sess = _portal_identified("30111222")
    r = client.get("/api/v1/portal/tickets", headers=_headers(sess["portal_token"]))
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data["items"], list)
    assert data["total"] == len(data["items"])


def test_portal_tickets_lista_y_detalle_propios():
    sess = _portal_identified("30111222")
    token = sess["portal_token"]
    conv = sess["conversacion"]
    assert (conv.get("abonado") or {}).get("id")
    tid = f"TK-P-{uuid.uuid4().hex[:10]}"

    db = get_session_factory()()
    try:
        c = db.get(ConversacionCanal, conv["id"])
        assert c is not None
        t = add_ticket(
            db,
            c.organizacion_id,
            id=tid,
            estado="Abierto",
            categoria="Internet",
            linea=(c.telefono or "2235550000"),
            descripcion_falla="Corte reportado por portal test",
        )
        c.ticket_id = t.id
        db.commit()
    finally:
        db.close()

    r = client.get("/api/v1/portal/tickets", headers=_headers(token))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert any(i["id"] == tid for i in items)
    mine = next(i for i in items if i["id"] == tid)
    assert mine["estado"] == "Abierto"
    assert mine["categoria"] == "Internet"
    assert mine["conversacion_id"] == conv["id"]
    assert "asignado_a" not in mine
    assert "estado_sla" not in mine

    d = client.get(f"/api/v1/portal/tickets/{tid}", headers=_headers(token))
    assert d.status_code == 200, d.text
    body = d.json()
    assert body["ticket"]["id"] == tid
    assert isinstance(body["eventos"], list)


def test_portal_tickets_no_ve_ajenos():
    sess_a = _portal_identified("30111222")
    sess_b = _portal_identified("26444555")
    token_b = sess_b["portal_token"]
    tid = f"TK-S-{uuid.uuid4().hex[:10]}"

    db = get_session_factory()()
    try:
        c_a = db.get(ConversacionCanal, sess_a["conversacion"]["id"])
        assert c_a is not None
        t = add_ticket(
            db,
            c_a.organizacion_id,
            id=tid,
            estado="Abierto",
            categoria="Privado",
            linea="9999999999",
        )
        c_a.ticket_id = t.id
        db.commit()
    finally:
        db.close()

    r = client.get("/api/v1/portal/tickets", headers=_headers(token_b))
    assert r.status_code == 200
    ids = {i["id"] for i in r.json()["items"]}
    assert tid not in ids

    d = client.get(f"/api/v1/portal/tickets/{tid}", headers=_headers(token_b))
    assert d.status_code == 404
