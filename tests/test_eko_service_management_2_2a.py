"""Eko 2.2A — service_list READ (catálogo comercial)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.config as app_config
import app.services.eko_action_bridge as bridge
from app.services.eko_action_runtime import (
    ActionRequest,
    ActionResult,
    TrustedContext,
    _exec_service_list,
    bootstrap_registry,
    execute_action,
    format_service_list_message,
    is_registered,
    parse_llm_action_proposal,
    sanitize_parameters,
)
from app.services.eko_capability_contract import build_capability
from app.services.eko_journeys import detect_journey_name, get_journey, maybe_handle_journey_turn


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


def _enable(monkeypatch, *actions: str):
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ENABLED", True)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(
        bridge,
        "ACTION_RUNTIME_ACTIONS",
        frozenset(actions or ("service_list", "show_balance", "show_invoice", "open_OV")),
    )
    bootstrap_registry()


def _catalog(*rows: dict) -> dict:
    return {
        "status": "ok",
        "checked_at": "2026-09-22T12:00:00+00:00",
        "services": list(rows),
        "reason_code": None,
    }


def _svc(
    *,
    sid: str = "s1",
    tip: str = "internet",
    product: str = "Internet 600M",
    label: str = "Internet 600M",
    active: bool = True,
    line_msisdn: str | None = None,
) -> dict:
    row = {
        "id": sid,
        "type": tip,
        "label": label,
        "product": product,
        "active": active,
    }
    if line_msisdn is not None:
        row["line_msisdn"] = line_msisdn
    return row


def test_capability_service_list_registered():
    bootstrap_registry()
    assert is_registered("service_list")
    cap = build_capability("service_list")
    assert cap is not None
    assert cap.type == "READ"
    assert cap.domain == "services"
    assert cap.requires_authorization is True


def test_t01_single_account(monkeypatch):
    _enable(monkeypatch)
    cat = _catalog(_svc())

    def _disp(action, **kwargs):
        assert action == "service_list"
        return ActionResult(
            action="service_list",
            status="success",
            user_message=format_service_list_message(cat["services"]),
            data={"services": cat["services"], "count": 1},
            execution_path="runtime",
        )

    with (
        patch("app.services.eko_journeys.dispatch_runtime", side_effect=_disp),
        patch(
            "app.services.portal_services.evaluar_servicios_portal",
            side_effect=AssertionError("legacy must not run"),
        ),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "¿Qué servicios tengo?",
            canal="wa",
            ctx={},
        )
    assert t and t.journey == "service_catalog"
    assert t.action == "service_list"
    assert t.action_status == "success"
    assert "Internet 600M" in (t.user_message or "")
    assert "Activo" in (t.user_message or "")
    assert "operational" not in (t.user_message or "").lower()


def test_t02_multi_account_needs_input(monkeypatch):
    _enable(monkeypatch)
    ctx = {"phone_candidates": [{"dni": "1"}, {"dni": "2"}]}
    with (
        patch("app.services.eko_journeys.dispatch_runtime") as disp,
        patch("app.services.portal_services.evaluar_servicios_portal") as reader,
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            None,
            "¿Qué servicios tengo?",
            canal="wa",
            ctx=ctx,
        )
    assert t and t.action_status == "needs_input"
    assert t.data.get("needs_input") == "account_selection"
    disp.assert_not_called()
    reader.assert_not_called()


def test_t03_empty_client_number(monkeypatch):
    _enable(monkeypatch)
    with (
        patch("app.services.eko_journeys.dispatch_runtime") as disp,
        patch("app.services.portal_services.evaluar_servicios_portal") as reader,
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(client_number=""),
            "Mostrame mis servicios",
            canal="wa",
            ctx={},
        )
    assert t and t.action_status == "needs_input"
    assert t.reason_code == "missing_client_number"
    disp.assert_not_called()
    reader.assert_not_called()


def test_t04_ownership_immutable():
    bootstrap_registry()
    trusted = TrustedContext(
        abonado=_abo(client_number="AAAA"),
        organization_id="org",
        conversation_id="c1",
        db=MagicMock(),
    )
    req = ActionRequest(
        action="service_list",
        parameters={"client_number": "BBBB"},
        source="llm_proposal",
    )
    with patch("app.services.portal_services.evaluar_servicios_portal") as reader:
        ar = _exec_service_list(req, trusted)
    assert ar.status == "denied"
    assert ar.reason_code == "client_number_mismatch"
    reader.assert_not_called()
    # sanitize strip (bridge path)
    cleaned = sanitize_parameters({"client_number": "BBBB", "foo": 1})
    assert "client_number" not in cleaned


def test_t05_multiple_services_no_selection(monkeypatch):
    _enable(monkeypatch)
    rows = [
        _svc(sid="1", tip="internet", product="Internet 600M"),
        _svc(sid="2", tip="movil", product="IMOWI", line_msisdn="2235559999"),
        _svc(sid="3", tip="tv", product="Sensa"),
    ]
    ctx: dict = {}

    def _disp(action, **kwargs):
        return ActionResult(
            action="service_list",
            status="success",
            user_message=format_service_list_message(rows),
            data={"services": rows, "count": 3},
        )

    with patch("app.services.eko_journeys.dispatch_runtime", side_effect=_disp):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "¿Qué servicios tengo contratados?",
            canal="wa",
            ctx=ctx,
        )
    assert t and t.data.get("count") == 3
    assert len(t.data.get("services") or []) == 3
    assert not ctx.get("login_seleccionado")
    assert not get_journey(ctx).get("selected_service")


def test_t06_commercial_active_never_operational():
    msg = format_service_list_message([_svc(active=True)])
    assert "Activo" in msg
    low = msg.lower()
    assert "operational" not in low
    assert "funcionando" not in low
    assert "conectado" not in low


def test_t07_inactive_commercial():
    msg = format_service_list_message([_svc(active=False, product="Internet Radio")])
    assert "Inactivo" in msg
    assert "operational" not in msg.lower()


def test_t08_empty_catalog_honest(monkeypatch):
    _enable(monkeypatch)

    def _disp(action, **kwargs):
        return ActionResult(
            action="service_list",
            status="success",
            reason_code="empty_catalog",
            user_message=format_service_list_message([]),
            data={"services": [], "count": 0},
        )

    with patch("app.services.eko_journeys.dispatch_runtime", side_effect=_disp):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "¿Qué servicios tengo?",
            canal="wa",
            ctx={},
        )
    assert t and t.reason_code == "empty_catalog"
    low = (t.user_message or "").lower()
    assert "no encuentro servicios" in low
    assert "caído" not in low
    assert "baja" not in low


def test_t09_no_fabricated_fields(monkeypatch):
    _enable(monkeypatch)
    row = _svc()
    # Inject fake keys into catalog response — public projection must drop them
    dirty = {
        **row,
        "price": 999,
        "due_date": "2026-10-01",
        "installation_date": "2026-01-01",
        "technical_status": "operational",
        "uptime": "10d",
        "speed": 600,
    }

    def _disp(action, **kwargs):
        from app.services.eko_action_runtime import public_service_row

        clean = public_service_row(dirty)
        return ActionResult(
            action="service_list",
            status="success",
            user_message=format_service_list_message([clean]),
            data={"services": [clean], "count": 1},
        )

    with patch("app.services.eko_journeys.dispatch_runtime", side_effect=_disp):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "¿Qué servicios tengo?",
            canal="wa",
            ctx={},
        )
    svc = (t.data.get("services") or [])[0]
    for banned in (
        "price",
        "due_date",
        "installation_date",
        "technical_status",
        "uptime",
        "speed",
    ):
        assert banned not in svc


def test_t10_llm_cannot_execute_other_action():
    bootstrap_registry()
    # Proposal asking forbidden conversion is still just a proposal; execute only if registered
    req = parse_llm_action_proposal(
        {
            "action": "service_list",
            "parameters": {
                "client_number": "EVIL",
                "also_run": "create_ticket",
                "run_diagnostic_pppoe": True,
            },
        }
    )
    assert req is not None
    assert req.action == "service_list"
    assert "client_number" not in req.parameters
    # Executing create_ticket from LLM claim without confirmation stays gated
    trusted = TrustedContext(
        abonado=_abo(),
        organization_id="org",
        conversation_id="c1",
        confirmation_received=False,
    )
    ar = execute_action(
        ActionRequest(action="create_ticket", parameters={"motivo": "x"}, source="llm_proposal"),
        trusted,
    )
    assert ar.status == "needs_confirmation"
    # service_list with mismatch denied, no create_ticket side effect
    with patch("app.services.portal_services.evaluar_servicios_portal") as reader:
        ar2 = _exec_service_list(
            ActionRequest(
                action="service_list",
                parameters={"client_number": "EVIL"},
                source="llm_proposal",
            ),
            TrustedContext(abonado=_abo(client_number="GOOD"), organization_id="org", db=MagicMock()),
        )
    assert ar2.status == "denied"
    reader.assert_not_called()


def test_t11_routing_not_billing_or_connectivity():
    assert detect_journey_name("¿Qué servicios tengo?") == "service_catalog"
    assert detect_journey_name("Mostrame mis servicios") == "service_catalog"
    assert detect_journey_name("¿Qué tengo contratado?") == "service_catalog"
    assert detect_journey_name("¿Cuánto debo?") == "billing_self_service"
    assert detect_journey_name("No tengo internet") == "internet_sin_conectividad"


def test_executor_calls_portal_services():
    bootstrap_registry()
    db = MagicMock()
    trusted = TrustedContext(
        abonado=_abo(),
        organization_id="org",
        conversation_id="c1",
        db=db,
    )
    cat = _catalog(
        _svc(sid="a"),
        _svc(sid="b", tip="tv", product="Sensa", active=False),
    )
    with patch(
        "app.services.portal_services.evaluar_servicios_portal",
        return_value=cat,
    ) as reader:
        ar = _exec_service_list(ActionRequest(action="service_list"), trusted)
    reader.assert_called_once_with(db, abonado=trusted.abonado)
    assert ar.status == "success"
    assert ar.data.get("count") == 2
    assert "Activo" in ar.user_message
    assert "Inactivo" in ar.user_message
