"""Eko 2.7D — Incident & Customer Experience (journey continuity).

Asserts behavior (service ref, state, actions, ticket_id, XOR, ownership),
not fragile response-string equality.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.config as app_config
import app.services.eko_action_bridge as bridge
from app.estate import repository as repo
from app.estate.models import Abonado, ConversacionCanal, TicketEvent
from app.services.eko_action_runtime import (
    ActionResult,
    TrustedContext,
    execute_action,
    parse_llm_action_proposal,
)
from app.services.eko_journeys import (
    _wants_incident_followup,
    _wants_ticket_customer_note,
    apply_service_ref,
    detect_journey_name,
    get_journey,
    maybe_handle_journey_turn,
)
from app.services.eko_service_selection import ServiceRef
from tests.conftest import add_ticket


def _abo(**kwargs):
    d = {
        "id": "abo-27d",
        "organizacion_id": "org-1",
        "nombre": "María",
        "dni": "30127001",
        "servicio": "internet",
        "plan": "100Mb",
        "estado": "activo",
        "linea_msisdn": "2235127001",
        "client_number": "27001",
    }
    d.update(kwargs)
    return SimpleNamespace(**d)


def _conv(**kwargs):
    d = {
        "id": "conv-27d",
        "ticket_id": "",
        "estado": "bot",
        "telefono": "2235127001",
        "canal": "whatsapp",
        "abonado_id": "abo-27d",
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


def _pppoe_ar(*, login: str = "INT27001", service_id: str = "svc-27001", online: bool = False):
    return ActionResult(
        action="run_diagnostic_pppoe",
        status="success",
        data={
            "_estado": SimpleNamespace(online=online, sesion=SimpleNamespace(online=online)),
            "login_used": login,
            "service_id": service_id,
            "connectivity_status": "degraded" if not online else "operational",
            "reason_code": "no_session" if not online else "",
            "connectivity": {
                "status": "degraded" if not online else "operational",
                "reason_code": "no_session" if not online else "",
                "message": "sin sesión" if not online else "ok",
            },
        },
        user_message="sin sesión" if not online else "ok",
        correlation_id="c-27d",
        execution_path="runtime",
        reason_code="no_session" if not online else "",
    )


# --- Detection helpers ---


def test_27d_followup_and_note_phrases():
    assert _wants_incident_followup("sigue sin funcionar")
    assert _wants_incident_followup("todavía no tengo internet")
    assert _wants_ticket_customer_note("quiero agregar que sigue sin funcionar")
    assert _wants_ticket_customer_note("quiero agregar algo al reclamo")
    assert detect_journey_name("quiero agregar que sigue sin funcionar") == "ticket_consulta"
    assert detect_journey_name("qué pasó con mi reclamo") == "ticket_consulta"
    assert detect_journey_name("no tengo internet") == "internet_sin_conectividad"


# --- TEST 1 — Single service ---


def test_27d_single_service_diagnoses_correct_service(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "run_diagnostic_pppoe", "request_account_selection")
    ctx: dict = {}
    ar = _pppoe_ar(login="INT-ONLY", service_id="svc-only")
    with (
        patch("app.services.eko_context.internet_logins_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=ar) as disp,
        patch(
            "app.services.eko_journeys._enrich_login_to_ref",
            return_value=True,
        ),
        patch(
            "app.services.eko_journeys._try_capture_login",
            return_value="",
        ),
        patch(
            "app.services.canal_abonado._servicios_conectividad_abonado",
            return_value=[],
        ),
        patch(
            "app.services.billtrack.listar_logins_conectividad",
            return_value=["INT-ONLY"],
        ),
    ):
        # Seed canonical ref as single-service authority
        apply_service_ref(
            ctx,
            ServiceRef(
                service_id="svc-only",
                login="INT-ONLY",
                client_number="27001",
                service_type="internet",
            ),
        )
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
    assert turn.action_status != "needs_input"
    assert disp.call_count == 1
    assert turn.data.get("login_used") == "INT-ONLY"
    assert turn.data.get("service_id") == "svc-only"
    ref = get_journey(ctx).get("selected_service_ref") or {}
    assert ref.get("login") == "INT-ONLY" or ref.get("service_id") == "svc-only"


# --- TEST 2 — Multi service: no diag / no ticket ---


def test_27d_multi_service_needs_selection_no_diag_no_ticket(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(
        monkeypatch,
        "request_account_selection",
        "run_diagnostic_pppoe",
        "create_ticket",
    )
    ctx: dict = {}
    ar = ActionResult(
        action="request_account_selection",
        status="needs_input",
        user_message="elegí cuenta",
        correlation_id="c",
    )
    with (
        patch("app.services.eko_journeys._login_count", return_value=2),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=ar) as disp,
        patch(
            "app.services.canal_abonado._ticket_via_runtime_o_legacy",
            side_effect=AssertionError("no ticket on ambiguous"),
        ),
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
    assert turn.step == "service_selection"
    assert turn.action_status == "needs_input" or turn.action == "request_account_selection"
    assert get_journey(ctx).get("asked_selection") is True
    # No diagnostic action recorded as executed probe beyond selection
    actions = [c.args[0] for c in disp.call_args_list]
    assert "run_diagnostic_pppoe" not in actions
    assert "create_ticket" not in actions


# --- TEST 3 — Multi after selection ---


def test_27d_multi_after_selection_diagnoses_selected(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "run_diagnostic_pppoe", "request_account_selection")
    ctx: dict = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "service_selection",
            "asked_selection": True,
            "next_required_input": "login",
            "intent": "internet",
            "domain": "internet",
            "correlation_id": "c-sel",
        },
        "multi_cuenta_pendiente": True,
    }
    apply_service_ref(
        ctx,
        ServiceRef(
            service_id="svc-b",
            login="INT-B",
            client_number="27001",
            service_type="internet",
        ),
    )
    ar = _pppoe_ar(login="INT-B", service_id="svc-b")
    with (
        patch("app.services.eko_journeys._login_count", return_value=2),
        patch(
            "app.services.eko_handoff_continuity.should_ask_service_selection",
            return_value=False,
        ),
        patch("app.services.eko_journeys.dispatch_runtime", return_value=ar) as disp,
        patch("app.services.eko_journeys._try_capture_login", return_value=""),
    ):
        turn = maybe_handle_journey_turn(
            MagicMock(),
            "org-1",
            _conv(),
            _abo(),
            "revisá la conexión",
            canal="wa",
            ctx=ctx,
        )
    assert turn is not None
    assert turn.action == "run_diagnostic_pppoe"
    assert turn.data.get("login_used") == "INT-B"
    assert turn.data.get("service_id") == "svc-b"
    assert get_journey(ctx).get("selected_service_ref", {}).get("login") == "INT-B"
    assert disp.call_count == 1


# --- TEST 4 — Existing ticket continuity ---


def test_27d_existing_ticket_no_duplicate_on_repeat(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "run_diagnostic_pppoe", "create_ticket")
    ctx: dict = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "done",
            "last_action": "create_ticket",
            "last_action_status": "success",
            "last_diagnostic_result": "no_session",
            "intent": "internet",
            "domain": "internet",
            "correlation_id": "c-t",
        },
        "pppoe_informado": True,
    }
    apply_service_ref(
        ctx,
        ServiceRef(
            service_id="svc-only",
            login="INT-ONLY",
            client_number="27001",
            service_type="internet",
        ),
    )
    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch(
            "app.services.eko_journeys.dispatch_runtime",
            side_effect=AssertionError("no re-diag / no create"),
        ),
        patch(
            "app.services.canal_abonado._ticket_via_runtime_o_legacy",
            side_effect=AssertionError("no duplicate ticket"),
        ),
    ):
        turn = maybe_handle_journey_turn(
            MagicMock(),
            "org-1",
            _conv(ticket_id="TK-27D-EXIST"),
            _abo(),
            "todavía no tengo internet",
            canal="wa",
            ctx=ctx,
        )
    assert turn is not None
    assert turn.action_status == "already_done"
    assert turn.reason_code == "incident_continuity"
    assert turn.data.get("ticket_id") == "TK-27D-EXIST"
    assert turn.data.get("no_duplicate_ticket") is True
    assert get_journey(ctx).get("selected_service_ref", {}).get("login") == "INT-ONLY"


# --- TEST 5 — Follow-up → note path ---


def test_27d_followup_note_uses_existing_ticket(db, monkeypatch):
    session, org_id = db
    abo = Abonado(
        organizacion_id=org_id,
        dni="30127005",
        nombre="Follow",
        telefono_e164="2235127005",
        linea_msisdn="2235127005",
        servicio="internet",
        estado="activo",
    )
    session.add(abo)
    session.commit()
    session.refresh(abo)
    t = add_ticket(session, org_id, id="TK-27D-NOTE", linea="2235127005", estado="Abierto")
    conv = ConversacionCanal(
        organizacion_id=org_id,
        canal="wa",
        telefono="2235127005",
        abonado_id=abo.id,
        ticket_id=t.id,
        estado="bot",
    )
    session.add(conv)
    session.commit()
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "ticket_customer_note")
    ctx: dict = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "done",
            "last_action": "create_ticket",
            "intent": "internet",
            "domain": "internet",
            "correlation_id": "c-n",
        }
    }
    turn = maybe_handle_journey_turn(
        session,
        org_id,
        conv,
        abo,
        "quiero agregar que sigue sin funcionar",
        canal="wa",
        ctx=ctx,
    )
    assert turn is not None
    assert turn.action == "ticket_customer_note"
    assert turn.action_status == "success"
    assert turn.data.get("ticket_id") == t.id
    events = [e for e in repo.list_ticket_events(session, org_id, t.id) if e.tipo == "nota"]
    assert len(events) == 1
    assert "sigue sin funcionar" in (events[0].detalle or "").lower()


# --- TEST 6 — Foreign ticket DENY ---


def test_27d_foreign_ticket_deny(db, monkeypatch):
    session, org_id = db
    owner = Abonado(
        organizacion_id=org_id,
        dni="30127006",
        nombre="Owner",
        telefono_e164="2235127006",
        linea_msisdn="2235127006",
        servicio="internet",
        estado="activo",
    )
    other = Abonado(
        organizacion_id=org_id,
        dni="30127007",
        nombre="Other",
        telefono_e164="2235127007",
        linea_msisdn="2235127007",
        servicio="internet",
        estado="activo",
    )
    session.add_all([owner, other])
    session.commit()
    session.refresh(owner)
    session.refresh(other)
    foreign_tid = "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff"
    t = add_ticket(session, org_id, id=foreign_tid, linea="2235127006", estado="Abierto")
    other_conv = ConversacionCanal(
        organizacion_id=org_id,
        canal="wa",
        telefono="2235127007",
        abonado_id=other.id,
        ticket_id="",
        estado="bot",
    )
    session.add(other_conv)
    session.commit()
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "ticket_customer_note")
    turn = maybe_handle_journey_turn(
        session,
        org_id,
        other_conv,
        other,
        f"dejar nota {foreign_tid}: intento ajeno 27d",
        canal="wa",
        ctx={},
    )
    assert turn is not None
    assert turn.action_status == "denied"
    assert turn.reason_code == "foreign_ticket"
    assert not any(
        e.detalle and "intento ajeno" in e.detalle
        for e in repo.list_ticket_events(session, org_id, t.id)
    )


# --- TEST 7 — Ambiguous ticket ---


def test_27d_ambiguous_ticket_needs_input(db, monkeypatch):
    session, org_id = db
    abo = Abonado(
        organizacion_id=org_id,
        dni="30127008",
        nombre="Ambig",
        telefono_e164="2235127008",
        linea_msisdn="2235127008",
        servicio="internet",
        estado="activo",
    )
    session.add(abo)
    session.commit()
    session.refresh(abo)
    add_ticket(session, org_id, id="TK-27D-A1", linea="2235127008", estado="Abierto")
    add_ticket(session, org_id, id="TK-27D-A2", linea="2235127008", estado="Abierto")
    conv = ConversacionCanal(
        organizacion_id=org_id,
        canal="wa",
        telefono="2235127008",
        abonado_id=abo.id,
        ticket_id="",
        estado="bot",
    )
    session.add(conv)
    session.commit()
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "ticket_customer_note")
    turn = maybe_handle_journey_turn(
        session,
        org_id,
        conv,
        abo,
        "dejar nota: sigue igual",
        canal="wa",
        ctx={},
    )
    assert turn is not None
    assert turn.action_status == "needs_input"
    assert turn.reason_code == "ambiguous_ticket"
    assert session.query(TicketEvent).filter_by(organizacion_id=org_id).count() == 0


# --- TEST 8 — No active ticket ---


def test_27d_no_ticket_honest_fallback(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "ticket_customer_note")
    with patch(
        "app.services.abonado_tickets.list_tickets_visibles_abonado",
        return_value=[],
    ):
        turn = maybe_handle_journey_turn(
            MagicMock(),
            "org-1",
            _conv(ticket_id=""),
            _abo(telefono_e164="2235127001"),
            "quiero agregar que sigue sin funcionar",
            canal="wa",
            ctx={},
        )
    assert turn is not None
    assert turn.action == "ticket_customer_note"
    assert turn.action_status == "needs_input"
    assert turn.reason_code == "missing_ticket"


# --- TEST 9 — CASI: LLM cannot bypass ownership ---


def test_27d_casi_llm_cannot_bypass_ownership(db):
    session, org_id = db
    owner = Abonado(
        organizacion_id=org_id,
        dni="30127009",
        nombre="Own",
        telefono_e164="2235127009",
        linea_msisdn="2235127009",
        servicio="internet",
        estado="activo",
    )
    other = Abonado(
        organizacion_id=org_id,
        dni="30127010",
        nombre="Oth",
        telefono_e164="2235127010",
        linea_msisdn="2235127010",
        servicio="internet",
        estado="activo",
    )
    session.add_all([owner, other])
    session.commit()
    session.refresh(owner)
    session.refresh(other)
    t = add_ticket(session, org_id, id="TK-27D-CASI", linea="2235127009", estado="Abierto")
    prop = parse_llm_action_proposal(
        {
            "action": "ticket_customer_note",
            "parameters": {
                "ticket_id": t.id,
                "mensaje": "steal",
                "abonado_id": other.id,
                "ownership": "agent_authorized",
            },
            "abonado_id": other.id,
        }
    )
    assert prop is not None
    assert "abonado_id" not in prop.parameters
    assert "ownership" not in prop.parameters
    trusted = TrustedContext(
        conversation_id="conv-casi",
        organization_id=org_id,
        abonado_id=other.id,
        abonado=other,
        conv=MagicMock(id="conv-casi", ticket_id=t.id, estado="bot"),
        ctx={},
        db=session,
        canal="wa",
        confirmation_received=False,
        confirmation_rejected=False,
        decision_name="test_27d_casi",
    )
    r = execute_action(prop, trusted)
    assert r.status == "denied"
    assert r.reason_code == "foreign_ticket"


# --- TEST 10 — Runtime XOR create_ticket ---


def test_27d_xor_runtime_on_legacy_zero(monkeypatch):
    _enable_runtime(monkeypatch, "create_ticket")
    from app.services.canal_abonado import _ticket_via_runtime_o_legacy

    conv = _conv()
    ctx: dict = {
        "eko_action": {"action": "create_ticket", "status": "confirmation_pending"}
    }
    with (
        patch(
            "app.services.canal_abonado._crear_ticket_n2",
            side_effect=AssertionError("legacy must be 0"),
        ) as legacy,
        patch(
            "app.services.eko_action_bridge.dispatch_runtime",
            return_value=ActionResult(
                action="create_ticket",
                status="success",
                data={"ticket_id": "TK-XOR-ON"},
                execution_path="runtime",
            ),
        ),
    ):
        tid, pending = _ticket_via_runtime_o_legacy(
            MagicMock(),
            "org-1",
            conv,
            _abo(),
            "motivo",
            ctx=ctx,
            texto="sí",
            canal="wa",
        )
    assert tid == "TK-XOR-ON"
    assert pending is None
    legacy.assert_not_called()


def test_27d_xor_runtime_off_legacy_one(monkeypatch):
    _disable_runtime(monkeypatch)
    from app.services.canal_abonado import _ticket_via_runtime_o_legacy

    conv = _conv()
    with patch(
        "app.services.canal_abonado._crear_ticket_n2",
        return_value="TK-XOR-OFF",
    ) as legacy:
        tid, pending = _ticket_via_runtime_o_legacy(
            MagicMock(),
            "org-1",
            conv,
            _abo(),
            "motivo",
            ctx={},
            texto="sí",
            canal="wa",
        )
    assert tid == "TK-XOR-OFF"
    assert pending is None
    assert legacy.call_count == 1


def test_27d_note_runtime_off_no_legacy_visible(monkeypatch):
    _enable_journeys(monkeypatch)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ACTIONS", frozenset({"create_ticket"}))
    ctx: dict = {}
    turn = maybe_handle_journey_turn(
        MagicMock(),
        "org-1",
        _conv(ticket_id="TK-GATE"),
        _abo(),
        "dejar nota: sigue igual",
        canal="wa",
        ctx=ctx,
    )
    assert turn is not None
    assert turn.action == "ticket_customer_note"
    assert turn.action_status == "unavailable"
    assert turn.reason_code == "runtime_gate_off"


# --- Follow-up symptom without note phrase ---


def test_27d_sigue_sin_funcionar_keeps_incident(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "run_diagnostic_pppoe", "create_ticket")
    ctx: dict = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "done",
            "last_action": "create_ticket",
            "last_diagnostic_result": "no_session",
            "intent": "internet",
            "domain": "internet",
            "correlation_id": "c-f",
        }
    }
    with (
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch(
            "app.services.eko_journeys.dispatch_runtime",
            side_effect=AssertionError("no probe"),
        ),
    ):
        turn = maybe_handle_journey_turn(
            MagicMock(),
            "org-1",
            _conv(ticket_id="TK-27D-FU"),
            _abo(),
            "sigue sin funcionar",
            canal="wa",
            ctx=ctx,
        )
    assert turn is not None
    assert turn.data.get("incident_continuity") is True
    assert turn.data.get("ticket_id") == "TK-27D-FU"
    assert get_journey(ctx).get("name") == "internet_sin_conectividad"


# --- espera_agente hook ---


def test_27d_espera_agente_routes_followup(monkeypatch):
    _enable_journeys(monkeypatch)
    _enable_runtime(monkeypatch, "ticket_customer_note", "show_ticket")
    from app.services.canal_abonado import _try_incident_cx_en_espera

    abo = _abo()
    conv = _conv(ticket_id="TK-ESPERA", estado="espera_agente", abonado_id=abo.id)
    db = MagicMock()
    db.get.return_value = abo
    ctx_store = {
        "eko_journey": {
            "name": "internet_sin_conectividad",
            "step": "done",
            "last_action": "create_ticket",
            "last_diagnostic_result": "no_session",
            "intent": "internet",
            "domain": "internet",
        }
    }
    with (
        patch("app.services.canal_abonado.crepo.get_contexto", return_value=ctx_store),
        patch("app.services.canal_abonado.crepo.set_contexto"),
        patch("app.services.canal_abonado._enviar_respuesta"),
        patch("app.services.eko_journeys._login_count", return_value=1),
    ):
        out = _try_incident_cx_en_espera(
            db, "org-1", conv, "sigue sin funcionar", canal="wa"
        )
    assert out is not None
    assert out.get("incident_cx_espera") is True
    assert out.get("modo") == "espera_agente"
    assert out.get("ticket_id") == "TK-ESPERA"
