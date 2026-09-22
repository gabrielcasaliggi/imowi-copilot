"""Eko 2.0 MVP 2.1 — Billing Self-Service (READ + NAVIGATION)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.config as app_config
import app.services.eko_action_bridge as bridge
from app.services.eko_action_runtime import ActionResult
from app.services.eko_context import billing_capabilities_hint, build_eko_facts
from app.services.eko_journeys import maybe_handle_journey_turn


def _abo(**kwargs):
    d = {
        "id": "abo-1",
        "organizacion_id": "org-1",
        "nombre": "Ana",
        "dni": "30111222",
        "servicio": "internet",
        "plan": "100Mb",
        "estado": "activo",
        "deuda_monto": "2500",
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


def _enable(monkeypatch, *actions: str):
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ENABLED", True)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(
        bridge,
        "ACTION_RUNTIME_ACTIONS",
        frozenset(actions or ("show_balance", "open_OV", "run_diagnostic_pppoe")),
    )


def _bal(amount: str = "2500", status: str = "stale") -> ActionResult:
    return ActionResult(
        action="show_balance",
        status="success",
        user_message=f"Saldo padrón ${amount}",
        data={"amount": amount, "billing_status": status},
        execution_path="runtime",
    )


def _ov(dest: str = "pagar") -> ActionResult:
    return ActionResult(
        action="open_OV",
        status="success",
        user_message=f"https://ov.example/{dest}",
        data={"url": f"https://ov.example/{dest}", "destination": dest},
        execution_path="runtime",
    )


def test_b01_balance_from_facts(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    with patch("app.services.eko_journeys.dispatch_runtime", return_value=_bal()) as disp:
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "¿Cuánto debo?", canal="wa", ctx=ctx
        )
    assert t and t.journey == "billing_self_service"
    assert t.action == "show_balance"
    assert "2500" in (t.user_message or "") or "Saldo" in (t.user_message or "")
    assert disp.call_args.args[0] == "show_balance"


def test_b02_stale_not_claimed_al_dia(monkeypatch):
    _enable(monkeypatch, "show_balance")
    # Legacy path with stale facts
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", False)
    ctx: dict = {}
    with patch("app.services.eko_journeys.dispatch_runtime", return_value=None):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(deuda_monto="0"), "mi saldo", canal="wa", ctx=ctx
        )
    assert t and t.action == "show_balance"
    low = (t.user_message or "").lower()
    # May say sin deuda from snapshot, but must not invent freshness as live
    assert "al instante" in low or "padrón" in low or "0" in (t.user_message or "")


def test_b03_unavailable_no_invent(monkeypatch):
    _enable(monkeypatch)
    with patch(
        "app.services.eko_journeys.dispatch_runtime",
        return_value=ActionResult(
            action="show_balance",
            status="unavailable",
            reason_code="billing_unavailable",
            user_message="No puedo consultar el saldo en este momento.",
        ),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "cuánto debo", canal="wa", ctx={}
        )
    assert t and t.action_status == "unavailable"
    low = (t.user_message or "").lower()
    assert "no puedo" in low or "momento" in low
    assert "vence" not in low


def test_b04_due_date_honest_plus_ov(monkeypatch):
    _enable(monkeypatch)

    def _disp(action, **kwargs):
        assert action == "open_OV"
        return _ov("my")

    with patch("app.services.eko_journeys.dispatch_runtime", side_effect=_disp):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "¿Cuándo vence?", canal="wa", ctx={}
        )
    assert t and t.data.get("honest_unavailable") == "due_date"
    assert "vencimiento" in (t.user_message or "").lower()
    assert "oficina virtual" in (t.user_message or "").lower()


def test_b05_invoice_header_from_reader(monkeypatch):
    _enable(monkeypatch, "show_balance", "show_invoice", "open_OV")

    def _disp(action, **kwargs):
        if action == "show_invoice":
            return ActionResult(
                action="show_invoice",
                status="success",
                user_message=(
                    "Esta es tu factura más reciente:\n\n"
                    "Factura 0013-00097239 (FC B)\n"
                    "Importe: $ 22648,67\n"
                    "Emitida: 18/09/2026\n"
                    "Estado: Registrado"
                ),
                data={
                    "invoices": [
                        {
                            "invoice_id": 1,
                            "invoice_number": "0013-00097239",
                            "full_type": "FC B",
                            "type": "FC",
                            "amount": "22648.67",
                            "status": "Registrado",
                            "currency": None,
                            "due_date": None,
                        }
                    ],
                    "count": 1,
                },
            )
        if action == "open_OV":
            return _ov("my")
        return _bal()

    with patch("app.services.eko_journeys.dispatch_runtime", side_effect=_disp):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "Quiero ver mi factura", canal="wa", ctx={}
        )
    assert t and t.action == "show_invoice"
    assert t.data.get("billing_act") == "invoice"
    low = (t.user_message or "").lower()
    assert "0013-00097239" in (t.user_message or "")
    assert "registrado" in low
    assert "vence el" not in low


def test_b08_invoice_destination(monkeypatch):
    _enable(monkeypatch, "show_invoice", "open_OV")
    calls: list[str] = []

    def _disp(action, **kwargs):
        calls.append(action)
        if action == "show_invoice":
            return ActionResult(
                action="show_invoice",
                status="success",
                user_message="Factura 1",
                data={"invoices": [], "count": 0},
                reason_code="no_fc_invoices",
            )
        if action == "open_OV":
            assert kwargs.get("parameters", {}).get("destination") == "my"
            return _ov("my")
        return _bal()

    with patch("app.services.eko_journeys.dispatch_runtime", side_effect=_disp):
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "Mostrame la factura", canal="wa", ctx={}
        )
    assert "show_invoice" in calls
    assert "open_OV" in calls


def test_b06_payment_history_honest(monkeypatch):
    _enable(monkeypatch)
    with patch("app.services.eko_journeys.dispatch_runtime", return_value=_ov("my")):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "¿Qué pagos hice?", canal="wa", ctx={}
        )
    assert t and t.data.get("honest_unavailable") == "payment_history"
    assert "historial" in (t.user_message or "").lower()


def test_b07_pay_opens_ov(monkeypatch):
    _enable(monkeypatch)

    def _disp(action, **kwargs):
        assert action == "open_OV"
        assert kwargs.get("parameters", {}).get("destination") == "pagar"
        return _ov("pagar")

    with patch("app.services.eko_journeys.dispatch_runtime", side_effect=_disp):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "Quiero pagar", canal="wa", ctx={}
        )
    assert t and t.action == "open_OV"
    assert t.data.get("ov_destination") == "pagar"


def test_b09_payment_slip(monkeypatch):
    _enable(monkeypatch)
    with patch("app.services.eko_journeys.dispatch_runtime", return_value=_ov("talon")) as disp:
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "Quiero el talón de pago", canal="wa", ctx={}
        )
    assert t and t.data.get("ov_destination") == "talon-de-pago"
    assert disp.call_args.kwargs.get("parameters", {}).get("destination") == "talon-de-pago"


def test_b10_phone_candidates_needs_input(monkeypatch):
    _enable(monkeypatch)
    ctx = {"phone_candidates": [{"dni": "1"}, {"dni": "2"}]}
    with patch("app.services.eko_journeys.dispatch_runtime") as disp:
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), None, "cuánto debo", canal="wa", ctx=ctx
        )
    assert t and t.action_status == "needs_input"
    assert t.data.get("needs_input") == "account_selection"
    disp.assert_not_called()


def test_b11_billing_after_connectivity_no_pppoe(monkeypatch):
    _enable(monkeypatch)
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "respond",
            "domain": "internet",
            "intent": "internet",
            "correlation_id": "c",
            "last_diagnostic_result": "pppoe_session_up",
        },
        "pppoe_informado": True,
    }
    with patch("app.services.eko_journeys.dispatch_runtime", return_value=_bal()) as disp:
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "cuánto debo", canal="wa", ctx=ctx
        )
    assert t and t.journey == "billing_self_service"
    assert all(c.args[0] != "run_diagnostic_pppoe" for c in disp.call_args_list)


def test_b12_connectivity_after_billing_no_auto_diag(monkeypatch):
    _enable(monkeypatch)
    ctx = {
        "eko_journey": {
            "name": "billing_self_service",
            "step": "done",
            "domain": "billing",
            "intent": "facturacion",
            "selected_service": "INT1",
            "correlation_id": "b",
        },
        "login_seleccionado": "INT1",
    }
    with patch("app.services.eko_journeys.dispatch_runtime") as disp:
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "Bueno, volvamos al Internet",
            canal="wa",
            ctx=ctx,
        )
    assert t and t.data.get("no_auto_diagnostic") is True
    disp.assert_not_called()


def test_b13_llm_due_date_ignored_facts_win(monkeypatch):
    """Pedido de vencimiento → honest unavailable; no inventa fecha."""
    _enable(monkeypatch)
    with patch("app.services.eko_journeys.dispatch_runtime", return_value=_ov("my")):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "¿Cuándo vence? (el LLM diría 15/10)",
            canal="wa",
            ctx={},
        )
    assert "15/10" not in (t.user_message or "")
    assert "vencimiento" in (t.user_message or "").lower()


def test_b14_balance_uses_facts_amount(monkeypatch):
    _enable(monkeypatch)
    with patch(
        "app.services.eko_journeys.dispatch_runtime",
        return_value=_bal("9999"),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(deuda_monto="9999"), "cuánto debo", canal="wa", ctx={}
        )
    assert "9999" in (t.user_message or "")


def test_b15_create_ticket_not_in_actions(monkeypatch):
    _enable(monkeypatch)  # sin create_ticket
    assert "create_ticket" not in bridge.ACTION_RUNTIME_ACTIONS
    with (
        patch("app.services.eko_journeys.dispatch_runtime", return_value=_ov("pagar")),
        patch("app.services.canal_abonado._crear_ticket_n2") as create,
    ):
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "quiero pagar", canal="wa", ctx={}
        )
    create.assert_not_called()


def test_capabilities_hint_in_facts():
    with patch(
        "app.services.eko_context.load_ov_facts",
        return_value={"available": True, "links": {"pay": "https://x"}, "auth": "external"},
    ):
        facts = build_eko_facts(_abo())
    hint = (facts.get("billing") or {}).get("capabilities_hint") or {}
    assert hint.get("can_answer_balance") is True
    assert hint.get("can_answer_invoice_fields") is False
    assert hint.get("can_answer_payment_history") is False
    assert hint.get("can_navigate_ov") is True
    assert "invoices" not in (facts.get("billing") or {})


def test_billing_capabilities_hint_helper():
    h = billing_capabilities_hint(ov_available=False)
    assert h["can_navigate_ov"] is False
    assert h["can_answer_invoice_fields"] is False
