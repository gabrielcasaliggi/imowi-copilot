"""EKO 2.7E — cortesía posterior al cierre no reemite el acknowledgement.

El hilo sigue en bot. No se cierra la conversación ni se relanza el diagnóstico.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.config as app_config
from app.services.eko_action_runtime import ActionResult
from app.services.eko_journeys import get_journey, maybe_handle_journey_turn

ACK = "Me alegra que se haya solucionado."
DIAG = "Veo una sesión de conexión activa"


def _abo():
    return SimpleNamespace(
        id="abo-27e",
        organizacion_id="org-1",
        nombre="Armando",
        dni="30111222",
        servicio="internet",
        client_number="200",
    )


def _conv():
    return SimpleNamespace(
        id="conv-27e",
        ticket_id="",
        estado="bot",
        telefono="2230000000",
        canal="whatsapp",
        abonado_id="abo-27e",
    )


def _enable(monkeypatch):
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ENABLED", True)


def _online():
    estado = SimpleNamespace(online=True, sesion=SimpleNamespace(online=True))
    return ActionResult(
        action="run_diagnostic_pppoe",
        status="success",
        data={"_estado": estado, "login_used": "INT1", "service_id": "svc-1"},
        user_message="resumen",
        correlation_id="c-27e",
        execution_path="runtime",
        reason_code=None,
    )


def _play(monkeypatch, turns: list[str]):
    _enable(monkeypatch)
    ctx: dict = {}
    conv = _conv()
    abo = _abo()
    calls: list[str] = []

    def dispatch(action, *args, **kwargs):
        calls.append(action)
        if action == "run_diagnostic_pppoe":
            return _online()
        return ActionResult(
            action=action,
            status="success",
            user_message="Factura 0001-1. Importe 1000.",
            data={"invoices": []},
            execution_path="runtime",
        )

    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", side_effect=dispatch),
        patch("app.services.eko_journeys._capability_allowed", return_value=True),
    ):
        out = []
        for texto in turns:
            before = len(calls)
            turn = maybe_handle_journey_turn(
                MagicMock(), "org-1", conv, abo, texto, canal="wa", ctx=ctx
            )
            out.append((turn, list(calls[before:]), id(ctx), conv.id, conv.estado))
    return out, ctx, conv


def test_27e_resolve_then_thanks_is_silence(monkeypatch):
    out, ctx, conv = _play(
        monkeypatch,
        ["no tengo internet", "si gracias ya se soluciono", "gracias"],
    )
    diag, ack, courtesy = out
    assert DIAG in (diag[0].user_message or "")
    assert ACK in (ack[0].user_message or "")
    assert ack[0].step == "done"
    assert get_journey(ctx).get("resolved_ack") is True
    assert courtesy[0].handled is True
    assert courtesy[0].user_message == ""
    assert courtesy[0].reason_code == "post_resolution_courtesy"
    assert courtesy[0].step == "done"
    assert courtesy[1] == []
    assert conv.estado == "bot"
    assert diag[3] == ack[3] == courtesy[3]
    assert diag[2] == ack[2] == courtesy[2]


def test_27e_ok_gracias_is_silence(monkeypatch):
    out, _, conv = _play(
        monkeypatch,
        ["no tengo internet", "ya se soluciono gracias", "ok gracias"],
    )
    assert out[2][0].user_message == ""
    assert out[2][1] == []
    assert conv.estado == "bot"
    assert "sesión de conexión activa" not in (out[2][0].user_message or "")


def test_27e_thanks_plus_invoice_continues(monkeypatch):
    out, ctx, conv = _play(
        monkeypatch,
        [
            "no tengo internet",
            "si gracias ya se soluciono",
            "gracias, quiero consultar mi factura",
        ],
    )
    turn = out[2][0]
    assert turn.user_message != ""
    assert ACK not in (turn.user_message or "")
    assert turn.journey == "billing_self_service"
    assert get_journey(ctx).get("name") == "billing_self_service"
    assert "run_diagnostic_pppoe" not in out[2][1]
    assert conv.estado == "bot"


def test_27e_internet_again_rediagnoses(monkeypatch):
    out, ctx, conv = _play(
        monkeypatch,
        [
            "no tengo internet",
            "si gracias ya se soluciono",
            "necesito ayuda con internet nuevamente",
        ],
    )
    turn, calls, *_ = out[2]
    assert calls == ["run_diagnostic_pppoe"]
    assert DIAG in (turn.user_message or "")
    assert get_journey(ctx).get("name") == "internet_sin_conectividad"
    assert conv.estado == "bot"


def test_27e_agent_is_handoff_not_silence(monkeypatch):
    out, ctx, conv = _play(
        monkeypatch,
        [
            "no tengo internet",
            "si gracias ya se soluciono",
            "quiero hablar con un agente",
        ],
    )
    turn, calls, *_ = out[2]
    assert turn.user_message != ""
    assert turn.data.get("handoff") is True
    assert turn.action == "create_ticket"
    assert turn.action_status == "needs_confirmation"
    assert "agente" in (turn.user_message or "").lower()
    assert calls == []
    assert get_journey(ctx).get("pending_confirmation") is True
    assert conv.estado == "bot"


def test_27e_courtesy_does_not_close_thread_or_dispatch(monkeypatch):
    phrases = ["gracias", "ok gracias", "muchas gracias", "perfecto gracias", "👍"]
    for phrase in phrases:
        out, _, conv = _play(
            monkeypatch,
            ["no tengo internet", "si gracias ya se soluciono", phrase],
        )
        assert out[2][0].user_message == "", phrase
        assert out[2][1] == [], phrase
        assert conv.estado == "bot"
