"""Eko 2.6N-C — Test harness Runtime isolation (ACTIONS=create_ticket only).

PATH C validation: no remote hosts, no production config, synthetic DB/mocks only.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.services.eko_action_bridge as bridge
from app.config import ACTION_RUNTIME_ACTIONS as DEFAULT_ACTIONS
from app.estate import repository as repo
from app.estate.models import Abonado, ConversacionCanal, TicketEvent
from app.services.eko_action_runtime import (
    TrustedContext,
    execute_action,
    parse_llm_action_proposal,
)
from app.services.eko_ticket_proactive import map_ticket_event_type

# Default set names that must NOT be covered when ACTIONS={create_ticket}
_OTHER_DEFAULT_ACTIONS = frozenset(DEFAULT_ACTIONS) - {"create_ticket"}

assert "ticket_customer_note" in _OTHER_DEFAULT_ACTIONS
assert "show_ticket" in _OTHER_DEFAULT_ACTIONS


def _abo_ns(**kwargs):
    d = {
        "id": "abo-26nc",
        "organizacion_id": "org-1",
        "nombre": "María",
        "dni": "30127001",
        "servicio": "internet",
        "plan": "100Mb",
        "estado": "activo",
        "linea_msisdn": "2235127001",
        "client_number": "201",
    }
    d.update(kwargs)
    return SimpleNamespace(**d)


def _conv_ns(**kwargs):
    d = {
        "id": "conv-26nc",
        "ticket_id": "",
        "estado": "bot",
        "telefono": "2235127001",
        "canal": "whatsapp",
        "abonado_id": "abo-26nc",
        "servicio_detectado": "",
    }
    d.update(kwargs)
    return SimpleNamespace(**d)


def _enable_isolated(monkeypatch):
    """Rollout target: ENABLED=true, ACTIONS={create_ticket} only."""
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ACTIONS", frozenset({"create_ticket"}))


def _disable_runtime(monkeypatch):
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", False)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ACTIONS", frozenset({"create_ticket"}))


# --- TEST 1 / 5: Isolation ---


def test_26nc_isolated_actions_only_create_covered(monkeypatch):
    _enable_isolated(monkeypatch)
    assert bridge.action_runtime_covers("create_ticket") is True
    for name in sorted(_OTHER_DEFAULT_ACTIONS):
        assert bridge.action_runtime_covers(name) is False, name
    # Not in default either
    assert bridge.action_runtime_covers("update_ticket") is False
    assert bridge.action_runtime_covers("escalate_human") is False


def test_26nc_isolated_not_equal_to_default_set(monkeypatch):
    _enable_isolated(monkeypatch)
    assert bridge.ACTION_RUNTIME_ACTIONS == frozenset({"create_ticket"})
    assert bridge.ACTION_RUNTIME_ACTIONS != DEFAULT_ACTIONS
    assert len(DEFAULT_ACTIONS) > 1
    assert "ticket_customer_note" in DEFAULT_ACTIONS
    assert "ticket_customer_note" not in bridge.ACTION_RUNTIME_ACTIONS


# --- TEST 2 + 3 + 6: Full agentic path + XOR + CASI ---


def test_26nc_proposal_policy_confirmation_runtime_xor(monkeypatch):
    """LLM proposal → Policy → confirmation → Runtime once; Legacy branch 0."""
    _enable_isolated(monkeypatch)
    from app.services.canal_abonado import _ticket_via_runtime_o_legacy

    prop = parse_llm_action_proposal(
        {
            "action": "create_ticket",
            "parameters": {
                "motivo": "sin internet",
                "client_number": "HACK",
                "visible_cliente": "Sí",
            },
            "abonado_id": "fake",
        }
    )
    assert prop is not None
    assert prop.source == "llm_proposal"
    assert "client_number" not in prop.parameters
    assert "visible_cliente" not in prop.parameters

    # Without trusted confirmation → Policy blocks write
    trusted_no = TrustedContext(
        conversation_id="conv-26nc",
        organization_id="org-1",
        abonado_id="abo-26nc",
        abonado=_abo_ns(),
        conv=_conv_ns(),
        ctx={},
        db=MagicMock(),
        canal="wa",
        confirmation_received=False,
        confirmation_rejected=False,
        decision_name="test_26nc",
    )
    with patch("app.services.canal_abonado._crear_ticket_n2") as create:
        r0 = execute_action(prop, trusted_no)
    assert r0.status == "needs_confirmation"
    assert r0.policy == "NEEDS_CONFIRMATION"
    create.assert_not_called()

    # N1 XOR helper with pending + «sí» → exactly one Runtime dispatch, one writer
    ctx: dict = {
        "eko_action": {"action": "create_ticket", "status": "confirmation_pending"}
    }
    captured: list = []
    real_dispatch = bridge.dispatch_runtime

    def capturing_dispatch(*a, **kw):
        ar = real_dispatch(*a, **kw)
        captured.append(ar)
        return ar

    with (
        patch(
            "app.services.canal_abonado._crear_ticket_n2",
            return_value="TK-26NC-1",
        ) as writer,
        patch(
            "app.services.eko_action_bridge.dispatch_runtime",
            side_effect=capturing_dispatch,
        ) as disp,
        patch("app.estate.canal_repo.list_mensajes", return_value=[]),
    ):
        tid, pending = _ticket_via_runtime_o_legacy(
            MagicMock(),
            "org-1",
            _conv_ns(),
            _abo_ns(),
            "sin internet",
            ctx=ctx,
            canal="wa",
            texto="sí",
            decision_name="escape_agente",
        )
    assert pending is None
    assert tid == "TK-26NC-1"
    assert disp.call_count == 1
    assert disp.call_args.args[0] == "create_ticket"
    assert writer.call_count == 1
    assert len(captured) == 1
    assert captured[0].execution_path == "runtime"
    assert captured[0].status == "success"


def test_26nc_runtime_on_legacy_branch_zero_and_single_executor(monkeypatch):
    _enable_isolated(monkeypatch)
    from app.services.canal_abonado import _ticket_via_runtime_o_legacy

    ctx: dict = {
        "eko_action": {"action": "create_ticket", "status": "confirmation_pending"}
    }
    runtime_calls = {"n": 0}
    real_dispatch = bridge.dispatch_runtime

    def counting_dispatch(*a, **kw):
        runtime_calls["n"] += 1
        return real_dispatch(*a, **kw)

    def counting_writer(*a, **kw):
        # Solo vía executor Runtime; Legacy del helper no debe sumar otra.
        return "TK-26NC-XOR"

    with (
        patch(
            "app.services.canal_abonado._crear_ticket_n2",
            side_effect=counting_writer,
        ) as writer,
        patch(
            "app.services.eko_action_bridge.dispatch_runtime",
            side_effect=counting_dispatch,
        ),
        patch("app.estate.canal_repo.list_mensajes", return_value=[]),
    ):
        tid, pending = _ticket_via_runtime_o_legacy(
            MagicMock(),
            "org-1",
            _conv_ns(),
            _abo_ns(),
            "motivo",
            ctx=ctx,
            canal="wa",
            texto="sí",
            decision_name="create_ticket",
        )
    assert pending is None
    assert tid == "TK-26NC-XOR"
    assert runtime_calls["n"] == 1
    assert writer.call_count == 1
    assert writer.call_count == runtime_calls["n"]


# --- TEST 4: Runtime OFF ---


def test_26nc_runtime_off_legacy_one_runtime_zero(monkeypatch):
    _disable_runtime(monkeypatch)
    from app.services.canal_abonado import _ticket_via_runtime_o_legacy

    assert bridge.action_runtime_covers("create_ticket") is False
    with (
        patch(
            "app.services.canal_abonado._crear_ticket_n2",
            return_value="TK-26NC-LEG",
        ) as writer,
        patch(
            "app.services.eko_action_bridge.dispatch_runtime",
            wraps=bridge.dispatch_runtime,
        ) as disp,
    ):
        tid, pending = _ticket_via_runtime_o_legacy(
            MagicMock(),
            "org-1",
            _conv_ns(),
            _abo_ns(),
            "motivo",
            ctx={},
            canal="wa",
            texto="",
            decision_name="create_ticket",
        )
    assert tid == "TK-26NC-LEG"
    assert pending is None
    assert disp.call_count == 0
    assert writer.call_count == 1


# --- Synthetic Ticket + Event(creacion) under isolated ACTIONS ---


def test_26nc_harness_ticket_and_creacion_event(db, monkeypatch):
    _enable_isolated(monkeypatch)
    session, org_id = db
    abo = Abonado(
        organizacion_id=org_id,
        dni="30127099",
        nombre="Abo 26NC",
        telefono_e164="2235127099",
        linea_msisdn="2235127099",
        servicio="internet",
        estado="activo",
    )
    session.add(abo)
    session.commit()
    session.refresh(abo)
    conv = ConversacionCanal(
        organizacion_id=org_id,
        canal="wa",
        telefono="2235127099",
        abonado_id=abo.id,
        ticket_id="",
        estado="bot",
    )
    session.add(conv)
    session.commit()
    session.refresh(conv)

    prop = parse_llm_action_proposal(
        {"action": "create_ticket", "parameters": {"motivo": "Event 26NC"}}
    )
    assert prop is not None
    trusted = TrustedContext(
        conversation_id=conv.id,
        organization_id=org_id,
        abonado_id=abo.id,
        abonado=abo,
        conv=conv,
        ctx={},
        db=session,
        canal="wa",
        confirmation_received=True,
        confirmation_rejected=False,
        decision_name="test_26nc_event",
    )
    with patch(
        "app.services.eko_action_bridge.dispatch_runtime",
        wraps=bridge.dispatch_runtime,
    ):
        # Direct execute_action after Policy allow (confirmation trusted) —
        # same authority chain as dispatch; counts as agentic Runtime entry.
        r = execute_action(prop, trusted)
    assert r.status == "success"
    assert r.execution_path == "runtime"
    tid = r.data.get("ticket_id")
    assert tid
    events = [
        e for e in repo.list_ticket_events(session, org_id, tid) if e.tipo == "creacion"
    ]
    assert len(events) == 1
    assert events[0].visible_cliente == "Sí"
    assert map_ticket_event_type(events[0]) == "ticket.created"
    assert (
        session.query(TicketEvent)
        .filter_by(organizacion_id=org_id, ticket_id=tid, tipo="creacion")
        .count()
        == 1
    )
    # Note still not covered under isolation
    assert bridge.action_runtime_covers("ticket_customer_note") is False


def test_26nc_casi_llm_cannot_skip_policy(monkeypatch):
    _enable_isolated(monkeypatch)
    prop = parse_llm_action_proposal(
        {
            "action": "create_ticket",
            "parameters": {"motivo": "x", "confirmation": True},
        }
    )
    assert prop is not None
    assert "confirmation" not in prop.parameters
    trusted = TrustedContext(
        conversation_id="c",
        organization_id="org-1",
        abonado_id="a",
        abonado=_abo_ns(),
        conv=_conv_ns(),
        ctx={},
        db=MagicMock(),
        canal="wa",
        confirmation_received=False,
        confirmation_rejected=False,
        decision_name="casi",
    )
    with patch("app.services.canal_abonado._crear_ticket_n2") as create:
        r = execute_action(prop, trusted)
    assert r.status == "needs_confirmation"
    create.assert_not_called()
