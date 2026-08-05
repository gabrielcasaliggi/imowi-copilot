"""Tests canal Telegram (webhook + simulate + delivery)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.estate.database import get_session_factory
from app.estate.models import ConversacionCanal
from main import app

client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": "admin", "password": "admin"})
    assert r.status_code == 200
    return {
        "Authorization": f"Bearer {r.json()['token']}",
        "X-Tenant-Slug": "coop-batan",
    }


def _cerrar_tg(chat_id: str) -> None:
    Session = get_session_factory()
    with Session() as db:
        for c in db.scalars(select(ConversacionCanal)).all():
            if c.canal == "telegram" and (c.telefono == chat_id or c.wa_id == chat_id):
                c.estado = "cerrado"
                c.contexto_json = "{}"
                c.ticket_id = ""
                c.agente_id = ""
        db.commit()


def test_telegram_webhook_sin_secret_en_dev(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.telegram.resolve_telegram",
        lambda _db=None: {
            "bot_token": "",
            "webhook_secret": "",
            "default_org_slug": "coop-batan",
        },
    )
    monkeypatch.setattr("app.api.v1.telegram.es_produccion", lambda: False)
    body = {"update_id": 1, "message": {"message_id": 1, "chat": {"id": 999001}, "text": "hola"}}
    r = client.post(
        "/api/v1/telegram/webhook",
        content=json.dumps(body),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_telegram_webhook_exige_secret(monkeypatch):
    secret = "tg-test-secret"

    monkeypatch.setattr(
        "app.api.v1.telegram.resolve_telegram",
        lambda _db=None: {
            "bot_token": "x:y",
            "webhook_secret": secret,
            "default_org_slug": "coop-batan",
        },
    )
    body = {"update_id": 1}
    raw = json.dumps(body).encode()

    bad = client.post(
        "/api/v1/telegram/webhook",
        content=raw,
        headers={"Content-Type": "application/json"},
    )
    assert bad.status_code == 403

    ok = client.post(
        "/api/v1/telegram/webhook",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Telegram-Bot-Api-Secret-Token": secret,
        },
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "ok"


def test_telegram_simulate_crea_hilo():
    headers = _admin_headers()
    chat_id = "42424201"
    _cerrar_tg(chat_id)
    r = client.post(
        "/api/v1/inbox/simulate",
        headers=headers,
        json={"telefono": chat_id, "texto": "hola", "usar_llama": False, "canal": "telegram"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("ok") is True
    assert data.get("conversacion_id")
    Session = get_session_factory()
    with Session() as db:
        c = db.get(ConversacionCanal, data["conversacion_id"])
        assert c is not None
        assert c.canal == "telegram"
        assert c.telefono == chat_id
        assert c.session_id.startswith("tg:")


def test_telegram_canal_display():
    headers = _admin_headers()
    chat_id = "42424202"
    _cerrar_tg(chat_id)
    sim = client.post(
        "/api/v1/inbox/simulate",
        headers=headers,
        json={"telefono": chat_id, "texto": "hola", "usar_llama": False, "canal": "telegram"},
    )
    assert sim.status_code == 200
    cid = sim.json()["conversacion_id"]
    listing = client.get("/api/v1/inbox/conversations", headers=headers)
    assert listing.status_code == 200
    row = next((x for x in listing.json()["conversaciones"] if x["id"] == cid), None)
    assert row is not None
    assert row["canal"] == "telegram"
    assert row["canal_display"] == "Telegram"
