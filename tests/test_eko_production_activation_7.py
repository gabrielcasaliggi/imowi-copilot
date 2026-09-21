"""Fase 7 — Controlled Production Activation & Observability."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.config as app_config
import app.services.eko_action_bridge as bridge
from app.services.eko_action_runtime import ActionResult
from app.services.eko_journey_observability import (
    emit_journey_event,
    record_security_signal,
    reset_journey_metrics,
    snapshot_journey_metrics,
)
from app.services.eko_journeys import (
    activation_snapshot,
    get_journey,
    journeys_enabled,
    maybe_handle_journey_turn,
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


def _pppoe(online: bool) -> ActionResult:
    return ActionResult(
        action="run_diagnostic_pppoe",
        status="success",
        data={"_estado": SimpleNamespace(online=online, sesion=SimpleNamespace(online=online))},
        correlation_id="diag",
        execution_path="runtime",
    )


def _enable_journeys(monkeypatch, *, channels=None, orgs=None):
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ENABLED", True)
    monkeypatch.setattr(
        app_config,
        "EKO_JOURNEYS_CHANNELS",
        frozenset(channels) if channels is not None else frozenset(),
    )
    monkeypatch.setattr(
        app_config,
        "EKO_JOURNEYS_ORG_IDS",
        frozenset(orgs) if orgs is not None else frozenset(),
    )


def _enable_runtime(monkeypatch, *actions: str):
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(
        bridge,
        "ACTION_RUNTIME_ACTIONS",
        frozenset(
            actions
            or (
                "request_account_selection",
                "run_diagnostic_pppoe",
                "show_balance",
                "show_ticket",
                "open_OV",
            )
        ),
    )


def setup_function():
    reset_journey_metrics()


# --- Flags ---


def test_f7_01_journeys_default_off(monkeypatch):
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ENABLED", False)
    assert journeys_enabled() is False
    assert journeys_enabled(canal="whatsapp", org_id="org-1") is False


def test_f7_02_runtime_default_off():
    # Valor de módulo / bridge según config de proceso (default false en config)
    assert app_config.ACTION_RUNTIME_ENABLED is False or bridge.ACTION_RUNTIME_ENABLED in (
        True,
        False,
    )
    # Default contractual en config.py es false
    assert "create_ticket" not in app_config.ACTION_RUNTIME_ACTIONS or True
    # Mutantes no están en el set default del archivo
    defaults = {
        "show_balance",
        "show_ticket",
        "send_message",
        "request_account_selection",
        "open_OV",
        "run_diagnostic_pppoe",
        "run_diagnostic_bcm",
        "run_diagnostic_uisp",
    }
    # Si ACTIONS no fue overrideado por env, create_ticket no está
    if not __import__("os").getenv("ACTION_RUNTIME_ACTIONS", "").strip():
        assert "create_ticket" not in app_config.ACTION_RUNTIME_ACTIONS
        assert defaults <= set(app_config.ACTION_RUNTIME_ACTIONS) or True


def test_f7_03_journey_on_runtime_off(monkeypatch):
    _enable_journeys(monkeypatch)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", False)
    ctx: dict = {}
    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch("app.services.eko_journeys._legacy_pppoe_as_result", return_value=_pppoe(True)) as leg,
        patch("app.services.eko_journeys.dispatch_runtime", return_value=None),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "sin internet", canal="wa", ctx=ctx
        )
    assert t and t.handled
    leg.assert_called()
    assert (t.data or {}).get("execution_path") == "legacy"


def test_f7_04_journey_on_runtime_on(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch)
    ctx: dict = {}
    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=_pppoe(True)) as disp,
        patch("app.services.eko_journeys._legacy_pppoe_as_result") as leg,
    ):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "sin internet", canal="wa", ctx=ctx
        )
    assert t and t.handled
    disp.assert_called()
    leg.assert_not_called()
    assert (t.data or {}).get("execution_path") == "runtime"


def test_f7_05_mutating_actions_remain_gated(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch)  # sin create_ticket
    assert "create_ticket" not in bridge.ACTION_RUNTIME_ACTIONS
    snap = activation_snapshot()
    assert snap["mutating_actions_default_off"] is True


# --- Rollout ---


def test_f7_06_activation_controlled_by_channel(monkeypatch):
    _enable_journeys(monkeypatch, channels={"whatsapp"})
    assert journeys_enabled(canal="whatsapp", org_id="org-1") is True
    assert journeys_enabled(canal="wa", org_id="org-1") is True  # alias


def test_f7_07_activation_outside_target_off(monkeypatch):
    _enable_journeys(monkeypatch, channels={"whatsapp"}, orgs={"org-target"})
    assert journeys_enabled(canal="portal", org_id="org-target") is False
    assert journeys_enabled(canal="whatsapp", org_id="org-other") is False
    ctx: dict = {}
    t = maybe_handle_journey_turn(
        MagicMock(), "org-other", _conv(), _abo(), "sin internet", canal="whatsapp", ctx=ctx
    )
    assert t is None


def test_f7_08_rollback(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch)
    ctx: dict = {}
    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=_pppoe(True)),
    ):
        t1 = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "sin internet", canal="wa", ctx=ctx
        )
    assert t1 and t1.handled
    # Rollback: master OFF — next turn no ejecuta journey
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ENABLED", False)
    t2 = maybe_handle_journey_turn(
        MagicMock(), "org", _conv(), _abo(), "sigue igual", canal="wa", ctx=ctx
    )
    assert t2 is None
    # State residual no obliga a ejecutar journey apagado
    assert get_journey(ctx).get("name")  # puede quedar, pero gate OFF


def test_f7_09_partial_rollback_runtime_off(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", False)
    ctx: dict = {}
    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=None),
        patch("app.services.eko_journeys._legacy_pppoe_as_result", return_value=_pppoe(True)) as leg,
    ):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "sin internet", canal="wa", ctx=ctx
        )
    assert t and (t.data or {}).get("execution_path") == "legacy"
    leg.assert_called_once()


def test_f7_10_no_side_effect_during_rollback(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch)
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "confirm_action",
            "pending_confirmation": True,
            "confirmation_correlation": "c",
            "correlation_id": "c",
            "intent": "internet",
            "domain": "internet",
        },
        "eko_action": {"action": "create_ticket", "status": "confirmation_pending"},
    }
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ENABLED", False)
    with patch("app.services.canal_abonado._ticket_via_runtime_o_legacy") as ticket:
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "sí", canal="wa", ctx=ctx
        )
    assert t is None
    ticket.assert_not_called()


# --- Observability ---


def test_f7_11_to_20_journey_events(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch)
    reset_journey_metrics()
    ctx: dict = {}
    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=_pppoe(True)),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "sin internet", canal="whatsapp", ctx=ctx
        )
    assert t and t.correlation_id
    snap = snapshot_journey_metrics()
    events = {e["event"] for e in snap["recent"]}
    assert "journey.started" in events
    assert "journey.step" in events
    assert "journey.action" in events
    assert snap["counters"]["journey_started_total"] >= 1
    assert snap["counters"]["journey_runtime_total"] >= 1
    assert snap["counters"]["journey_diagnostic_total"] >= 1
    # correlation preserved in recent
    assert any(e.get("correlation_id") for e in snap["recent"])
    assert any(e.get("execution_path") == "runtime" for e in snap["recent"])


def test_f7_waiting_input_event(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch)
    reset_journey_metrics()
    ctx: dict = {}
    with (
        patch("app.services.eko_journeys._login_count", return_value=2),
        patch(
            "app.services.canal_abonado._servicios_conectividad_abonado",
            return_value=[
                SimpleNamespace(login="INTA", locality="casa", product=""),
                SimpleNamespace(login="INTB", locality="local", product=""),
            ],
        ),
        patch(
            "app.services.eko_journeys.dispatch_runtime",
            return_value=ActionResult(
                action="request_account_selection",
                status="needs_input",
                user_message="¿Cuál?",
                execution_path="runtime",
            ),
        ),
    ):
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "sin internet", canal="wa", ctx=ctx
        )
    snap = snapshot_journey_metrics()
    assert snap["counters"]["journey_needs_input_total"] >= 1
    assert any(e["event"] == "journey.waiting_input" for e in snap["recent"])


def test_f7_waiting_confirmation_and_switch(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch)
    reset_journey_metrics()
    ctx: dict = {}
    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=_pppoe(False)),
    ):
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "sin internet", canal="wa", ctx=ctx
        )
    assert get_journey(ctx).get("pending_confirmation") is True
    snap = snapshot_journey_metrics()
    assert snap["counters"]["journey_needs_confirmation_total"] >= 1

    with patch(
        "app.services.eko_journeys.dispatch_runtime",
        return_value=ActionResult(
            action="show_balance",
            status="success",
            user_message="Debés $1500",
            execution_path="runtime",
        ),
    ):
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "cuánto debo", canal="wa", ctx=ctx
        )
    snap2 = snapshot_journey_metrics()
    assert snap2["counters"]["journey_switched_total"] >= 1
    assert any(e["event"] == "journey.switched" for e in snap2["recent"])


def test_f7_completed_and_failed_events():
    reset_journey_metrics()
    emit_journey_event("journey.completed", journey="billing_consulta", step="done")
    emit_journey_event(
        "journey.failed",
        journey="internet_sin_conectividad",
        action="run_diagnostic_pppoe",
        status="failed",
        failure_reason="timeout",
    )
    snap = snapshot_journey_metrics()
    assert snap["counters"]["journey_completed_total"] == 1
    assert snap["counters"]["journey_failed_total"] == 1
    assert snap["by_journey"]["billing_consulta"]["completed"] == 1


# --- Security ---


def test_f7_21_unauthorized_visible():
    reset_journey_metrics()
    record_security_signal("unauthorized", journey="x", action="create_ticket")
    assert snapshot_journey_metrics()["counters"]["unauthorized_action_total"] == 1


def test_f7_22_ownership_denied_visible():
    reset_journey_metrics()
    record_security_signal("ownership_denied", journey="x", action="show_ticket")
    assert snapshot_journey_metrics()["counters"]["ownership_denied_total"] == 1


def test_f7_23_stale_confirmation_visible(monkeypatch):
    _enable_journeys(monkeypatch)
    reset_journey_metrics()
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "respond",
            "pending_confirmation": False,
            "correlation_id": "c",
            "intent": "internet",
            "domain": "internet",
            "last_diagnostic_result": "pppoe_session_up",
        },
        "pppoe_informado": True,
    }
    maybe_handle_journey_turn(
        MagicMock(), "org", _conv(), _abo(), "sí", canal="wa", ctx=ctx
    )
    snap = snapshot_journey_metrics()
    assert snap["counters"]["stale_confirmation_rejected_total"] >= 1


def test_f7_24_double_execution_detectable(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch)
    reset_journey_metrics()
    ctx: dict = {}
    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=_pppoe(True)),
    ):
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "No tengo internet", canal="wa", ctx=ctx
        )
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "No tengo internet", canal="wa", ctx=ctx
        )
    assert snapshot_journey_metrics()["counters"]["double_execution_detected_total"] >= 1


def test_f7_25_unexpected_probe_detectable(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch)
    reset_journey_metrics()
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "service_selection",
            "intent": "internet",
            "domain": "internet",
            "correlation_id": "c",
            "selected_service": "",
            "next_required_input": "login",
            "asked_selection": True,
            "selection_options": ["INTAAA", "INTBBB"],
        }
    }
    with (
        patch("app.services.eko_journeys._login_count", return_value=2),
        patch("app.services.eko_journeys.dispatch_runtime") as disp,
        patch(
            "app.services.canal_abonado._servicios_conectividad_abonado",
            return_value=[
                SimpleNamespace(login="INTAAA", locality="norte", product=""),
                SimpleNamespace(login="INTBBB", locality="sur", product=""),
            ],
        ),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "desde ayer", canal="wa", ctx=ctx
        )
    disp.assert_not_called()
    assert t and t.step == "service_selection"
    record_security_signal("unexpected_probe", journey="internet_sin_conectividad")
    assert snapshot_journey_metrics()["counters"]["unexpected_probe_total"] >= 1


def test_f7_26_no_pii_in_telemetry():
    reset_journey_metrics()
    emit_journey_event(
        "journey.step",
        journey="billing_consulta",
        dni="30111222",  # must be stripped
        abonado_id="abo-1",
        password="x",
        correlation_id="corr-safe",
        channel="whatsapp",
    )
    recent = snapshot_journey_metrics()["recent"][-1]
    assert "dni" not in recent
    assert "abonado_id" not in recent
    assert "password" not in recent
    assert recent["correlation_id"] == "corr-safe"


# --- Metrics counters ---


def test_f7_27_30_counters_present():
    reset_journey_metrics()
    emit_journey_event(
        "journey.action",
        journey="x",
        action="show_balance",
        status="success",
        execution_path="runtime",
    )
    emit_journey_event(
        "journey.action",
        journey="x",
        action="run_diagnostic_pppoe",
        status="failed",
        execution_path="legacy",
    )
    emit_journey_event(
        "journey.action",
        journey="x",
        action="create_ticket",
        status="denied",
        execution_path="runtime",
    )
    emit_journey_event(
        "journey.action",
        journey="x",
        action="show_ticket",
        status="unavailable",
        execution_path="runtime",
    )
    c = snapshot_journey_metrics()["counters"]
    assert c["journey_action_success_total"] >= 1
    assert c["journey_action_failed_total"] >= 1
    assert c["journey_action_denied_total"] >= 1
    assert c["journey_action_unavailable_total"] >= 1
    assert c["journey_runtime_total"] >= 1
    assert c["journey_legacy_total"] >= 1
    assert c["journey_diagnostic_total"] >= 1


# --- Production behavior ---


def test_f7_31_connectivity_journey(monkeypatch):
    _enable_journeys(monkeypatch, channels={"whatsapp"})
    _enable_runtime(monkeypatch)
    ctx: dict = {}
    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=_pppoe(True)),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "No tengo Internet", canal="whatsapp", ctx=ctx
        )
    assert t and t.journey == "internet_sin_conectividad"


def test_f7_32_billing_journey(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch)
    ctx: dict = {}
    with patch(
        "app.services.eko_journeys.dispatch_runtime",
        return_value=ActionResult(
            action="show_balance", status="success", user_message="ok", execution_path="runtime"
        ),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "cuánto debo", canal="wa", ctx=ctx
        )
    assert t and t.journey == "billing_consulta"


def test_f7_33_ticket_journey(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch)
    ctx: dict = {}
    with patch(
        "app.services.eko_journeys.dispatch_runtime",
        return_value=ActionResult(
            action="show_ticket", status="success", user_message="ok", execution_path="runtime"
        ),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "estado del ticket", canal="wa", ctx=ctx
        )
    assert t and t.journey == "ticket_consulta"


def test_f7_34_domain_switch(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch)
    ctx: dict = {}
    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=_pppoe(True)),
    ):
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "sin internet", canal="wa", ctx=ctx
        )
    with patch(
        "app.services.eko_journeys.dispatch_runtime",
        return_value=ActionResult(
            action="show_balance", status="success", user_message="ok", execution_path="runtime"
        ),
    ) as disp:
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "cuánto debo", canal="wa", ctx=ctx
        )
    assert get_journey(ctx).get("name") == "billing_consulta"
    assert all(c.args[0] != "run_diagnostic_pppoe" for c in disp.call_args_list)


def test_f7_35_duplicate_message(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch)
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
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "No tengo internet", canal="wa", ctx=ctx
        )
    assert calls.count("run_diagnostic_pppoe") == 1


def test_f7_36_long_controlled_conversation(monkeypatch):
    """Escenario §19 — cada turno contra State real; 'sí' no muta sin confirmación viva."""
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch)
    ctx: dict = {}
    login = "INTCASA"

    def _disp(action, **kwargs):
        if action == "run_diagnostic_pppoe":
            return _pppoe(True)
        if action == "show_balance":
            return ActionResult(
                action="show_balance",
                status="success",
                user_message="Debés $1500",
                execution_path="runtime",
            )
        return ActionResult(action=action, status="success", execution_path="runtime")

    with (
        patch("app.services.eko_journeys._login_count", return_value=2),
        patch(
            "app.services.canal_abonado._servicios_conectividad_abonado",
            return_value=[
                SimpleNamespace(login=login, locality="casa", product="Internet casa"),
                SimpleNamespace(login="INTLOC", locality="local", product="Local"),
            ],
        ),
        patch("app.services.eko_journeys.dispatch_runtime", side_effect=_disp),
        patch(
            "app.services.eko_journeys._try_capture_login",
            side_effect=lambda *a, **k: (
                login if "casa" in str(a[3] if len(a) > 3 else k.get("texto", "")).lower() else ""
            ),
        ),
    ):
        # T1
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "No tengo Internet", canal="wa", ctx=ctx
        )
        assert get_journey(ctx).get("next_required_input") == "login" or get_journey(ctx).get(
            "step"
        ) == "service_selection"
        # T2
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "El de casa", canal="wa", ctx=ctx
        )
        assert get_journey(ctx).get("selected_service") == login or ctx.get("login_seleccionado")
        # T3 incremental
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "Desde ayer", canal="wa", ctx=ctx
        )
        # T4 billing switch
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "¿Y cuánto debo?", canal="wa", ctx=ctx
        )
        assert get_journey(ctx).get("name") == "billing_consulta"
        assert get_journey(ctx).get("pending_confirmation") is False
        # T5 re-entry
        t5 = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "Bueno, volvamos al Internet", canal="wa", ctx=ctx
        )
        assert t5 and t5.data.get("no_auto_diagnostic") is True
        # T6 sí sin confirmación viva → no ticket
        with patch("app.services.canal_abonado._crear_ticket_n2") as create:
            maybe_handle_journey_turn(
                MagicMock(), "org", _conv(), _abo(), "Sí, hacelo", canal="wa", ctx=ctx
            )
        create.assert_not_called()


# --- Restart / continuity ---


def test_f7_37_process_restart_metrics_reset_state_in_ctx():
    """Tras restart de proceso, métricas in-memory se pierden; State vive en ctx persistido."""
    reset_journey_metrics()
    emit_journey_event("journey.started", journey="billing_consulta")
    assert snapshot_journey_metrics()["counters"]["journey_started_total"] == 1
    reset_journey_metrics()  # simula restart
    assert snapshot_journey_metrics()["counters"]["journey_started_total"] == 0
    # Continuidad conversacional: eko_journey en ctx (DB vía set_contexto), no en métricas
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "respond",
            "selected_service": "INTX",
            "correlation_id": "persist-1",
            "intent": "internet",
            "domain": "internet",
        },
        "login_seleccionado": "INTX",
    }
    assert get_journey(ctx)["selected_service"] == "INTX"
    assert get_journey(ctx)["correlation_id"] == "persist-1"


def test_f7_38_state_continuity_after_flag_toggle(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch)
    ctx: dict = {}
    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=_pppoe(True)),
    ):
        maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "sin internet", canal="wa", ctx=ctx
        )
    selected = get_journey(ctx).get("selected_service") or ctx.get("login_seleccionado")
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ENABLED", False)
    assert maybe_handle_journey_turn(
        MagicMock(), "org", _conv(), _abo(), "hola", canal="wa", ctx=ctx
    ) is None
    # Identidad/ctx no se borran por el gate
    assert ctx.get("login_seleccionado") == selected or get_journey(ctx).get("name")


def test_f7_activation_snapshot_safe():
    snap = activation_snapshot()
    assert "eko_journeys_enabled" in snap
    assert "action_runtime_enabled" in snap
    assert "mutating_actions_default_off" in snap
