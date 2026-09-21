"""Fase 6 — Conversational QA & Journey Hardening."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.config as app_config
import app.services.eko_action_bridge as bridge
from app.services.eko_action_runtime import ActionResult, get_action_state
from app.services.eko_journeys import (
    get_journey,
    maybe_handle_journey_turn,
    set_journey,
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


def _svc(login: str, locality: str = "", product: str = ""):
    return SimpleNamespace(login=login, locality=locality, product=product, label=product)


def _enable(monkeypatch, *actions: str):
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ENABLED", True)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(
        bridge,
        "ACTION_RUNTIME_ACTIONS",
        frozenset(actions or (
            "request_account_selection",
            "run_diagnostic_pppoe",
            "show_balance",
            "show_ticket",
            "open_OV",
            "create_ticket",
        )),
    )


def _pppoe(online: bool) -> ActionResult:
    return ActionResult(
        action="run_diagnostic_pppoe",
        status="success",
        data={"_estado": SimpleNamespace(online=online, sesion=SimpleNamespace(online=online))},
        correlation_id="diag",
        execution_path="runtime",
    )


def _snap(ctx: dict) -> dict:
    j = get_journey(ctx)
    return {
        "intent": j.get("intent"),
        "domain": j.get("domain"),
        "selected_service": j.get("selected_service") or ctx.get("login_seleccionado"),
        "current_step": j.get("step") or j.get("current_step"),
        "pending_input": j.get("next_required_input"),
        "pending_confirmation": j.get("pending_confirmation"),
        "last_action": j.get("last_action"),
        "name": j.get("name"),
    }


# --- C01 baseline ---


def test_c01_happy_path_single_service(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=_pppoe(True)),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "No tengo internet", canal="wa", ctx=ctx
        )
    assert t and t.handled
    assert t.journey == "internet_sin_conectividad"
    assert t.action == "run_diagnostic_pppoe"
    assert get_journey(ctx).get("last_diagnostic_result") == "pppoe_session_up"
    assert get_journey(ctx).get("pending_confirmation") is False


def test_c01_journey_completion_flags(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=_pppoe(True)),
    ):
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "sin internet", canal="wa", ctx=ctx
        )
    j = get_journey(ctx)
    assert j.get("step") == "respond"
    assert not j.get("next_required_input")
    assert not j.get("pending_confirmation")


# --- C02 pending input ---


def test_c02_pending_selection_el_de_casa(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    svcs = [_svc("INT1", "Casa Batán"), _svc("INT2", "Local Comercial")]
    ar_sel = ActionResult(
        action="request_account_selection", status="success", user_message="elegí"
    )
    with (
        patch("app.services.eko_journeys._login_count", return_value=2),
        patch(
            "app.services.canal_abonado._servicios_conectividad_abonado",
            return_value=svcs,
        ),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=ar_sel),
    ):
        t1 = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "No tengo internet", canal="wa", ctx=ctx
        )
    assert t1 and t1.step == "service_selection"
    assert _snap(ctx)["pending_input"] == "login"
    assert _snap(ctx)["intent"] == "internet"

    with (
        patch("app.services.eko_journeys._login_count", return_value=2),
        patch(
            "app.services.canal_abonado._servicios_conectividad_abonado",
            return_value=svcs,
        ),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=_pppoe(False)),
    ):
        t2 = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "El de casa", canal="wa", ctx=ctx
        )
    assert t2 and t2.action == "run_diagnostic_pppoe"
    assert ctx.get("login_seleccionado") == "INT1"
    assert _snap(ctx)["selected_service"] == "INT1"
    assert "qué problema" not in (t2.user_message or "").lower()


# --- C03 incremental ---


def test_c03_incremental_info_no_restart(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    svcs = [_svc("INT1", "Casa"), _svc("INT2", "Local")]
    with (
        patch("app.services.eko_journeys._login_count", return_value=2),
        patch(
            "app.services.canal_abonado._servicios_conectividad_abonado",
            return_value=svcs,
        ),
        patch(
            "app.services.eko_journeys.dispatch_runtime",
            return_value=ActionResult(
                action="request_account_selection", status="success", user_message="elige"
            ),
        ),
    ):
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "No tengo internet", canal="wa", ctx=ctx
        )
    with (
        patch("app.services.eko_journeys._login_count", return_value=2),
        patch(
            "app.services.canal_abonado._servicios_conectividad_abonado",
            return_value=svcs,
        ),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=_pppoe(True)),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "El de casa, desde ayer a la noche",
            canal="wa",
            ctx=ctx,
        )
    assert get_journey(ctx).get("name") == "internet_sin_conectividad"
    assert get_journey(ctx).get("intent") == "internet"
    assert ctx.get("login_seleccionado") == "INT1"
    assert t and t.action == "run_diagnostic_pppoe"


# --- C04 redundant ---


def test_c04_no_repeat_selection_question(monkeypatch):
    _enable(monkeypatch)
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "service_selection",
            "asked_selection": True,
            "next_required_input": "login",
            "intent": "internet",
            "domain": "internet",
            "selection_options": ["INT1", "INT2"],
            "correlation_id": "c",
        },
        "multi_cuenta_pendiente": True,
    }
    with patch("app.services.eko_journeys._login_count", return_value=2):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "internet de casa", canal="wa", ctx=ctx
        )
    # Without locality metadata match, stays on selection — but not full first ask
    assert t and t.step == "service_selection"
    assert "Todavía necesito" in t.user_message or "cuenta" in t.user_message.lower()


# --- C05 / C06 switch ---


def test_c05_explicit_domain_switch_no_diagnostic(monkeypatch):
    _enable(monkeypatch)
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "service_selection",
            "asked_selection": True,
            "next_required_input": "login",
            "intent": "internet",
            "domain": "internet",
            "pending_confirmation": True,
            "confirmation_correlation": "old",
            "correlation_id": "old",
        },
        "eko_action": {"action": "create_ticket", "status": "confirmation_pending"},
    }
    with patch(
        "app.services.eko_journeys.dispatch_runtime",
        return_value=ActionResult(
            action="show_balance", status="success", user_message="Saldo OK"
        ),
    ) as disp:
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "Antes decime cuánto debo",
            canal="wa",
            ctx=ctx,
        )
    assert t and t.journey == "billing_consulta"
    assert get_journey(ctx).get("pending_confirmation") is False
    assert get_action_state(ctx).get("status") == "cleared_on_domain_switch"
    assert disp.call_args.args[0] == "show_balance"
    assert all(c.args[0] != "run_diagnostic_pppoe" for c in disp.call_args_list)


def test_c06_return_to_connectivity_no_auto_diag(monkeypatch):
    _enable(monkeypatch)
    ctx = {
        "eko_journey": {
            "name": "billing_consulta",
            "step": "done",
            "intent": "facturacion",
            "domain": "billing",
            "selected_service": "INT9",
            "correlation_id": "b",
        },
        "login_seleccionado": "INT9",
    }
    with patch("app.services.eko_journeys.dispatch_runtime") as disp:
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "Bueno, ¿y el Internet?",
            canal="wa",
            ctx=ctx,
        )
    assert t and t.journey == "internet_sin_conectividad"
    assert t.data.get("no_auto_diagnostic") is True
    disp.assert_not_called()
    assert ctx.get("login_seleccionado") == "INT9"


def test_c06b_reentry_without_selected_no_auto_diag(monkeypatch):
    """Piloto: volvamos al internet tras billing sin selected_service → no re-probe."""
    _enable(monkeypatch)
    ctx = {
        "eko_journey": {
            "name": "billing_consulta",
            "step": "done",
            "intent": "facturacion",
            "domain": "billing",
            "selected_service": "",
            "last_diagnostic_result": "no_fixed_internet",
            "correlation_id": "b",
        },
        "eko_no_fixed_internet": True,
    }
    with (
        patch("app.services.eko_journeys._login_count", return_value=0),
        patch("app.services.eko_journeys.dispatch_runtime") as disp,
        patch("app.services.eko_journeys._legacy_pppoe_as_result") as leg,
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "bueno volvamos al internet",
            canal="wa",
            ctx=ctx,
        )
    assert t and t.data.get("no_auto_diagnostic") is True
    assert "no veo un servicio de Internet fijo" in (t.user_message or "")
    disp.assert_not_called()
    leg.assert_not_called()


def test_c01b_no_fixed_internet_no_probe(monkeypatch):
    """Abonado sin INT en padrón: mensaje claro, cero probes."""
    _enable(monkeypatch)
    ctx: dict = {}
    with (
        patch("app.services.eko_journeys._login_count", return_value=0),
        patch("app.services.eko_journeys.dispatch_runtime") as disp,
        patch("app.services.eko_journeys._legacy_pppoe_as_result") as leg,
    ):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "No tengo internet", canal="wa", ctx=ctx
        )
    assert t and t.data.get("no_fixed_internet") is True
    assert t.reason_code == "no_fixed_internet"
    assert "no veo un servicio de Internet fijo" in (t.user_message or "")
    assert get_journey(ctx).get("last_diagnostic_result") == "no_fixed_internet"
    disp.assert_not_called()
    leg.assert_not_called()


# --- C07 contradiction ---


def test_c07_service_contradiction_invalidates_diag(monkeypatch):
    _enable(monkeypatch)
    svcs = [_svc("INT1", "Casa"), _svc("INT2", "Local comercial")]
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "respond",
            "intent": "internet",
            "domain": "internet",
            "selected_service": "INT1",
            "diagnostic_started": True,
            "last_diagnostic_result": "pppoe_session_up",
            "selection_options": ["INT1", "INT2"],
            "correlation_id": "c",
        },
        "login_seleccionado": "INT1",
        "pppoe_informado": True,
    }
    with (
        patch("app.services.eko_journeys._login_count", return_value=2),
        patch(
            "app.services.canal_abonado._servicios_conectividad_abonado",
            return_value=svcs,
        ),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=_pppoe(False)),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "No, en realidad es el del local",
            canal="wa",
            ctx=ctx,
        )
    assert ctx.get("login_seleccionado") == "INT2"
    assert t and t.action == "run_diagnostic_pppoe"


# --- C08 ambiguity ---


def test_c08_si_without_pending_no_ticket(monkeypatch):
    _enable(monkeypatch)
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "service_selection",
            "asked_selection": True,
            "next_required_input": "login",
            "intent": "internet",
            "domain": "internet",
            "pending_confirmation": False,
            "correlation_id": "c",
        },
        "multi_cuenta_pendiente": True,
    }
    with (
        patch("app.services.eko_journeys._login_count", return_value=2),
        patch("app.services.canal_abonado._crear_ticket_n2") as create,
    ):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "sí", canal="wa", ctx=ctx
        )
    create.assert_not_called()
    assert t and t.step == "service_selection"


def test_c08_ese_el_segundo(monkeypatch):
    _enable(monkeypatch)
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "service_selection",
            "asked_selection": True,
            "next_required_input": "login",
            "intent": "internet",
            "domain": "internet",
            "selection_options": ["INTA", "INTB"],
            "correlation_id": "c",
        },
        "multi_cuenta_pendiente": True,
    }
    with (
        patch("app.services.eko_journeys._login_count", return_value=2),
        patch(
            "app.services.canal_abonado._servicios_conectividad_abonado",
            return_value=[_svc("INTA"), _svc("INTB")],
        ),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=_pppoe(True)),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "el segundo", canal="wa", ctx=ctx
        )
    assert ctx.get("login_seleccionado") == "INTB"
    assert t and t.action == "run_diagnostic_pppoe"


# --- C09 out of order ---


def test_c09_out_of_order_keeps_selection_gate(monkeypatch):
    _enable(monkeypatch)
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "service_selection",
            "asked_selection": True,
            "next_required_input": "login",
            "intent": "internet",
            "domain": "internet",
            "selection_options": ["INT1", "INT2"],
            "correlation_id": "c",
        },
        "multi_cuenta_pendiente": True,
    }
    with (
        patch("app.services.eko_journeys._login_count", return_value=2),
        patch(
            "app.services.conexion_pppoe.consultar_conexion_pppoe",
            side_effect=AssertionError("no probe"),
        ) as radius,
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "Está caído desde ayer",
            canal="wa",
            ctx=ctx,
        )
    radius.assert_not_called()
    assert t and t.step == "service_selection"


# --- C10 stale confirmation ---


def test_c10_stale_confirmation_after_billing_rejected(monkeypatch):
    _enable(monkeypatch)
    ctx = {
        "eko_journey": {
            "name": "billing_consulta",
            "step": "done",
            "intent": "facturacion",
            "domain": "billing",
            "pending_confirmation": False,
            "correlation_id": "bill",
            "previous_journey": "internet_sin_conectividad",
        },
        "eko_action": {"action": "create_ticket", "status": "confirmation_pending"},
    }
    with patch("app.services.canal_abonado._crear_ticket_n2") as create:
        # bare sí on billing — billing path, not ticket confirm
        with patch(
            "app.services.eko_journeys.dispatch_runtime",
            return_value=ActionResult(
                action="show_balance", status="success", user_message="ok"
            ),
        ):
            # detect: "sí" alone doesn't start billing; active is billing
            t = maybe_handle_journey_turn(
                MagicMock(), "org", _conv(), _abo(), "sí", canal="wa", ctx=ctx
            )
    create.assert_not_called()
    assert t is not None
    # still billing domain
    assert get_journey(ctx).get("domain") == "billing"


def test_c10_confirmation_cleared_on_switch(monkeypatch):
    _enable(monkeypatch)
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "decide",
            "pending_confirmation": True,
            "confirmation_correlation": "oldc",
            "correlation_id": "oldc",
            "intent": "internet",
            "domain": "internet",
            "last_diagnostic_result": "pppoe_session_down",
        },
        "eko_action": {"action": "create_ticket", "status": "confirmation_pending"},
    }
    with patch(
        "app.services.eko_journeys.dispatch_runtime",
        return_value=ActionResult(
            action="show_balance", status="success", user_message="saldo"
        ),
    ):
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "¿Cuánto debo?", canal="wa", ctx=ctx
        )
    assert get_journey(ctx).get("pending_confirmation") is False
    assert get_action_state(ctx).get("confirmation") == "CLEARED"


# --- C11 idempotency ---


def test_c11_duplicate_connectivity_message_no_second_diag(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    calls = []

    def _disp(action, **kwargs):
        calls.append(action)
        return _pppoe(True)

    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", side_effect=_disp),
    ):
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "No tengo internet", canal="wa", ctx=ctx
        )
        t2 = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "No tengo internet", canal="wa", ctx=ctx
        )
    assert calls.count("run_diagnostic_pppoe") == 1
    assert t2 and t2.data.get("idempotent_skip") is True


def test_c11_duplicate_ticket_attempt(monkeypatch):
    _enable(monkeypatch)
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "confirm_action",
            "pending_confirmation": True,
            "confirmation_correlation": "c",
            "correlation_id": "c",
            "intent": "internet",
            "domain": "internet",
            "last_diagnostic_result": "pppoe_session_down",
        },
        "eko_action": {"action": "create_ticket", "status": "confirmation_pending"},
    }
    with patch(
        "app.services.canal_abonado._ticket_via_runtime_o_legacy",
        return_value=("T1", None),
    ) as ticket:
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(ticket_id="T1"), _abo(), "sí", canal="wa", ctx=ctx
        )
        # second sí after done
        set_journey(ctx, step="done", pending_confirmation=False)
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(ticket_id="T1"), _abo(), "sí", canal="wa", ctx=ctx
        )
    assert ticket.call_count == 1


# --- C12 long conversation ---


def test_c12_long_mixed_conversation(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    svcs = [_svc("INT1", "Casa"), _svc("INT2", "Local")]
    snaps = []

    def turn(text, ar=None, n=2):
        with (
            patch("app.services.eko_journeys._login_count", return_value=n),
            patch(
                "app.services.canal_abonado._servicios_conectividad_abonado",
                return_value=svcs,
            ),
            patch(
                "app.services.eko_journeys.dispatch_runtime",
                return_value=ar
                or ActionResult(
                    action="request_account_selection",
                    status="success",
                    user_message="elige",
                ),
            ),
        ):
            r = maybe_handle_journey_turn(
                MagicMock(), "org", _conv(), _abo(), text, canal="wa", ctx=ctx
            )
        snaps.append(_snap(ctx))
        return r

    turn("No tengo internet")
    assert snaps[-1]["pending_input"] == "login"
    turn("El de casa", _pppoe(False))
    assert snaps[-1]["selected_service"] == "INT1"
    turn("¿Cuánto debo?", ActionResult(action="show_balance", status="success", user_message="$0"), n=1)
    assert snaps[-1]["domain"] == "billing"
    turn("estado del ticket", ActionResult(action="show_ticket", status="needs_input", user_message="pasame nro"), n=1)
    assert snaps[-1]["name"] == "ticket_consulta"
    # return connectivity
    with patch("app.services.eko_journeys.dispatch_runtime") as d:
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "Bueno, ¿y el Internet?", canal="wa", ctx=ctx
        )
        d.assert_not_called()
    assert get_journey(ctx).get("selected_service") == "INT1" or ctx.get("login_seleccionado") == "INT1"
    assert len(snaps) >= 4


# --- C13 handoff ---


def test_c13_handoff_preserves_context(monkeypatch):
    _enable(monkeypatch)
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "confirm_action",
            "pending_confirmation": True,
            "confirmation_correlation": "c",
            "correlation_id": "c",
            "selected_service": "INT1",
            "last_diagnostic_result": "pppoe_session_down",
            "intent": "internet",
            "domain": "internet",
        },
        "login_seleccionado": "INT1",
        "eko_action": {"action": "create_ticket", "status": "confirmation_pending"},
    }
    with patch(
        "app.services.canal_abonado._ticket_via_runtime_o_legacy",
        return_value=("T-H", None),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "sí", canal="wa", ctx=ctx
        )
    assert t and t.data.get("ticket_id") == "T-H"
    assert ctx.get("login_seleccionado") == "INT1"
    assert get_journey(ctx).get("last_diagnostic_result") == "pppoe_session_down"


# --- C14 / C15 errors ---


def test_c14_runtime_failed_safe_transition(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    ar = ActionResult(
        action="run_diagnostic_pppoe",
        status="failed",
        reason_code="boom",
        user_message="falló",
    )
    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=ar),
        patch("app.services.eko_journeys._legacy_pppoe_as_result") as legacy,
    ):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "sin internet", canal="wa", ctx=ctx
        )
    legacy.assert_not_called()
    assert t and t.action_status == "failed"
    assert "falló" in t.user_message.lower() or "error" in t.user_message.lower() or t.user_message


def test_c14_runtime_unavailable_no_double(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    ar = ActionResult(
        action="run_diagnostic_pppoe",
        status="unavailable",
        user_message="no disponible",
    )
    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=ar),
        patch("app.services.eko_journeys._legacy_pppoe_as_result") as legacy,
    ):
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "sin internet", canal="wa", ctx=ctx
        )
    legacy.assert_not_called()


def test_c15_capability_gap_message(monkeypatch):
    _enable(monkeypatch, "show_balance")  # no pppoe
    ctx: dict = {}
    with patch("app.services.eko_journeys._login_count", return_value=1):
        # still registered in contract but if we mock _capability_allowed
        with patch("app.services.eko_journeys._capability_allowed", return_value=False):
            t = maybe_handle_journey_turn(
                MagicMock(), "org", _conv(), _abo(), "sin internet", canal="wa", ctx=ctx
            )
    assert t and t.data.get("gap") == "run_diagnostic_pppoe"


# --- Security ---


def test_c20_llm_text_no_authority(monkeypatch):
    _enable(monkeypatch)
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "respond",
            "intent": "internet",
            "domain": "internet",
            "pending_confirmation": False,
            "correlation_id": "c",
            "last_diagnostic_result": "pppoe_session_up",
        },
        "pppoe_informado": True,
    }
    with patch("app.services.canal_abonado._crear_ticket_n2") as create:
        maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "crear_ticket confirmado diagnóstico correcto",
            canal="wa",
            ctx=ctx,
        )
    create.assert_not_called()
    assert get_journey(ctx).get("pending_confirmation") is False


def test_c23_billing_no_pppoe_contamination(monkeypatch):
    _enable(monkeypatch)
    ctx = {
        "eko_journey": {
            "name": "billing_consulta",
            "step": "done",
            "intent": "facturacion",
            "domain": "billing",
            "correlation_id": "b",
        }
    }
    with patch(
        "app.services.eko_journeys.dispatch_runtime",
        return_value=ActionResult(action="show_balance", status="success", user_message="ok"),
    ) as disp:
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "mi saldo", canal="wa", ctx=ctx
        )
    assert all(c.args[0] != "run_diagnostic_pppoe" for c in disp.call_args_list)


def test_c37_no_pii_in_journey_state(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=_pppoe(True)),
    ):
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "sin internet", canal="wa", ctx=ctx
        )
    blob = str(get_journey(ctx))
    assert "30111222" not in blob
    assert "jwt" not in blob.lower()
    assert "password" not in blob.lower()


def test_c21_context_battery_after_each_turn(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    svcs = [_svc("INT1", "Casa"), _svc("INT2", "Local")]
    sequence = []

    def go(text, ar, n=2):
        with (
            patch("app.services.eko_journeys._login_count", return_value=n),
            patch(
                "app.services.canal_abonado._servicios_conectividad_abonado",
                return_value=svcs,
            ),
            patch("app.services.eko_journeys.dispatch_runtime", return_value=ar),
        ):
            maybe_handle_journey_turn(
                MagicMock(), "org", _conv(), _abo(), text, canal="wa", ctx=ctx
            )
        sequence.append(_snap(ctx))

    go(
        "No tengo internet",
        ActionResult(action="request_account_selection", status="success", user_message="e"),
    )
    assert sequence[-1]["intent"] == "internet"
    go("El de casa", _pppoe(True))
    assert sequence[-1]["selected_service"] == "INT1"
    go(
        "¿Cuánto debo?",
        ActionResult(action="show_balance", status="success", user_message="$"),
        n=1,
    )
    assert sequence[-1]["domain"] == "billing"
    assert sequence[-1]["pending_confirmation"] is False
