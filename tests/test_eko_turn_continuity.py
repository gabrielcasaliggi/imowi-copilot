"""Continuidad transversal: un journey resuelto no reejecuta su última operación."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.config as app_config
from app.services.eko_action_runtime import ActionResult
from app.services.eko_journeys import get_journey, maybe_handle_journey_turn

SALDO = "No figuran deudas pendientes (saldo 0 pesos)."
DIAG = "Veo una sesión de conexión activa"
ACK = "Me alegra que se haya solucionado."


def _enable(monkeypatch):
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ENABLED", True)


def _abo():
    return SimpleNamespace(
        id="abo-cont",
        organizacion_id="org-1",
        nombre="Armando",
        dni="30111222",
        servicio="internet",
        client_number="200",
    )


def _conv():
    return SimpleNamespace(
        id="conv-cont",
        ticket_id="",
        estado="bot",
        telefono="2230000000",
        canal="portal",
        abonado_id="abo-cont",
    )


def _online():
    estado = SimpleNamespace(online=True, sesion=SimpleNamespace(online=True))
    return ActionResult(
        action="run_diagnostic_pppoe",
        status="success",
        data={"_estado": estado, "login_used": "INT1", "service_id": "svc-1"},
        user_message="resumen",
        correlation_id="c-cont",
        execution_path="runtime",
    )


def _result(action: str, message: str):
    return ActionResult(
        action=action,
        status="success",
        user_message=message,
        data={},
        execution_path="runtime",
    )


def _play(monkeypatch, turns: list[str]):
    _enable(monkeypatch)
    ctx: dict = {}
    conv = _conv()
    calls: list[str] = []

    def dispatch(action, *args, **kwargs):
        calls.append(action)
        if action == "run_diagnostic_pppoe":
            return _online()
        if action == "show_balance":
            return _result(action, SALDO)
        if action == "show_invoice":
            return _result(action, "Factura 0001-1.")
        if action == "open_OV":
            return _result(action, "Para pagar, usá la Oficina Virtual.")
        return _result(action, action)

    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", side_effect=dispatch),
        patch("app.services.eko_journeys._capability_allowed", return_value=True),
    ):
        out = []
        for texto in turns:
            before = len(calls)
            turn = maybe_handle_journey_turn(
                MagicMock(), "org-1", conv, _abo(), texto, canal="portal", ctx=ctx
            )
            out.append((turn, list(calls[before:]), conv.estado))
    return out, ctx, conv


def test_billing_courtesy_after_balance_is_silence(monkeypatch):
    out, ctx, conv = _play(
        monkeypatch,
        ["si mi deuda", "perfecto, gracias entonces"],
    )
    balance, courtesy = out
    assert SALDO in (balance[0].user_message or "")
    assert balance[1] == ["show_balance"]
    assert courtesy[0].user_message == ""
    assert courtesy[0].reason_code == "post_resolution_hold"
    assert courtesy[1] == []
    assert courtesy[2] == "bot"
    assert get_journey(ctx).get("step") == "done"
    assert get_journey(ctx).get("name") == "billing_self_service"
    assert conv.estado == "bot"


def test_billing_how_to_pay_is_pay_not_balance(monkeypatch):
    out, _, conv = _play(monkeypatch, ["si mi deuda", "¿cómo pago?"])
    turn, calls, estado = out[1]
    assert turn.data.get("billing_act") == "pay"
    assert calls == ["open_OV"]
    assert "show_balance" not in calls
    assert SALDO not in (turn.user_message or "")
    assert estado == "bot"
    assert conv.estado == "bot"


def test_billing_invoice_after_balance(monkeypatch):
    out, ctx, _ = _play(monkeypatch, ["si mi deuda", "quiero ver mi factura"])
    turn, calls, _estado = out[1]
    assert "show_invoice" in calls
    assert "show_balance" not in calls
    assert "Factura" in (turn.user_message or "")
    assert SALDO not in (turn.user_message or "")
    assert get_journey(ctx).get("name") == "billing_self_service"


def test_billing_then_internet_switches_domain(monkeypatch):
    out, ctx, conv = _play(monkeypatch, ["si mi deuda", "no tengo internet"])
    turn, calls, estado = out[1]
    assert "show_balance" not in calls
    assert turn.journey == "internet_sin_conectividad"
    assert get_journey(ctx).get("name") == "internet_sin_conectividad"
    assert turn.user_message != ""
    assert estado == "bot"
    assert conv.estado == "bot"


def test_connectivity_thanks_stays_silent(monkeypatch):
    out, ctx, conv = _play(
        monkeypatch,
        ["no tengo internet", "ya se soluciono", "gracias"],
    )
    diag, ack, courtesy = out
    assert DIAG in (diag[0].user_message or "")
    assert diag[1] == ["run_diagnostic_pppoe"]
    assert ACK in (ack[0].user_message or "")
    assert ack[0].step == "done"
    assert courtesy[0].user_message == ""
    assert courtesy[1] == []
    assert courtesy[2] == "bot"
    assert get_journey(ctx).get("step") == "done"
    assert conv.estado == "bot"


def test_connectivity_then_debt_opens_billing(monkeypatch):
    out, ctx, conv = _play(
        monkeypatch,
        ["no tengo internet", "ya se soluciono", "ahora quiero consultar mi deuda"],
    )
    turn, calls, estado = out[2]
    assert calls == ["show_balance"]
    assert SALDO in (turn.user_message or "")
    assert get_journey(ctx).get("name") == "billing_self_service"
    assert estado == "bot"
    assert conv.estado == "bot"


def test_explicit_close_after_resolved_billing(monkeypatch):
    closed = {"n": 0}

    def fake_close(db, org_id, conv, canal="", **kwargs):
        conv.estado = "cerrado"
        closed["n"] += 1
        return {"ok": True, "modo": "cerrado"}

    _enable(monkeypatch)
    ctx: dict = {}
    conv = _conv()
    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch(
            "app.services.eko_journeys.dispatch_runtime",
            return_value=_result("show_balance", SALDO),
        ),
        patch("app.services.eko_journeys._capability_allowed", return_value=True),
        patch("app.services.canal_abonado._cerrar_consulta_resuelta", side_effect=fake_close),
    ):
        maybe_handle_journey_turn(
            MagicMock(), "org-1", conv, _abo(), "si mi deuda", canal="portal", ctx=ctx
        )
        turn = maybe_handle_journey_turn(
            MagicMock(),
            "org-1",
            conv,
            _abo(),
            "cerra la conversacion",
            canal="portal",
            ctx=ctx,
        )
    assert turn.reason_code == "explicit_conversation_close"
    assert turn.data.get("close_action") is True
    assert turn.user_message == ""
    assert closed["n"] == 1
    assert conv.estado == "cerrado"


def test_handoff_after_resolved_billing_does_not_replay(monkeypatch):
    out, ctx, conv = _play(
        monkeypatch,
        ["si mi deuda", "quiero hablar con una persona"],
    )
    turn, calls, estado = out[1]
    assert calls == []
    assert turn.data.get("handoff") is True
    assert turn.action == "create_ticket"
    assert turn.action_status == "needs_confirmation"
    assert SALDO not in (turn.user_message or "")
    assert "agente" in (turn.user_message or "").lower()
    assert get_journey(ctx).get("pending_confirmation") is True
    assert estado == "bot"
    assert conv.estado == "bot"


def test_service_selection_still_continues(monkeypatch):
    _enable(monkeypatch)
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "service_selection",
            "next_required_input": "login",
            "asked_selection": True,
            "intent": "internet",
            "domain": "internet",
        }
    }
    with (
        patch("app.services.eko_journeys._login_count", return_value=2),
        patch(
            "app.services.eko_handoff_continuity.should_ask_service_selection",
            return_value=True,
        ),
        patch(
            "app.services.eko_journeys.dispatch_runtime",
            side_effect=AssertionError("no debe diagnosticar"),
        ),
    ):
        turn = maybe_handle_journey_turn(
            MagicMock(), "org-1", _conv(), _abo(), "el segundo", canal="portal", ctx=ctx
        )
    assert turn is not None
    assert turn.user_message != ""
    assert turn.reason_code not in ("post_resolution_hold", "post_resolution_courtesy")
    assert turn.step != "done"
    assert any(w in (turn.user_message or "").lower() for w in ("cuenta", "servicio"))


def test_unrecognized_text_after_balance_is_silence(monkeypatch):
    out, ctx, conv = _play(monkeypatch, ["si mi deuda", "asdf qwerty"])
    turn, calls, estado = out[1]
    assert turn.user_message == ""
    assert calls == []
    assert get_journey(ctx).get("step") == "done"
    assert estado == "bot"
    assert conv.estado == "bot"
