"""Tests encuesta de satisfacción CSAT."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.estate.database import get_session_factory
from app.estate.models import ConversacionCanal, EncuestaSatisfaccion, Organization
from app.services.encuesta_satisfaccion import (
    ORIGEN_BOT,
    ORIGEN_TECNICO,
    enviar_encuesta_cierre,
    intentar_capturar_voto,
    parse_puntuacion,
)
from main import app

client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": "admin", "password": "admin"})
    assert r.status_code == 200
    return {
        "Authorization": f"Bearer {r.json()['token']}",
        "X-Tenant-Slug": "coop-batan",
    }


def _org_id() -> str:
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        assert org
        return org.id


def test_parse_puntuacion():
    assert parse_puntuacion("5") == 5
    assert parse_puntuacion("1") == 1
    assert parse_puntuacion("csat:3") == 3
    assert parse_puntuacion("2 · Mala") == 2
    assert parse_puntuacion("hola") is None
    assert parse_puntuacion("15") is None


def test_envio_y_voto_bot_simulate():
    headers = _admin_headers()
    tel = "5491112345678"
    Session = get_session_factory()
    with Session() as db:
        for c in db.scalars(
            select(ConversacionCanal).where(ConversacionCanal.telefono.contains("1112345678"))
        ).all():
            c.estado = "cerrado"
            c.contexto_json = "{}"
        db.commit()

    r = client.post(
        "/api/v1/inbox/simulate",
        headers=headers,
        json={
            "telefono": tel,
            "texto": "hola",
            "usar_llama": False,
            "canal": "whatsapp",
        },
    )
    assert r.status_code == 200, r.text
    conv_id = r.json().get("conversacion_id") or r.json().get("conversacion", {}).get("id")
    assert conv_id

    with Session() as db:
        conv = db.get(ConversacionCanal, conv_id)
        assert conv
        conv.estado = "cerrado"
        db.commit()
        out = enviar_encuesta_cierre(db, conv, origen=ORIGEN_BOT, enviar_externo=False)
        assert out["ok"] is True

    capt = None
    with Session() as db:
        capt = intentar_capturar_voto(
            db,
            _org_id(),
            telefono=tel,
            texto="5",
            canal="whatsapp",
            enviar_externo=False,
        )
    assert capt and capt.get("ok")
    assert capt["puntuacion"] == 5
    assert capt["origen"] == ORIGEN_BOT

    with Session() as db:
        row = db.scalar(
            select(EncuestaSatisfaccion).where(EncuestaSatisfaccion.conversacion_id == conv_id)
        )
        assert row is not None
        assert row.puntuacion == 5
        assert row.origen == ORIGEN_BOT


def test_voto_bajo_marca_tag():
    headers = _admin_headers()
    tel = "5491198765432"
    Session = get_session_factory()
    with Session() as db:
        for c in db.scalars(
            select(ConversacionCanal).where(ConversacionCanal.telefono.contains("1198765432"))
        ).all():
            c.estado = "cerrado"
            c.contexto_json = "{}"
            for e in db.scalars(
                select(EncuestaSatisfaccion).where(EncuestaSatisfaccion.conversacion_id == c.id)
            ).all():
                db.delete(e)
        db.commit()

    r = client.post(
        "/api/v1/inbox/simulate",
        headers=headers,
        json={"telefono": tel, "texto": "hola", "usar_llama": False, "canal": "whatsapp"},
    )
    assert r.status_code == 200
    conv_id = r.json().get("conversacion_id") or r.json().get("conversacion", {}).get("id")

    with Session() as db:
        conv = db.get(ConversacionCanal, conv_id)
        assert conv
        conv.estado = "cerrado"
        conv.agente_id = "agente@coopbatan.com"
        db.commit()
        enviar_encuesta_cierre(
            db,
            conv,
            origen=ORIGEN_TECNICO,
            agente_id="agente@coopbatan.com",
            enviar_externo=False,
        )

    with Session() as db:
        capt = intentar_capturar_voto(
            db,
            _org_id(),
            telefono=tel,
            texto="1",
            canal="whatsapp",
            enviar_externo=False,
        )
    assert capt and capt.get("csat_bajo") is True

    from app.estate.models import TicketNotification

    with Session() as db:
        notifs = list(
            db.scalars(
                select(TicketNotification).where(TicketNotification.canal == "csat_bajo")
            ).all()
        )
        assert any("[CSAT_BAJO]" in (n.titulo or "") for n in notifs)
        assert any(n.destinatario for n in notifs)

    r_stats = client.get("/api/v1/analytics/csat", headers=headers)
    assert r_stats.status_code == 200, r_stats.text
    body = r_stats.json()
    assert "resumen" in body
    assert "bot" in body
    assert "agentes" in body


def test_telegram_callback_csat(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.telegram.resolve_telegram",
        lambda _db=None: {
            "bot_token": "",
            "webhook_secret": "",
            "default_org_slug": "coop-batan",
        },
    )
    monkeypatch.setattr("app.api.v1.telegram.es_produccion", lambda: False)
    monkeypatch.setattr(
        "app.api.v1.telegram.answer_callback_query",
        lambda *_a, **_k: {"ok": True},
    )
    body = {
        "update_id": 99,
        "callback_query": {
            "id": "cq1",
            "data": "csat:4",
            "message": {"chat": {"id": 777001}},
        },
    }
    r = client.post(
        "/api/v1/telegram/webhook",
        json=body,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
