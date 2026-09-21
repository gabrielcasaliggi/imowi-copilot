"""Fase 5 — Agentic Customer Operations (Journey orchestration)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.config as app_config
import app.services.eko_action_bridge as bridge
from app.services.eko_action_runtime import ActionResult
from app.services.eko_journeys import (
    detect_journey_name,
    get_journey,
    maybe_handle_journey_turn,
    transition_for_result,
)


def _abo(**kwargs):
    d = {
        "id": "abo-1",
        "organizacion_id": "org-1",
        "nombre": "María",
        "dni": "30111222",
        "servicio": "internet",
        "plan": "100Mb",
        "estado": "activo",
        "deuda_monto": "1500",
        "linea_msisdn": "2235551234",
        "client_number": "200",
    }
    d.update(kwargs)
    return SimpleNamespace(**d)


def _conv(**kwargs):
    d = {
        "id": "conv-1",
        "ticket_id": "",
        "estado": "bot",
        "telefono": "2235551234",
        "canal": "whatsapp",
        "abonado_id": "abo-1",
        "servicio_detectado": "",
    }
    d.update(kwargs)
    return SimpleNamespace(**d)


def _enable_journeys(monkeypatch):
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ENABLED", True)


def _enable_runtime(monkeypatch, *actions: str):
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ACTIONS", frozenset(actions))


def _disable_runtime(monkeypatch):
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", False)


# --- Detection / flag ---


def test_5_journeys_off_returns_none(monkeypatch):
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ENABLED", False)
    ctx: dict = {}
    assert (
        maybe_handle_journey_turn(
            None, "org-1", _conv(), _abo(), "No tengo internet", canal="wa", ctx=ctx
        )
        is None
    )


def test_5_detect_connectivity_variants():
    for t in (
        "No tengo internet",
        "Estoy sin servicio",
        "No navega",
        "Se cayó Internet",
        "Internet no funciona",
    ):
        assert detect_journey_name(t) == "internet_sin_conectividad"


def test_5_detect_billing_and_ticket():
    assert detect_journey_name("¿Cuánto debo?") == "billing_consulta"
    assert detect_journey_name("quiero pagar") == "billing_consulta"
    assert detect_journey_name("estado del ticket") == "ticket_consulta"


# --- Connectivity ---


def test_5_single_internet_runs_diagnostic(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "run_diagnostic_pppoe", "request_account_selection")
    ctx: dict = {}
    estado = SimpleNamespace(online=True, sesion=SimpleNamespace(online=True))
    ar = ActionResult(
        action="run_diagnostic_pppoe",
        status="success",
        data={"_estado": estado},
        user_message="ok",
        correlation_id="c1",
        execution_path="runtime",
    )
    with (
        patch("app.services.eko_context.internet_logins_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=ar) as disp,
        patch(
            "app.services.conexion_pppoe.consultar_conexion_pppoe",
            side_effect=AssertionError("direct Radius"),
        ),
    ):
        turn = maybe_handle_journey_turn(
            MagicMock(),
            "org-1",
            _conv(),
            _abo(),
            "No tengo internet",
            canal="whatsapp",
            ctx=ctx,
        )
    assert turn is not None and turn.handled
    assert turn.journey == "internet_sin_conectividad"
    assert turn.action == "run_diagnostic_pppoe"
    assert disp.call_count == 1
    assert get_journey(ctx).get("intent") == "internet"
    assert get_journey(ctx).get("diagnostic_started") is True


def test_5_multi_internet_needs_input_zero_probes(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "request_account_selection", "run_diagnostic_pppoe")
    ctx: dict = {}
    ar = ActionResult(
        action="request_account_selection",
        status="success",
        user_message="elegí cuenta",
        correlation_id="c",
    )
    with (
        patch("app.services.eko_journeys._login_count", return_value=2),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=ar) as disp,
        patch(
            "app.services.conexion_pppoe.consultar_conexion_pppoe",
            side_effect=AssertionError("Radius"),
        ) as radius,
    ):
        turn = maybe_handle_journey_turn(
            MagicMock(),
            "org-1",
            _conv(),
            _abo(),
            "No tengo internet",
            canal="whatsapp",
            ctx=ctx,
        )
    assert turn is not None
    assert turn.step == "service_selection"
    assert get_journey(ctx).get("next_required_input") == "login"
    assert ctx.get("multi_cuenta_pendiente") is True
    radius.assert_not_called()
    assert disp.call_args.args[0] == "request_account_selection"


def test_5_selection_then_diagnostic(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "request_account_selection", "run_diagnostic_pppoe")
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "service_selection",
            "asked_selection": True,
            "next_required_input": "login",
            "intent": "internet",
            "domain": "internet",
            "correlation_id": "c",
        },
        "multi_cuenta_pendiente": True,
    }
    estado = SimpleNamespace(online=False, sesion=SimpleNamespace(online=False))
    ar = ActionResult(
        action="run_diagnostic_pppoe",
        status="success",
        data={"_estado": estado},
        correlation_id="c2",
    )
    with (
        patch("app.services.eko_journeys._login_count", return_value=2),
        patch(
            "app.services.eko_journeys._try_capture_login",
            return_value="INT123",
        ),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=ar),
    ):
        turn = maybe_handle_journey_turn(
            MagicMock(),
            "org-1",
            _conv(),
            _abo(),
            "INT123",
            canal="whatsapp",
            ctx=ctx,
        )
    assert turn is not None
    assert turn.action == "run_diagnostic_pppoe"
    assert get_journey(ctx).get("last_diagnostic_result") == "pppoe_session_down"


def test_5_pppoe_down_offers_confirm_no_ticket_yet(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "run_diagnostic_pppoe", "create_ticket")
    ctx: dict = {}
    estado = SimpleNamespace(online=False, sesion=SimpleNamespace(online=False))
    ar = ActionResult(
        action="run_diagnostic_pppoe",
        status="success",
        data={"_estado": estado},
        correlation_id="c",
    )
    with (
        patch("app.services.eko_context.internet_logins_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=ar),
        patch("app.services.canal_abonado._crear_ticket_n2") as create,
    ):
        turn = maybe_handle_journey_turn(
            MagicMock(),
            "org-1",
            _conv(),
            _abo(),
            "sin internet",
            canal="wa",
            ctx=ctx,
        )
    assert turn is not None
    assert "ticket" in turn.user_message.lower() or "agente" in turn.user_message.lower()
    assert get_journey(ctx).get("pending_confirmation") is True
    create.assert_not_called()


def test_5_confirm_yes_creates_ticket_once(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "create_ticket", "run_diagnostic_pppoe")
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "decide",
            "pending_confirmation": True,
            "last_diagnostic_result": "pppoe_session_down",
            "intent": "internet",
            "domain": "internet",
            "correlation_id": "c",
        },
        "eko_action": {"action": "create_ticket", "status": "confirmation_pending"},
    }
    with (
        patch(
            "app.services.canal_abonado._ticket_via_runtime_o_legacy",
            return_value=("T-1", None),
        ) as ticket,
        patch("app.services.canal_abonado._crear_ticket_n2") as create,
    ):
        turn = maybe_handle_journey_turn(
            MagicMock(),
            "org-1",
            _conv(),
            _abo(),
            "sí",
            canal="wa",
            ctx=ctx,
        )
    assert turn is not None
    assert turn.action_status == "success"
    assert turn.data.get("ticket_id") == "T-1"
    assert ticket.call_count == 1
    create.assert_not_called()  # only via helper


def test_5_confirm_no_no_ticket(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "create_ticket")
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "confirm_action",
            "pending_confirmation": True,
            "last_diagnostic_result": "pppoe_session_down",
            "intent": "internet",
            "domain": "internet",
            "correlation_id": "c",
        },
        "eko_action": {"action": "create_ticket", "status": "confirmation_pending"},
    }
    with patch("app.services.canal_abonado._crear_ticket_n2") as create:
        turn = maybe_handle_journey_turn(
            MagicMock(), "org-1", _conv(), _abo(), "no", canal="wa", ctx=ctx
        )
    assert turn is not None
    assert "no genero" in turn.user_message.lower() or "no" in turn.user_message.lower()
    create.assert_not_called()
    assert get_journey(ctx).get("pending_confirmation") is False


def test_5_ticket_idempotent(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "create_ticket")
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "confirm_action",
            "pending_confirmation": True,
            "last_diagnostic_result": "pppoe_session_down",
            "intent": "internet",
            "domain": "internet",
            "correlation_id": "c",
        },
        "eko_action": {"action": "create_ticket", "status": "confirmation_pending"},
    }
    with patch(
        "app.services.canal_abonado._ticket_via_runtime_o_legacy",
        return_value=("T-EXIST", None),
    ) as ticket:
        turn = maybe_handle_journey_turn(
            MagicMock(),
            "org-1",
            _conv(ticket_id="T-EXIST"),
            _abo(),
            "sí",
            canal="wa",
            ctx=ctx,
        )
    assert turn is not None
    assert ticket.call_count == 1


def test_5_runtime_unavailable_contractual_fallback(monkeypatch):
    _enable_journeys(monkeypatch)
    _disable_runtime(monkeypatch)
    ctx: dict = {}
    with (
        patch("app.services.eko_context.internet_logins_count", return_value=1),
        patch(
            "app.services.eko_journeys._legacy_pppoe_as_result",
            return_value=ActionResult(
                action="run_diagnostic_pppoe",
                status="success",
                data={"_estado": SimpleNamespace(online=True, sesion=SimpleNamespace(online=True))},
                user_message="legacy ok",
                execution_path="legacy",
            ),
        ) as legacy,
        patch("app.services.eko_journeys.dispatch_runtime", return_value=None),
    ):
        turn = maybe_handle_journey_turn(
            MagicMock(),
            "org-1",
            _conv(),
            _abo(),
            "No tengo internet",
            canal="wa",
            ctx=ctx,
        )
    assert turn is not None
    assert legacy.call_count == 1
    assert turn.data.get("execution_path") == "legacy"


def test_5_no_double_runtime_legacy(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "run_diagnostic_pppoe")
    ar = ActionResult(
        action="run_diagnostic_pppoe",
        status="success",
        data={"_estado": SimpleNamespace(online=True, sesion=SimpleNamespace(online=True))},
        execution_path="runtime",
    )
    with (
        patch("app.services.eko_context.internet_logins_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=ar),
        patch("app.services.eko_journeys._legacy_pppoe_as_result") as legacy,
    ):
        maybe_handle_journey_turn(
            MagicMock(),
            "org-1",
            _conv(),
            _abo(),
            "sin internet",
            canal="wa",
            ctx={},
        )
    legacy.assert_not_called()


def test_5_action_result_transitions():
    assert transition_for_result("needs_input") == "service_selection"
    assert transition_for_result("needs_confirmation") == "confirm_action"
    assert transition_for_result("success") == "interpret"
    assert transition_for_result("denied") == "respond"


# --- Continuity / loop ---


def test_5_intent_domain_preserved_across_turns(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "request_account_selection")
    ctx: dict = {}
    ar = ActionResult(action="request_account_selection", status="success", user_message="elige")
    with (
        patch("app.services.eko_journeys._login_count", return_value=2),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=ar),
    ):
        maybe_handle_journey_turn(
            MagicMock(), "org-1", _conv(), _abo(), "No tengo internet", canal="wa", ctx=ctx
        )
        turn2 = maybe_handle_journey_turn(
            MagicMock(), "org-1", _conv(), _abo(), "hola", canal="wa", ctx=ctx
        )
    assert get_journey(ctx).get("intent") == "internet"
    assert get_journey(ctx).get("domain") == "internet"
    assert turn2 is not None
    assert turn2.step == "service_selection"
    # no back to generic menu question
    assert "qué problema" not in (turn2.user_message or "").lower()


def test_5_no_repeat_selection_spam(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "request_account_selection")
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "service_selection",
            "asked_selection": True,
            "next_required_input": "login",
            "intent": "internet",
            "domain": "internet",
            "correlation_id": "c",
        },
        "multi_cuenta_pendiente": True,
    }
    with patch("app.services.eko_journeys._login_count", return_value=2):
        turn = maybe_handle_journey_turn(
            MagicMock(), "org-1", _conv(), _abo(), "no sé", canal="wa", ctx=ctx
        )
    assert turn is not None
    assert "Todavía necesito" in turn.user_message


# --- Domain switch ---


def test_5_connectivity_to_billing_switch(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "show_balance")
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "diagnostic",
            "intent": "internet",
            "domain": "internet",
            "correlation_id": "old",
        }
    }
    with (
        patch("app.services.eko_context.internet_logins_count", return_value=1),
        patch(
            "app.services.eko_journeys.dispatch_runtime",
            return_value=ActionResult(
                action="show_balance",
                status="success",
                user_message="Saldo 0",
                data={"amount": "0"},
            ),
        ),
    ):
        turn = maybe_handle_journey_turn(
            MagicMock(),
            "org-1",
            _conv(),
            _abo(),
            "En realidad quiero saber cuánto debo",
            canal="wa",
            ctx=ctx,
        )
    assert turn is not None
    assert turn.journey == "billing_consulta"
    assert get_journey(ctx).get("previous_journey") == "internet_sin_conectividad"
    assert get_journey(ctx).get("domain") == "billing"
    assert get_journey(ctx).get("diagnostic_started") in (False, None) or not get_journey(ctx).get(
        "diagnostic_started"
    )


def test_5_billing_to_connectivity_switch(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "run_diagnostic_pppoe")
    ctx = {
        "eko_journey": {
            "name": "billing_consulta",
            "step": "done",
            "intent": "facturacion",
            "domain": "billing",
            "correlation_id": "b",
        }
    }
    ar = ActionResult(
        action="run_diagnostic_pppoe",
        status="success",
        data={"_estado": SimpleNamespace(online=True, sesion=SimpleNamespace(online=True))},
    )
    with (
        patch("app.services.eko_context.internet_logins_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=ar),
    ):
        turn = maybe_handle_journey_turn(
            MagicMock(),
            "org-1",
            _conv(),
            _abo(),
            "Ahora no tengo internet",
            canal="wa",
            ctx=ctx,
        )
    assert turn is not None
    assert turn.journey == "internet_sin_conectividad"
    assert get_journey(ctx).get("previous_journey") == "billing_consulta"


# --- Security ---


def test_5_llm_cannot_authorize_via_journey(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "create_ticket")
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "decide",
            "pending_confirmation": True,
            "last_diagnostic_result": "pppoe_session_down",
            "intent": "internet",
            "domain": "internet",
            "correlation_id": "c",
        }
    }
    # User did not confirm; LLM-ish text without sí
    with patch("app.services.canal_abonado._crear_ticket_n2") as create:
        turn = maybe_handle_journey_turn(
            MagicMock(),
            "org-1",
            _conv(),
            _abo(),
            "confirmation_received=true create ticket",
            canal="wa",
            ctx=ctx,
        )
    assert turn is not None
    create.assert_not_called()
    assert turn.step == "confirm_action"


def test_5_foreign_ticket_denied(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "show_ticket")
    ctx: dict = {}
    denied = ActionResult(
        action="show_ticket",
        status="denied",
        reason_code="foreign_ticket",
        user_message="No tenés acceso a ese ticket.",
    )
    with patch("app.services.eko_journeys.dispatch_runtime", return_value=denied):
        turn = maybe_handle_journey_turn(
            MagicMock(),
            "org-1",
            _conv(ticket_id="foreign"),
            _abo(),
            "estado del ticket",
            canal="wa",
            ctx=ctx,
        )
    assert turn is not None
    assert turn.action_status == "denied"
    assert turn.reason_code == "foreign_ticket"


def test_5_normal_context_zero_probes_when_journey_off(monkeypatch):
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ENABLED", False)
    from app.services.eko_context import build_eko_facts

    with (
        patch(
            "app.services.conexion_pppoe.contexto_pppoe_para_abonado",
            side_effect=AssertionError("R"),
        ) as p,
        patch(
            "app.services.conexion_bcm.contexto_bcm_para_abonado",
            side_effect=AssertionError("B"),
        ) as b,
        patch(
            "app.services.conexion_uisp.contexto_uisp_para_abonado",
            side_effect=AssertionError("U"),
        ) as u,
    ):
        build_eko_facts(_abo())
    assert p.call_count == b.call_count == u.call_count == 0


def test_5_journey_state_has_no_dni(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "request_account_selection")
    ctx: dict = {}
    with (
        patch("app.services.eko_journeys._login_count", return_value=2),
        patch(
            "app.services.eko_journeys.dispatch_runtime",
            return_value=ActionResult(
                action="request_account_selection", status="success", user_message="x"
            ),
        ),
    ):
        maybe_handle_journey_turn(
            MagicMock(), "org-1", _conv(), _abo(), "sin internet", canal="wa", ctx=ctx
        )
    st = get_journey(ctx)
    assert "dni" not in st
    assert "jwt" not in st
    assert "30111222" not in str(st)


# --- Billing / ticket ---


def test_5_show_balance_uses_facts_path(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "show_balance")
    ctx: dict = {}
    with patch(
        "app.services.eko_journeys.dispatch_runtime",
        return_value=ActionResult(
            action="show_balance",
            status="success",
            user_message="Tu saldo es $0",
            data={"amount": "0", "billing_status": "live"},
        ),
    ) as disp:
        turn = maybe_handle_journey_turn(
            MagicMock(),
            "org-1",
            _conv(),
            _abo(),
            "¿Cuánto debo?",
            canal="wa",
            ctx=ctx,
        )
    assert turn is not None
    assert turn.action == "show_balance"
    assert disp.called
    assert disp.call_args.args[0] == "show_balance"


def test_5_open_ov_on_pay_intent(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "show_balance", "open_OV")

    def _disp(action, **kwargs):
        if action == "show_balance":
            return ActionResult(
                action="show_balance", status="success", user_message="Deuda $10"
            )
        return ActionResult(
            action="open_OV",
            status="success",
            user_message="https://ov.example/pagar",
            data={"url": "https://ov.example/pagar"},
        )

    with patch("app.services.eko_journeys.dispatch_runtime", side_effect=_disp):
        turn = maybe_handle_journey_turn(
            MagicMock(),
            "org-1",
            _conv(),
            _abo(),
            "quiero pagar",
            canal="wa",
            ctx={},
        )
    assert turn is not None
    assert "pagar" in turn.user_message.lower() or "http" in turn.user_message.lower()


def test_5_show_ticket_missing_id(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "show_ticket")
    turn = maybe_handle_journey_turn(
        MagicMock(),
        "org-1",
        _conv(ticket_id=""),
        _abo(),
        "estado del ticket",
        canal="wa",
        ctx={},
    )
    assert turn is not None
    assert "número" in turn.user_message.lower() or "ticket" in turn.user_message.lower()


def test_5_bcm_uisp_not_auto_invoked(monkeypatch):
    """Fase 5: tras PPPoE no dispara BCM/UISP (gap Legacy documentado)."""
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "run_diagnostic_pppoe")
    ar = ActionResult(
        action="run_diagnostic_pppoe",
        status="success",
        data={"_estado": SimpleNamespace(online=False, sesion=SimpleNamespace(online=False))},
    )
    with (
        patch("app.services.eko_context.internet_logins_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=ar),
        patch(
            "app.services.conexion_bcm.consultar_onu_bcm_mejor_esfuerzo",
            side_effect=AssertionError("BCM"),
        ) as bcm,
        patch(
            "app.services.conexion_uisp.consultar_cpe_uisp",
            side_effect=AssertionError("UISP"),
        ) as uisp,
    ):
        maybe_handle_journey_turn(
            MagicMock(),
            "org-1",
            _conv(),
            _abo(),
            "sin internet",
            canal="wa",
            ctx={},
        )
    bcm.assert_not_called()
    uisp.assert_not_called()
