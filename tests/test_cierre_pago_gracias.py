"""Cierre amable tras pago/QR y desistimiento en espera_agente."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.canal_abonado import (
    _cerrar_consulta_resuelta,
    _cliente_desiste_o_resuelto,
    _es_consulta_medios_pago_publico,
    _responder_espera_agente,
)
from app.services.diagnostico_n1 import _cierra_consulta_facturacion


def test_cierra_consulta_tras_gracias_perfecto():
    assert _cierra_consulta_facturacion("Sí, perfecto, muchas gracias.") is True
    assert _cierra_consulta_facturacion("Bueno, perfecto, muchas gracias.") is True
    assert _cierra_consulta_facturacion("gracias") is True
    assert _cierra_consulta_facturacion("sigue el problema de la factura") is False


def test_desiste_cuando_ya_esta_solucionado():
    assert (
        _cliente_desiste_o_resuelto("no, ya está todo solucionado, no necesito más nada")
        is True
    )
    assert _cliente_desiste_o_resuelto("y la factura?") is False
    # Whisper / confusión: no cerrar
    assert _cliente_desiste_o_resuelto("no entiendo nada") is False
    assert _cliente_desiste_o_resuelto("no entiendo nada de lo que me decís") is False
    # Queja real de servicio (audio WA) — no es cierre
    assert (
        _cliente_desiste_o_resuelto(
            "no me da nada, no puedo ser que nunca da nada, este internet"
        )
        is False
    )
    from app.services.canal_abonado import _elige_pago_o_tecnico

    assert (
        _elige_pago_o_tecnico(
            "no me da nada, no puedo ser que nunca da nada, este internet"
        )
        == "tecnico"
    )


def test_elige_ya_lo_pague_sigue_tecnico():
    from app.services.canal_abonado import _elige_pago_o_tecnico

    assert _elige_pago_o_tecnico("ya lo pague") == "tecnico"
    assert _elige_pago_o_tecnico("ya lo pagué") == "tecnico"
    assert _elige_pago_o_tecnico("quiero pagar") == "pago"
    assert _elige_pago_o_tecnico("no entiendo nada") is None


def test_espera_agente_cierra_si_resuelto(monkeypatch):
    conv = SimpleNamespace(
        id="c1",
        ticket_id="IBOT-1027",
        estado="espera_agente",
        canal="whatsapp",
        telefono="5491",
        wa_id="5491",
    )
    db = MagicMock()
    sent: list[str] = []

    monkeypatch.setattr(
        "app.services.canal_abonado._enviar_respuesta",
        lambda *_a, **_k: sent.append(_k.get("texto") or (_a[3] if len(_a) > 3 else "")),
    )
    monkeypatch.setattr(
        "app.services.canal_abonado.enviar_encuesta_cierre",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "app.services.canal_abonado._append_evidencia_ticket",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "app.services.canal_abonado.crepo.get_contexto",
        lambda _c: {},
    )

    # _enviar_respuesta(db, org_id, conv, resp, ...)
    def _fake_enviar(db, org_id, conv, resp, **_k):
        sent.append(resp)

    monkeypatch.setattr("app.services.canal_abonado._enviar_respuesta", _fake_enviar)

    out = _responder_espera_agente(
        db,
        "org",
        conv,
        "no, ya está todo solucionado, no necesito más nada",
        canal="whatsapp",
    )
    assert out["modo"] == "cerrado"
    assert conv.estado == "cerrado"
    assert sent and "de nada" in sent[0].lower()
    assert "lindo día" in sent[0].lower() or "lindo dia" in sent[0].lower()


def test_mensaje_cierre_calido():
    from app.services.canal_abonado import _mensaje_cierre_calido

    con = _mensaje_cierre_calido("Jorge")
    assert "De nada Jorge" in con
    assert "no dudes en escribirme" in con
    assert "lindo día" in con.lower()
    sin = _mensaje_cierre_calido("")
    assert sin.startswith("De nada.")
    assert "no dudes en escribirme" in sin


def test_cerrar_consulta_resuelta_helper(monkeypatch):
    conv = SimpleNamespace(
        id="c2",
        ticket_id="",
        estado="bot",
        canal="whatsapp",
        telefono="5491",
        wa_id="5491",
    )
    sent: list[str] = []
    monkeypatch.setattr(
        "app.services.canal_abonado._enviar_respuesta",
        lambda db, org_id, conv, resp, **_k: sent.append(resp),
    )
    monkeypatch.setattr(
        "app.services.canal_abonado.enviar_encuesta_cierre",
        lambda *_a, **_k: None,
    )
    out = _cerrar_consulta_resuelta(
        MagicMock(),
        "org",
        conv,
        canal="whatsapp",
        mensaje="De nada. ¡Buen día!",
    )
    assert out["modo"] == "cerrado"
    assert conv.estado == "cerrado"
    assert "De nada" in sent[0]


def test_consulta_medios_pago_publico():
    assert _es_consulta_medios_pago_publico(
        "Me cortaron el servicio por falta de pago, como pago?"
    )
    assert _es_consulta_medios_pago_publico("quiero pagar la factura")
    assert not _es_consulta_medios_pago_publico("no me anda el wifi")


def test_cliente_informa_pago_en_aviso_deuda():
    from app.services.canal_abonado import _cliente_informa_pago, _mensaje_informar_pago_n1

    assert _cliente_informa_pago("Hola quiero avisar que pague recien")
    assert _cliente_informa_pago("no por eso queria avisar que pague recien")
    assert not _cliente_informa_pago("quiero pagar la factura")
    msg_gen = _mensaje_informar_pago_n1(seguir_tecnico=False).lower()
    assert "ov.batan.coop" in msg_gen
    assert "al instante" in msg_gen or "instante" in msg_gen
    assert "aviso-de-pago" in msg_gen
    assert "no hace falta avisar" not in msg_gen

    msg_ext = _mensaje_informar_pago_n1(
        "pague por rapipago", seguir_tecnico=True
    ).lower()
    assert "aviso-de-pago" in msg_ext
    assert "rapipago" in msg_ext or "externo" in msg_ext
    assert "seguimos" in msg_ext

    msg_ov = _mensaje_informar_pago_n1("pague por la oficina virtual").lower()
    assert "al instante" in msg_ov or "instante" in msg_ov
    assert "no hace falta" in msg_ov

    from app.services.eco_voice import mensaje_informar_pago_n1

    msg_rad = mensaje_informar_pago_n1(
        "", nombre="Jorge", conectado_radius=True
    ).lower()
    assert "activa" in msg_rad
    assert "conectad" in msg_rad
    assert "cerrad" in msg_rad or "algo más" in msg_rad


def test_espera_agente_responde_como_pago(monkeypatch):
    conv = SimpleNamespace(
        id="c-pago",
        ticket_id="",
        estado="espera_agente",
        canal="web",
        telefono="guest1",
        wa_id="guest1",
    )
    sent: list[str] = []
    ctx: dict = {"visitante": True, "invitado": True}

    monkeypatch.setattr(
        "app.services.canal_abonado._enviar_respuesta",
        lambda db, org_id, conv, resp, **_k: sent.append(resp),
    )
    monkeypatch.setattr(
        "app.services.canal_abonado.crepo.get_contexto",
        lambda _c: ctx,
    )
    monkeypatch.setattr(
        "app.services.canal_abonado.crepo.set_contexto",
        lambda _c, new_ctx: ctx.update(new_ctx),
    )

    out = _responder_espera_agente(
        MagicMock(),
        "org",
        conv,
        "Me cortaron el servicio por falta de pago, como pago?",
        canal="web",
    )
    assert out["modo"] == "espera_agente"
    assert out.get("faq_pago") is True
    assert sent
    low = sent[0].lower()
    assert "ov.batan.coop" in low
    assert "fiserv" in low or "qr" in low
    assert "ya está derivado" not in low
    assert ctx.get("faq_pago_enviado") is True


def test_whatsapp_audio_dni_ilegible_repregunta_no_deriva():
    """Audio mal transcrito tras pedir DNI: repreguntar, no derivar de golpe."""
    from sqlalchemy import select

    from app.estate import canal_repo as crepo
    from app.estate.database import get_session_factory
    from app.estate.models import ConversacionCanal, Organization
    from app.services.canal_abonado import procesar_mensaje_entrante

    tel = "5492235599001"
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        assert org
        for c in db.scalars(
            select(ConversacionCanal).where(ConversacionCanal.telefono.contains(tel[-10:]))
        ).all():
            c.estado = "cerrado"
            c.contexto_json = "{}"
            c.ticket_id = ""
            c.abonado_id = ""
        db.commit()
        conv = crepo.get_or_create_conversacion(
            db, org.id, telefono=tel, canal="whatsapp", wa_id=tel
        )
        conv.estado = "bot"
        conv.abonado_id = ""
        conv.contexto_json = "{}"
        db.commit()
        org_id = org.id

    with Session() as db:
        r1 = procesar_mensaje_entrante(
            db, org_id, telefono=tel, texto="Hola", canal="whatsapp", usar_llama=False
        )
        assert r1.get("modo") == "bot"
        assert "dni" in (r1.get("respuesta") or "").lower()
        r2 = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto="Se me llone, el 28.15.",
            canal="whatsapp",
            usar_llama=False,
            entrada_audio=True,
        )
    resp = (r2.get("respuesta") or "").lower()
    assert r2.get("modo") == "bot"
    assert r2.get("estado") == "bot"
    assert "escrito" in resp or "números" in resp or "numeros" in resp
    assert "no identifiqué" not in resp
    assert "derivo" not in resp
