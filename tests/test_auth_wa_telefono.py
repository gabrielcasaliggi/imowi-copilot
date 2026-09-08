"""F1: auth WhatsApp por celular BillTrack + desambiguación."""

from __future__ import annotations

from sqlalchemy import select

from app.services.billtrack import (
    DEFAULT_LOOKUP_BY_PHONE_SQL,
    dni_desde_doc_cuit,
    lookup_abonados_por_telefono,
    lookup_phone_sql,
)


def test_default_phone_sql_usa_api_person_phone():
    sql = lookup_phone_sql().lower()
    assert "api_person_phone" in sql
    assert ":phone" in lookup_phone_sql()
    assert ":phone_suf10" in lookup_phone_sql()
    assert DEFAULT_LOOKUP_BY_PHONE_SQL.strip().lower().startswith("select")


def test_dni_desde_doc_cuit():
    assert dni_desde_doc_cuit("20-30111222-3") == "30111222"
    assert dni_desde_doc_cuit("30111222") == "30111222"
    assert dni_desde_doc_cuit("") == ""
    assert dni_desde_doc_cuit("123") == ""


def test_lookup_por_telefono_unico_mock():
    hits = lookup_abonados_por_telefono("5492235551234", db=None)
    assert len(hits) == 1
    assert hits[0]["dni"] == "30111222"
    assert "María" in hits[0]["nombre"] or "Maria" in hits[0]["nombre"]


def test_lookup_por_telefono_multiple_mock():
    hits = lookup_abonados_por_telefono("5492235577777", db=None)
    assert len(hits) == 2
    dnis = {h["dni"] for h in hits}
    assert dnis == {"31111001", "31111002"}


def test_lookup_por_telefono_sin_match():
    assert lookup_abonados_por_telefono("5492235000000", db=None) == []


def test_lookup_por_telefono_falla_en_prod_no_tira(monkeypatch):
    from app.services import billtrack as bt

    monkeypatch.setattr(
        bt,
        "resolve_connection",
        lambda db=None: {
            "enabled": True,
            "url": "postgresql+psycopg://u:p@127.0.0.1:1/db",
            "sslmode": "disable",
        },
    )
    monkeypatch.setenv("BILLTRACK_LOOKUP_READY", "1")
    import app.config as cfg

    monkeypatch.setattr(cfg, "BILLTRACK_ENABLED", True)
    monkeypatch.setattr(cfg, "es_produccion", lambda: True)

    class Boom:
        def connect(self):
            raise OSError("billtrack down")

        def dispose(self):
            return None

    import sqlalchemy

    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *a, **k: Boom())
    assert bt.lookup_abonados_por_telefono("5492235551234", db=None) == []


def _reset_conv_wa(db, org_id: str, tel: str):
    from app.estate import canal_repo as crepo
    from app.estate.models import ConversacionCanal

    for c in db.scalars(
        select(ConversacionCanal).where(ConversacionCanal.telefono.contains(tel[-10:]))
    ).all():
        c.estado = "cerrado"
        c.contexto_json = "{}"
        c.ticket_id = ""
        c.agente_id = ""
        c.abonado_id = ""
    db.commit()
    conv = crepo.get_or_create_conversacion(
        db, org_id, telefono=tel, canal="whatsapp", wa_id=tel
    )
    conv.estado = "bot"
    conv.abonado_id = ""
    conv.contexto_json = "{}"
    db.commit()
    return conv


def test_wa_auth_telefono_unico_vincula(monkeypatch):
    from app.estate.database import get_session_factory
    from app.estate.models import Organization
    from app.services.canal_abonado import procesar_mensaje_entrante

    # Evitar soft-match local previo: usar teléfono de María del mock
    tel = "5492235551234"
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        assert org
        _reset_conv_wa(db, org.id, tel)
        org_id = org.id

    with Session() as db:
        r = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto="hola",
            canal="whatsapp",
            wa_id=tel,
            usar_llama=False,
        )
    assert r.get("ok") is True
    assert r.get("estado") == "bot"
    resp = (r.get("respuesta") or "").lower()
    # No debe pedir DNI: ya identificado por MSISDN
    assert "enviame tu dni" not in resp
    assert "dni o número de socio" not in resp
    assert "dni o numero de socio" not in resp

    with Session() as db:
        from app.estate import canal_repo as crepo

        conv = crepo.get_or_create_conversacion(
            db, org_id, telefono=tel, canal="whatsapp", wa_id=tel
        )
        assert conv.abonado_id
        ctx = crepo.get_contexto(conv)
        assert ctx.get("identificado") is True
        assert ctx.get("dni") == "30111222"


def test_wa_auth_telefono_multiple_desambigua_y_elige():
    from app.estate.database import get_session_factory
    from app.estate.models import Organization
    from app.services.canal_abonado import procesar_mensaje_entrante

    tel = "5492235577777"
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        assert org
        _reset_conv_wa(db, org.id, tel)
        org_id = org.id

    with Session() as db:
        r0 = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto="hola",
            canal="whatsapp",
            wa_id=tel,
            usar_llama=False,
        )
    assert r0.get("phone_disambiguation") is True
    resp0 = r0.get("respuesta") or ""
    assert "más de una cuenta" in resp0.lower() or "mas de una cuenta" in resp0.lower()
    assert "1)" in resp0 and "2)" in resp0
    assert "@" not in resp0  # sin email
    assert "cuenta alfa" in resp0.lower()

    with Session() as db:
        r1 = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto="1",
            canal="whatsapp",
            wa_id=tel,
            usar_llama=False,
        )
    assert r1.get("identificado_por") == "whatsapp_msisdn"
    assert "ubiqué por este whatsapp" in (r1.get("respuesta") or "").lower()

    with Session() as db:
        from app.estate import canal_repo as crepo

        conv = crepo.get_or_create_conversacion(
            db, org_id, telefono=tel, canal="whatsapp", wa_id=tel
        )
        ctx = crepo.get_contexto(conv)
        assert ctx.get("dni") == "31111001"
        assert not ctx.get("phone_candidates")


def test_telegram_no_auth_por_telefono(monkeypatch):
    from app.estate.database import get_session_factory
    from app.estate.models import Organization
    from app.services import billtrack as bt
    from app.services.canal_abonado import procesar_mensaje_entrante

    called = {"n": 0}

    def _boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("Telegram no debe consultar BillTrack por teléfono")

    monkeypatch.setattr(bt, "lookup_abonados_por_telefono", _boom)

    chat_id = "999001122"
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        assert org
        from app.estate import canal_repo as crepo
        from app.estate.models import ConversacionCanal

        for c in db.scalars(
            select(ConversacionCanal).where(ConversacionCanal.telefono == chat_id)
        ).all():
            c.estado = "cerrado"
            c.contexto_json = "{}"
            c.abonado_id = ""
        db.commit()
        conv = crepo.get_or_create_conversacion(
            db, org.id, telefono=chat_id, canal="telegram", wa_id=chat_id
        )
        conv.estado = "bot"
        conv.abonado_id = ""
        conv.contexto_json = "{}"
        db.commit()
        org_id = org.id

    with Session() as db:
        r = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=chat_id,
            texto="hola",
            canal="telegram",
            wa_id=chat_id,
            usar_llama=False,
        )
    assert called["n"] == 0
    resp = (r.get("respuesta") or "").lower()
    assert "dni" in resp or "agente" in resp
