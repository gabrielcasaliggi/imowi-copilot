"""H27a (unitario): un diagnóstico de planta unavailable/failed no cuenta como «ya revisado» ni como doble ejecución, y el «sí» con
un diagnóstico en curso sigue el playbook en vez de «No tengo una acción pendiente de confirmar»."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.config as app_config
import app.services.eko_action_bridge as bridge
from app.services.eko_action_runtime import ActionResult
from app.services.eko_journey_observability import reset_journey_metrics, snapshot_journey_metrics
from app.services.eko_journeys import maybe_handle_journey_turn

H27A = pytest.mark.xfail(strict=True, reason="H27a: unavailable/failed cuentan como «ya revisado» y doble ejecución; el «sí» con diagnóstico en curso choca con «No tengo una acción pendiente»")
AVISO = "No pude ver el estado de tu conexión desde acá, sigamos con unos chequeos:"


def _setup(monkeypatch):
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ENABLED", True)
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_CHANNELS", frozenset())
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ORG_IDS", frozenset())
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ACTIONS", frozenset({"run_diagnostic_pppoe"}))


ABO = SimpleNamespace(id="abo-1", organizacion_id="org-1", nombre="María", dni="30111222", servicio="internet",
                      plan="100Mb", estado="activo", deuda_monto="0", linea_msisdn="", client_number="200")
CONV = SimpleNamespace(id="conv-1", ticket_id="", estado="bot", telefono="2235551234", canal="whatsapp", abonado_id="abo-1",
                       servicio_detectado="")


def _ar(status: str) -> ActionResult:
    return ActionResult(action="run_diagnostic_pppoe", status=status, reason_code="sources_unavailable", correlation_id="d",
                        execution_path="runtime")


def _turnos(monkeypatch, status: str, textos: list[str]):
    _setup(monkeypatch)
    reset_journey_metrics()
    ctx: dict = {}
    out = []
    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=_ar(status)),
    ):
        for t in textos:
            out.append(maybe_handle_journey_turn(MagicMock(), "org", CONV, ABO, t, canal="web", ctx=ctx))
    return out, ctx


@H27A
def test_planta_unavailable_avisa_una_vez_y_cede_al_playbook(monkeypatch):
    (t1, t2), ctx = _turnos(monkeypatch, "unavailable", ["No tengo internet", "No tengo internet"])
    assert not t1.handled and t1.data.get("playbook_continue") and t1.data["aviso_previo"] == AVISO
    assert not t2.handled and t2.data.get("playbook_continue") and not t2.data.get("aviso_previo")
    assert "Ya revisé" not in (t2.user_message or "")


@H27A
def test_unavailable_no_cuenta_como_doble_ejecucion(monkeypatch):
    _turnos(monkeypatch, "unavailable", ["No tengo internet", "No tengo internet", "sigue igual"])
    assert snapshot_journey_metrics()["counters"]["double_execution_detected_total"] == 0


@H27A
def test_failed_no_cuenta_como_doble_ejecucion(monkeypatch):
    _turnos(monkeypatch, "failed", ["No tengo internet", "No tengo internet"])
    assert snapshot_journey_metrics()["counters"]["double_execution_detected_total"] == 0


@H27A
def test_si_con_diagnostico_en_curso_sigue_el_playbook(monkeypatch):
    _setup(monkeypatch)
    ctx = {
        "eko_journey": {
            "name": "internet_sin_conectividad", "step": "respond", "pending_confirmation": False, "correlation_id": "c",
            "intent": "internet", "domain": "internet", "last_action": "run_diagnostic_pppoe",
            "last_action_status": "success", "last_diagnostic_result": "pppoe_session_up",
        },
        "pppoe_informado": True,
    }
    with patch("app.services.eko_journeys._login_count", return_value=1):
        t = maybe_handle_journey_turn(MagicMock(), "org", CONV, ABO, "sí", canal="web", ctx=ctx)
    assert t is not None and not t.handled and t.data.get("playbook_continue"), t
