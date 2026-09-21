"""Fase 4B — Action Runtime controlado (allowlist + policy + executors)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.eco_voice import build_contexto_abonado
from app.services.eko_action_runtime import (
    ActionRequest,
    TrustedContext,
    evaluate_policy,
    execute_action,
    get_action,
    is_registered,
    list_registered_actions,
    parse_llm_action_proposal,
    sanitize_parameters,
)
from app.services.eko_context import build_eko_facts


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


def _trusted(**kwargs) -> TrustedContext:
    base = dict(
        conversation_id="conv-1",
        organization_id="org-1",
        abonado_id="abo-1",
        abonado=_abo(),
        conv=SimpleNamespace(id="conv-1", ticket_id="", estado="bot", telefono="223", canal="wa", servicio_detectado=""),
        ctx={},
        db=MagicMock(),
        canal="whatsapp",
        confirmation_received=False,
        confirmation_rejected=False,
        decision_name="test",
    )
    base.update(kwargs)
    return TrustedContext(**base)


# --- Registry ---


def test_4b_known_actions_registered():
    names = set(list_registered_actions())
    for a in (
        "show_balance",
        "show_ticket",
        "open_OV",
        "request_account_selection",
        "run_diagnostic_pppoe",
        "run_diagnostic_bcm",
        "run_diagnostic_uisp",
        "create_ticket",
        "update_ticket",
        "escalate_human",
        "close_conversation",
        "send_message",
    ):
        assert a in names
        assert is_registered(a)


def test_4b_unknown_action_denied():
    r = execute_action(ActionRequest(action="execute_shell"), _trusted())
    assert r.status == "denied"
    assert r.reason_code == "unknown_action"

    r2 = execute_action(ActionRequest(action="call_api"), _trusted())
    assert r2.status == "denied"


# --- LLM boundary ---


def test_4b_llm_cannot_propose_arbitrary_function():
    assert parse_llm_action_proposal({"action": "os.system"}) is None
    assert parse_llm_action_proposal({"action": "getattr"}) is None
    prop = parse_llm_action_proposal({"action": "show_balance", "abonado_id": "hack"})
    assert prop is not None
    assert prop.source == "llm_proposal"
    assert "abonado_id" not in prop.parameters


def test_4b_llm_cannot_inject_authorization_or_identity():
    cleaned = sanitize_parameters(
        {
            "ticket_id": "t1",
            "abonado_id": "evil",
            "organization_id": "x",
            "dni": "30111222",
            "authorization": True,
            "confirmation_received": True,
            "jwt": "tok",
        }
    )
    assert cleaned == {"ticket_id": "t1"}
    assert "abonado_id" not in cleaned
    assert "confirmation_received" not in cleaned

    # confirmation_received del LLM no salta el gate
    trusted = _trusted(confirmation_received=False)
    # inject attempt via parameters ignored
    r = execute_action(
        ActionRequest(
            action="create_ticket",
            parameters={"confirmation_received": True, "motivo": "x"},
            source="llm_proposal",
        ),
        trusted,
    )
    assert r.status == "needs_confirmation"


def test_4b_llm_cannot_bypass_confirmation():
    trusted = _trusted(confirmation_received=False)
    r = execute_action(
        ActionRequest(action="create_ticket", parameters={"motivo": "x"}, source="llm_proposal"),
        trusted,
    )
    assert r.status == "needs_confirmation"
    assert trusted.ctx.get("eko_action", {}).get("status") == "confirmation_pending"


# --- Authorization ---


def test_4b_foreign_ticket_denied():
    abo = _abo(id="mine")
    foreign = SimpleNamespace(id="foreign-t", organizacion_id="org-1", estado="Abierto")
    db = MagicMock()
    db.get.return_value = foreign
    trusted = _trusted(abonado=abo, db=db, organization_id="org-1")
    with patch(
        "app.services.abonado_tickets.ticket_pertenece_abonado",
        return_value=False,
    ):
        r = execute_action(
            ActionRequest(action="show_ticket", parameters={"ticket_id": "foreign-t"}),
            trusted,
        )
    assert r.status == "denied"
    assert r.reason_code == "foreign_ticket"


def test_4b_own_ticket_allowed():
    abo = _abo(id="mine")
    own = SimpleNamespace(id="mine-t", organizacion_id="org-1", estado="Abierto", categoria="X", origen="WA", created_at=None, updated_at=None)
    db = MagicMock()
    db.get.return_value = own
    trusted = _trusted(abonado=abo, db=db)
    with (
        patch("app.services.abonado_tickets.ticket_pertenece_abonado", return_value=True),
        patch(
            "app.services.abonado_tickets.load_ticket_facts",
            return_value={"status": "ok", "items": [{"id": "mine-t", "state": "Abierto"}]},
        ),
    ):
        r = execute_action(
            ActionRequest(action="show_ticket", parameters={"ticket_id": "mine-t"}),
            trusted,
        )
    assert r.status == "success"


# --- Confirmation ---


def test_4b_create_ticket_needs_confirmation_then_allows():
    conv = SimpleNamespace(id="c1", ticket_id="", estado="bot", telefono="1", canal="wa", servicio_detectado="")
    trusted = _trusted(conv=conv, confirmation_received=False)
    r1 = execute_action(
        ActionRequest(action="create_ticket", parameters={"motivo": "persiste"}),
        trusted,
    )
    assert r1.status == "needs_confirmation"

    trusted2 = _trusted(conv=conv, confirmation_received=True, ctx={})
    with patch(
        "app.services.canal_abonado._crear_ticket_n2",
        return_value="newtkt",
    ) as create:
        r2 = execute_action(
            ActionRequest(action="create_ticket", parameters={"motivo": "persiste"}),
            trusted2,
        )
    assert r2.status == "success"
    assert r2.data.get("ticket_id") == "newtkt"
    create.assert_called_once()


def test_4b_confirmation_rejected_denied():
    trusted = _trusted(confirmation_rejected=True, confirmation_received=False)
    r = execute_action(
        ActionRequest(action="create_ticket", parameters={"motivo": "x"}),
        trusted,
    )
    assert r.status == "denied"
    assert r.reason_code == "confirmation_rejected"


# --- Multi-account ---


def test_4b_multi_account_diagnostic_needs_input_zero_probes():
    trusted = _trusted(ctx={"multi_cuenta_pendiente": True})
    with (
        patch(
            "app.services.conexion_pppoe.consultar_conexion_pppoe",
            side_effect=AssertionError("no Radius"),
        ) as radius,
        patch(
            "app.services.eko_context.internet_logins_count",
            return_value=2,
        ),
    ):
        r = execute_action(ActionRequest(action="run_diagnostic_pppoe"), trusted)
    assert r.status == "needs_input"
    assert r.reason_code == "account_selection_required"
    radius.assert_not_called()


def test_4b_policy_multi_account_before_executor():
    trusted = _trusted(ctx={"multi_cuenta_pendiente": True})
    pol = evaluate_policy(ActionRequest(action="run_diagnostic_pppoe"), trusted)
    assert pol.verdict == "NEEDS_INPUT"


# --- Technical / probes ---


def test_4b_explicit_diagnostic_invokes_reader_when_selected():
    trusted = _trusted(ctx={"login_seleccionado": "INT1"})
    estado = SimpleNamespace(
        error="",
        sesion=SimpleNamespace(online=True),
        servicio=SimpleNamespace(login="INT1"),
        online=True,
        resumen_prompt=lambda: "estado=conectado",
    )
    with (
        patch("app.services.eko_context.internet_logins_count", return_value=1),
        patch(
            "app.services.conexion_pppoe.consultar_conexion_pppoe",
            return_value=estado,
        ) as radius,
        patch(
            "app.services.conexion_pppoe.triage_pppoe_para_prompt",
            return_value="linea_ok",
        ),
    ):
        r = execute_action(ActionRequest(action="run_diagnostic_pppoe"), trusted)
    assert r.status == "success"
    assert radius.call_count == 1
    assert trusted.ctx.get("pppoe_informado") is True


def test_4b_normal_context_still_zero_probes():
    abo = _abo()
    with (
        patch(
            "app.services.conexion_pppoe.contexto_pppoe_para_abonado",
            side_effect=AssertionError("Radius"),
        ) as pppoe,
        patch(
            "app.services.conexion_bcm.contexto_bcm_para_abonado",
            side_effect=AssertionError("BCM"),
        ) as bcm,
        patch(
            "app.services.conexion_uisp.contexto_uisp_para_abonado",
            side_effect=AssertionError("UISP"),
        ) as uisp,
        patch(
            "app.services.outages.abonado_afectado_por_nas",
            side_effect=AssertionError("outage"),
        ) as outage,
    ):
        build_eko_facts(abo)
        build_contexto_abonado(abo)
        # read-only action tampoco probea
        execute_action(ActionRequest(action="show_balance"), _trusted(abonado=abo, db=None))

    assert pppoe.call_count == 0
    assert bcm.call_count == 0
    assert uisp.call_count == 0
    assert outage.call_count == 0


# --- Idempotency ---


def test_4b_create_ticket_already_done():
    conv = SimpleNamespace(id="c1", ticket_id="existing", estado="espera_agente", telefono="1", canal="wa", servicio_detectado="")
    trusted = _trusted(conv=conv, confirmation_received=True)
    with patch("app.services.canal_abonado._crear_ticket_n2") as create:
        r = execute_action(
            ActionRequest(action="create_ticket", parameters={"motivo": "x"}),
            trusted,
        )
    assert r.status == "already_done"
    assert r.data["ticket_id"] == "existing"
    create.assert_not_called()


def test_4b_update_ticket_foreign_denied_idempotent_path():
    trusted = _trusted()
    with patch("app.services.abonado_tickets.ticket_pertenece_abonado", return_value=False):
        trusted.db.get.return_value = SimpleNamespace(id="t", organizacion_id="org-1")
        r = execute_action(
            ActionRequest(
                action="update_ticket",
                parameters={"ticket_id": "t", "nota": "hola"},
            ),
            trusted,
        )
    assert r.status == "denied"
    assert get_action("update_ticket").idempotency == "PROTECTED"


# --- Errors ---


def test_4b_billing_unavailable_not_success():
    trusted = _trusted(abonado=None)
    # show_balance requires abonado → denied missing
    r = execute_action(ActionRequest(action="show_balance"), trusted)
    assert r.status == "denied"
    assert r.status != "success"


def test_4b_open_ov_forbidden_destination():
    r = execute_action(
        ActionRequest(action="open_OV", parameters={"destination": "admin-panel"}),
        _trusted(abonado=None),
    )
    # requires_abonado=False for open_OV
    assert r.status == "denied"
    assert r.reason_code == "destination_forbidden"


def test_4b_open_ov_public_success():
    r = execute_action(
        ActionRequest(action="open_OV", parameters={"destination": "pay"}),
        _trusted(abonado=_abo(), db=None),
    )
    assert r.status == "success"
    assert "http" in (r.data.get("url") or "")
    assert r.data.get("auth") == "external"


def test_4b_show_balance_success_from_facts():
    r = execute_action(ActionRequest(action="show_balance"), _trusted(db=None))
    assert r.status == "success"
    assert r.data.get("amount") == "1500"
    assert r.data.get("billing_status") == "stale"


def test_4b_observability_log_has_no_dni():
    r = execute_action(ActionRequest(action="show_balance"), _trusted(db=None))
    log = r.to_log(conversation_id="c1", decision_name="billing")
    blob = str(log)
    assert "30111222" not in blob
    assert "action_name" in log
    assert log["result_status"] == "success"
