"""Eko 2.2D — installation status Discovery + honest unavailable.

CAPABILITY = UNAVAILABLE (no structured installation/agenda source).
Tests assert honest unavailable — no fabricated installation data.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.config as app_config
import app.services.eko_action_bridge as bridge
from app.services.eko_action_runtime import (
    ActionRequest,
    ActionResult,
    TrustedContext,
    bootstrap_registry,
    execute_action,
    sanitize_parameters,
)
from app.services.eko_journeys import (
    apply_service_ref,
    detect_journey_name,
    maybe_handle_journey_turn,
)
from app.services.eko_service_selection import ServiceRef


def _abo(**kwargs):
    d = {
        "id": "abo-1",
        "organizacion_id": "org-1",
        "nombre": "Ana",
        "dni": "30111222",
        "client_number": "18099",
        "deuda_monto": "0",
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
    }
    d.update(kwargs)
    return SimpleNamespace(**d)


def _enable(monkeypatch):
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ENABLED", True)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(
        bridge,
        "ACTION_RUNTIME_ACTIONS",
        frozenset(
            {
                "installation_status",
                "service_list",
                "run_diagnostic_pppoe",
                "show_balance",
                "show_ticket",
            }
        ),
    )
    bootstrap_registry()


def test_t01_routing_installation_intent():
    assert detect_journey_name("¿Cuándo me instalan?") == "installation_status"
    assert detect_journey_name("¿Cómo está mi instalación?") == "installation_status"
    assert detect_journey_name("¿Tengo turno de instalación?") == "installation_status"
    assert detect_journey_name("¿Cuándo viene el técnico?") == "installation_status"


def test_t02_honest_unavailable_no_invented_fields(monkeypatch):
    _enable(monkeypatch)
    t = maybe_handle_journey_turn(
        MagicMock(),
        "org",
        _conv(),
        _abo(),
        "¿Cuándo me instalan?",
        canal="wa",
        ctx={},
    )
    assert t is not None
    assert t.journey == "installation_status"
    assert t.action == "installation_status"
    assert t.action_status == "unavailable"
    assert t.reason_code == "source_unavailable"
    assert t.data.get("capability") == "unavailable"
    assert t.data.get("honest_unavailable") == "installation_status"
    for k in (
        "installation_id",
        "status",
        "scheduled_at",
        "visit_at",
        "technician",
        "ticket_id",
    ):
        assert t.data.get(k) is None
    assert "mañana" not in (t.user_message or "").lower()
    assert "programad" not in (t.user_message or "").lower() or "no tengo" in (
        t.user_message or ""
    ).lower()


def test_t03_runtime_executor_unavailable(monkeypatch):
    _enable(monkeypatch)
    ar = execute_action(
        ActionRequest(action="installation_status"),
        TrustedContext(abonado=_abo(), organization_id="org", db=MagicMock()),
    )
    assert ar.status == "unavailable"
    assert ar.reason_code == "source_unavailable"
    assert ar.data.get("scheduled_at") is None
    assert ar.data.get("status") is None


def test_t04_llm_fake_status_ignored(monkeypatch):
    _enable(monkeypatch)
    cleaned = sanitize_parameters(
        {
            "status": "scheduled",
            "scheduled_at": "2026-09-23",
            "technician": "Juan",
            "client_number": "EVIL",
        }
    )
    assert "client_number" not in cleaned
    ar = execute_action(
        ActionRequest(
            action="installation_status",
            parameters={
                "status": "in_progress",
                "scheduled_at": "mañana",
                "technician": "LLM",
            },
            source="llm_proposal",
        ),
        TrustedContext(abonado=_abo(), organization_id="org", db=MagicMock()),
    )
    assert ar.status == "unavailable"
    assert ar.data.get("status") is None
    assert ar.data.get("scheduled_at") is None
    assert ar.data.get("technician") is None


def test_t05_ticket_support_not_auto_installation():
    """Pregunta de ticket no se convierte en installation_status."""
    assert detect_journey_name("¿Cómo va el ticket?") == "ticket_consulta"
    assert detect_journey_name("estado del ticket") == "ticket_consulta"


def test_t06_rag_procedural_not_factual(monkeypatch):
    """Respuesta no afirma instalación programada (RAG no es fuente)."""
    _enable(monkeypatch)
    t = maybe_handle_journey_turn(
        MagicMock(),
        "org",
        _conv(),
        _abo(),
        "¿Ya está programada la instalación?",
        canal="wa",
        ctx={},
    )
    assert t and t.action_status == "unavailable"
    low = (t.user_message or "").lower()
    assert "no tengo información verificable" in low or "no tengo" in low
    assert "está programada para" not in low
    assert "el técnico va" not in low


def test_t07_no_effect(monkeypatch):
    _enable(monkeypatch)
    with patch("app.services.eko_journeys.dispatch_runtime") as disp:
        disp.return_value = ActionResult(
            action="installation_status",
            status="unavailable",
            reason_code="source_unavailable",
            user_message="sin dato",
            data={"capability": "unavailable"},
        )
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "¿Cuándo me instalan?",
            canal="wa",
            ctx={},
        )
    assert t and t.action == "installation_status"
    assert all(
        (c.args[0] if c.args else "")
        not in ("create_ticket", "open_OV", "show_invoice", "run_diagnostic_pppoe")
        for c in disp.call_args_list
    )


def test_t08_casi_llm_cannot_authorize_status(monkeypatch):
    _enable(monkeypatch)
    ar = execute_action(
        ActionRequest(
            action="installation_status",
            parameters={"status": "completed", "installation_id": "fake"},
            source="llm_proposal",
        ),
        TrustedContext(abonado=_abo(), organization_id="org"),
    )
    assert ar.status == "unavailable"
    assert ar.data.get("installation_id") is None


def test_t09_selected_service_not_used_as_installation(monkeypatch):
    """selected_service_ref no inventa asociación a instalación inexistente."""
    _enable(monkeypatch)
    ctx: dict = {}
    apply_service_ref(
        ctx,
        ServiceRef(
            service_id="s1",
            login="INT1",
            service_type="internet",
            client_number="18099",
        ),
    )
    t = maybe_handle_journey_turn(
        MagicMock(),
        "org",
        _conv(),
        _abo(),
        "estado de mi instalación",
        canal="wa",
        ctx=ctx,
    )
    assert t and t.action_status == "unavailable"
    assert t.data.get("status") is None


def test_t10_regression_service_list(monkeypatch):
    _enable(monkeypatch)
    assert detect_journey_name("¿Qué servicios tengo?") == "service_catalog"


def test_t11_regression_connectivity(monkeypatch):
    assert detect_journey_name("No tengo internet") == "internet_sin_conectividad"


def test_t12_regression_billing(monkeypatch):
    assert detect_journey_name("¿Cuánto debo?") == "billing_self_service"


def test_t13_no_client_number_still_honest(monkeypatch):
    """Sin CN: sigue unavailable (no hay fuente que consultar)."""
    _enable(monkeypatch)
    t = maybe_handle_journey_turn(
        MagicMock(),
        "org",
        _conv(),
        _abo(client_number=""),
        "¿Cuándo me instalan?",
        canal="wa",
        ctx={},
    )
    assert t and t.action_status == "unavailable"
    assert t.reason_code == "source_unavailable"
