"""Cierre amable tras pago/QR y desistimiento en espera_agente."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.canal_abonado import (
    _cerrar_consulta_resuelta,
    _cliente_desiste_o_resuelto,
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
    assert sent and "resuelto" in sent[0].lower()


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
