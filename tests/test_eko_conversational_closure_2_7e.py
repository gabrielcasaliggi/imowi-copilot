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
OFFER = "Perfecto. ¿Necesitás algo más?"
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
    assert OFFER in (ack[0].user_message or "")
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


def _patch_close(conv_holder: dict):
    def fake_close(db, org_id, conv, canal="", **kwargs):
        conv.estado = "cerrado"
        conv_holder["calls"] = conv_holder.get("calls", 0) + 1
        conv_holder["canal"] = canal
        return {"ok": True, "modo": "cerrado", "estado": "cerrado"}

    return patch(
        "app.services.canal_abonado._cerrar_consulta_resuelta",
        side_effect=fake_close,
    )


def test_27e_r1_real_sequence_courtesy_then_explicit_close(monkeypatch):
    """Tras la oferta, «bien» sigue en silencio y «no gracias» cierra. No vuelve a connectivity."""
    _enable(monkeypatch)
    ctx: dict = {}
    conv = _conv()
    abo = _abo()
    calls: list[str] = []
    closed: dict = {"calls": 0}

    def dispatch(action, *args, **kwargs):
        calls.append(action)
        if action == "run_diagnostic_pppoe":
            return _online()
        return ActionResult(action=action, status="success", user_message="Factura", data={})

    turns = [
        "no tengo internet",
        "gracias ya se soluciono",
        "bien",
        "no gracias",
    ]
    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", side_effect=dispatch),
        patch("app.services.eko_journeys._capability_allowed", return_value=True),
        _patch_close(closed),
    ):
        out = []
        for texto in turns:
            before = len(calls)
            turn = maybe_handle_journey_turn(
                MagicMock(), "org-1", conv, abo, texto, canal="portal", ctx=ctx
            )
            out.append(
                (
                    turn,
                    list(calls[before:]),
                    conv.estado,
                    dict(get_journey(ctx)),
                )
            )

    diag, ack, bien, no_gracias = out
    assert DIAG in (diag[0].user_message or "")
    assert diag[1] == ["run_diagnostic_pppoe"]
    assert diag[2] == "bot"
    assert OFFER in (ack[0].user_message or "")
    assert ack[0].step == "done"
    assert ack[1] == []
    assert ack[2] == "bot"
    offered_at = ack[3].get("continuity_offered_at")
    assert offered_at

    turn, runtime, estado, journey = bien
    assert turn.user_message == ""
    assert turn.step == "done"
    assert runtime == []
    assert estado == "bot"
    assert "Ya revisé" not in (turn.user_message or "")
    assert turn.reason_code == "post_resolution_courtesy"
    assert journey.get("continuity_pending") is True
    assert journey.get("continuity_offered_at") == offered_at

    assert no_gracias[0].user_message == ""
    assert no_gracias[0].reason_code == "explicit_conversation_close"
    assert no_gracias[1] == []
    assert no_gracias[2] == "cerrado"
    assert "Ya revisé" not in (no_gracias[0].user_message or "")
    assert closed["calls"] == 1
    assert conv.estado == "cerrado"


def test_27e_r1_courtesy_keeps_done(monkeypatch):
    for phrase in ("bien", "ok", "perfecto", "entendido", "genial"):
        out, ctx, conv = _play(
            monkeypatch,
            ["no tengo internet", "gracias ya se soluciono", phrase],
        )
        turn, runtime, *_ = out[2]
        assert turn.user_message == "", phrase
        assert turn.step == "done", phrase
        assert get_journey(ctx).get("step") == "done", phrase
        assert runtime == [], phrase
        assert conv.estado == "bot", phrase


def test_27e_r1_explicit_close_variants(monkeypatch):
    phrases = (
        "cerra la conversacion",
        "cerrá la conversación",
        "quiero cerrar la conversación",
        "podés cerrar la conversación",
        "puede cerrar la conversación",
        "terminemos la conversación",
        "quiero terminar",
        "quiero finalizar",
        "finalizar conversación",
    )
    for phrase in phrases:
        closed: dict = {"calls": 0}
        _enable(monkeypatch)
        ctx = {
            "eko_journey": {
                "name": "internet_sin_conectividad",
                "step": "done",
                "resolved_ack": True,
                "last_diagnostic_result": "pppoe_session_up",
                "intent": "internet",
                "domain": "internet",
            },
            "pppoe_informado": True,
        }
        conv = _conv()
        with (
            patch("app.services.eko_journeys._login_count", return_value=1),
            patch("app.services.eko_journeys.dispatch_runtime", side_effect=AssertionError(phrase)),
            patch("app.services.eko_journeys._capability_allowed", return_value=True),
            _patch_close(closed),
        ):
            turn = maybe_handle_journey_turn(
                MagicMock(), "org-1", conv, _abo(), phrase, canal="portal", ctx=ctx
            )
        assert turn is not None, phrase
        assert turn.reason_code == "explicit_conversation_close", phrase
        assert turn.data.get("close_action") is True, phrase
        assert closed["calls"] == 1, phrase
        assert conv.estado == "cerrado", phrase
        assert get_journey(ctx).get("step") == "done", phrase


def test_27e_r1_negated_close_does_not_close(monkeypatch):
    out, ctx, conv = _play(
        monkeypatch,
        [
            "no tengo internet",
            "gracias ya se soluciono",
            "no quiero cerrar la conversacion porque sigo sin internet",
        ],
    )
    turn, runtime, *_ = out[2]
    assert conv.estado == "bot"
    assert turn.reason_code != "explicit_conversation_close"
    assert runtime == ["run_diagnostic_pppoe"]
    assert DIAG in (turn.user_message or "")
    assert get_journey(ctx).get("name") == "internet_sin_conectividad"


def test_27e_r1_thanks_but_still_offline_rediagnoses(monkeypatch):
    out, ctx, conv = _play(
        monkeypatch,
        [
            "no tengo internet",
            "gracias ya se soluciono",
            "gracias, pero sigo sin internet",
        ],
    )
    turn, runtime, *_ = out[2]
    assert conv.estado == "bot"
    assert runtime == ["run_diagnostic_pppoe"]
    assert DIAG in (turn.user_message or "")
    assert ACK not in (turn.user_message or "")
    assert get_journey(ctx).get("name") == "internet_sin_conectividad"


def test_27e_r1_bien_plus_internet_reenters(monkeypatch):
    out, _, conv = _play(
        monkeypatch,
        [
            "no tengo internet",
            "gracias ya se soluciono",
            "bien, necesito ayuda con internet nuevamente",
        ],
    )
    turn, runtime, *_ = out[2]
    assert conv.estado == "bot"
    assert runtime == ["run_diagnostic_pppoe"]
    assert turn.user_message != ""
    assert ACK not in (turn.user_message or "")


def test_27e_r1_ok_plus_agent_is_handoff(monkeypatch):
    out, ctx, conv = _play(
        monkeypatch,
        [
            "no tengo internet",
            "gracias ya se soluciono",
            "ok, quiero hablar con un agente",
        ],
    )
    turn, runtime, *_ = out[2]
    assert conv.estado == "bot"
    assert runtime == []
    assert turn.data.get("handoff") is True
    assert turn.action_status == "needs_confirmation"
    assert get_journey(ctx).get("pending_confirmation") is True
