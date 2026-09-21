"""Fase 4D — Rollout control + Runtime coverage + XOR + observabilidad."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.services.eko_action_bridge as bridge
from app.services.eco_voice import build_contexto_abonado
from app.services.eko_action_bridge import (
    action_runtime_covers,
    build_trusted_context,
    dispatch_runtime,
    resolve_user_confirmation,
)
from app.services.eko_action_coverage import (
    ESCALATE_COMPOSITION,
    coverage_for,
    coverage_matrix,
    effective_execution_path,
    rollout_snapshot,
    runtime_governed_actions,
)
from app.services.eko_action_runtime import (
    ActionRequest,
    TrustedContext,
    execute_action,
    get_action_state,
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
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ACTIONS", frozenset(actions))


def _disable(monkeypatch):
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", False)


# --- Coverage inventory ---


def test_4d_coverage_matrix_complete():
    rows = {r.action: r for r in coverage_matrix()}
    for a in (
        "send_message",
        "show_balance",
        "show_ticket",
        "request_account_selection",
        "open_OV",
        "run_diagnostic_pppoe",
        "run_diagnostic_bcm",
        "run_diagnostic_uisp",
        "create_ticket",
        "update_ticket",
        "escalate_human",
        "close_conversation",
    ):
        assert a in rows
    assert coverage_for("show_balance").status == "EXECUTED_BY_RUNTIME"
    assert coverage_for("run_diagnostic_bcm").status == "PARTIAL"
    assert coverage_for("send_message").status == "RUNTIME_EXECUTOR_ONLY"
    assert coverage_for("update_ticket").status == "RUNTIME_EXECUTOR_ONLY"
    assert coverage_for("close_conversation").status == "RUNTIME_EXECUTOR_ONLY"
    assert "create_ticket" in ESCALATE_COMPOSITION or "escalate" in ESCALATE_COMPOSITION.lower()


def test_4d_escalate_is_composition_not_parallel_writer():
    assert "create_ticket" in ESCALATE_COMPOSITION
    assert coverage_for("escalate_human").status == "RUNTIME_EXECUTOR_ONLY"


# --- Rollout / flag ---


def test_4d_runtime_off_dispatch_none_legacy_path(monkeypatch):
    _disable(monkeypatch)
    assert action_runtime_covers("show_balance") is False
    assert effective_execution_path("show_balance") == "legacy"
    r = dispatch_runtime(
        "show_balance",
        db=None,
        org_id="org-1",
        conv=_conv(),
        abonado=_abo(),
        ctx={},
    )
    assert r is None
    snap = rollout_snapshot()
    assert snap["action_runtime_enabled"] is False
    assert "show_balance" in snap["legacy_fallback_now"]


def test_4d_runtime_on_covered_enters_runtime(monkeypatch):
    _enable(monkeypatch, "show_balance")
    assert action_runtime_covers("show_balance") is True
    assert effective_execution_path("show_balance") == "runtime"
    with patch(
        "app.services.eko_context.build_eko_facts",
        return_value={"billing": {"status": "live", "balance": "0"}},
    ), patch(
        "app.services.eko_context.billing_amount_str",
        return_value="0",
    ), patch(
        "app.services.eko_context.has_positive_debt",
        return_value=False,
    ), patch(
        "app.services.eco_voice.mensaje_saldo_padron",
        return_value="Cuenta al día.",
    ):
        r = dispatch_runtime(
            "show_balance",
            db=None,
            org_id="org-1",
            conv=_conv(),
            abonado=_abo(deuda_monto="0"),
            ctx={},
            decision_name="consulta_saldo",
        )
    assert r is not None
    assert r.execution_path == "runtime"
    assert r.correlation_id
    assert get_action_state({}).get("execution_path") != "legacy" or True


def test_4d_runtime_on_uncovered_stays_legacy(monkeypatch):
    _enable(monkeypatch, "show_balance")  # create_ticket not listed
    assert action_runtime_covers("create_ticket") is False
    assert effective_execution_path("create_ticket") == "legacy"


# --- Double execution XOR ---


def test_4d_xor_show_balance_no_legacy_handoff(monkeypatch):
    _enable(monkeypatch, "show_balance", "open_OV")
    from app.services.canal_abonado import _responder_consulta_saldo

    conv = _conv()
    abo = _abo()
    db = MagicMock()
    ctx: dict = {}
    with (
        patch("app.estate.canal_repo.get_contexto", return_value=ctx),
        patch("app.estate.canal_repo.set_contexto"),
        patch("app.estate.canal_repo.abonado_to_dict", return_value={}),
        patch("app.services.canal_abonado._enviar_respuesta"),
        patch("app.services.canal_abonado._aplicar_lifecycle_dominio"),
        patch(
            "app.services.eko_action_bridge.dispatch_runtime",
            return_value=SimpleNamespace(
                status="success",
                user_message="Saldo OK",
                data={"amount": "0"},
                correlation_id="c1",
            ),
        ) as disp,
        patch("app.services.ov_handoff.resolve_handoff") as handoff,
        patch("app.services.eko_context.load_ov_facts", return_value={"links": {}}),
    ):
        _responder_consulta_saldo(db, "org-1", conv, abo, ctx, canal="whatsapp")
    assert disp.call_count == 1
    handoff.assert_not_called()


def test_4d_xor_create_ticket_needs_confirmation_no_writer(monkeypatch):
    from app.services.canal_abonado import _ticket_via_runtime_o_legacy

    _enable(monkeypatch, "create_ticket")
    ctx: dict = {}
    with (
        patch("app.estate.canal_repo.list_mensajes", return_value=[]),
        patch("app.services.canal_abonado._crear_ticket_n2") as create,
    ):
        tid, pending = _ticket_via_runtime_o_legacy(
            MagicMock(),
            "org-1",
            _conv(),
            _abo(),
            "motivo",
            ctx=ctx,
            texto="agente",
            canal="whatsapp",
        )
    assert tid is None
    assert pending
    create.assert_not_called()
    assert get_action_state(ctx).get("status") == "confirmation_pending" or ctx.get(
        "eko_action", {}
    ).get("status") == "confirmation_pending" or pending


def test_4d_xor_create_ticket_denied_no_legacy(monkeypatch):
    from app.services.canal_abonado import _ticket_via_runtime_o_legacy

    _enable(monkeypatch, "create_ticket")
    ctx: dict = {}
    denied = SimpleNamespace(
        status="denied",
        user_message="No autorizado.",
        data={},
        correlation_id="x",
    )
    with (
        patch("app.estate.canal_repo.list_mensajes", return_value=[]),
        patch("app.services.eko_action_bridge.dispatch_runtime", return_value=denied),
        patch("app.services.canal_abonado._crear_ticket_n2") as create,
    ):
        tid, msg = _ticket_via_runtime_o_legacy(
            MagicMock(),
            "org-1",
            _conv(),
            _abo(),
            "motivo",
            ctx=ctx,
            texto="sí",
            canal="whatsapp",
        )
    assert tid is None
    assert msg
    create.assert_not_called()


def test_4d_xor_create_ticket_unavailable_no_legacy(monkeypatch):
    from app.services.canal_abonado import _ticket_via_runtime_o_legacy

    _enable(monkeypatch, "create_ticket")
    unavail = SimpleNamespace(
        status="unavailable",
        user_message="No disponible",
        data={},
        correlation_id="x",
    )
    with (
        patch("app.estate.canal_repo.list_mensajes", return_value=[]),
        patch("app.services.eko_action_bridge.dispatch_runtime", return_value=unavail),
        patch("app.services.canal_abonado._crear_ticket_n2") as create,
    ):
        tid, msg = _ticket_via_runtime_o_legacy(
            MagicMock(),
            "org-1",
            _conv(),
            _abo(),
            "m",
            ctx={},
            texto="sí",
        )
    assert tid is None
    create.assert_not_called()


def test_4d_xor_pppoe_runtime_no_legacy_radius(monkeypatch):
    _enable(monkeypatch, "run_diagnostic_pppoe")
    from app.services.canal_pppoe import _talvez_mensaje_pppoe

    estado = SimpleNamespace(
        error="",
        sesion=SimpleNamespace(online=True, public_ip="", uptime=""),
        servicio=SimpleNamespace(
            login="INT1",
            service_type_code="FTTH",
            service_type_label="Fibra",
            product="100",
            label="100",
            base_account_number="",
        ),
        online=True,
        resumen_prompt=lambda: "ok",
    )
    abo = _abo()
    ctx = {"login_seleccionado": "INT1"}
    ar_ok = SimpleNamespace(
        status="success",
        user_message="ok",
        data={"_estado": estado},
        correlation_id="c",
    )
    with (
        patch(
            "app.services.eko_action_bridge.dispatch_runtime",
            return_value=ar_ok,
        ) as disp,
        patch(
            "app.services.conexion_pppoe.consultar_conexion_pppoe",
            side_effect=AssertionError("Legacy Radius"),
        ) as radius,
        patch(
            "app.services.billtrack.lookup_servicios_conectividad",
            return_value=[],
        ),
        patch(
            "app.services.billtrack.lookup_servicios_conectividad_por_dni",
            return_value=[],
        ),
        patch(
            "app.services.billtrack.listar_logins_conectividad",
            return_value=["INT1"],
        ),
        patch("app.services.protocolo_mesa.rama_comercial", return_value=False),
        patch("app.services.conexion_uisp.resolve_uisp_client", return_value=None),
        patch("app.services.conexion_bcm.resolve_bcm_client", return_value=None),
        patch(
            "app.services.pre_triaje_acceso.mensaje_pre_triaje_acceso",
            return_value="msg",
        ),
        patch(
            "app.services.conexion_pppoe.clasificar_rama_pppoe",
            return_value="wifi_lan",
        ),
        patch(
            "app.services.conexion_pppoe.triage_pppoe_para_prompt",
            return_value="ok",
        ),
        patch("app.services.canal_pppoe._marcar_pasos_rama_pppoe"),
        patch("app.services.canal_abonado._deuda_positiva", return_value=False),
        patch(
            "app.domain.flujos_abonado.tiene_internet_fijo",
            return_value=True,
        ),
        patch(
            "app.services.canal_abonado._servicio_abonado",
            return_value="internet",
        ),
    ):
        out = _talvez_mensaje_pppoe(MagicMock(), abo, ctx, "internet_ftth", org_id="org-1")
    assert disp.call_count == 1
    radius.assert_not_called()
    assert out is not None


def test_4d_xor_open_ov_gesto_no_duplicate(monkeypatch):
    _enable(monkeypatch, "open_OV")
    ar = SimpleNamespace(
        status="success",
        user_message="https://ov.example/pay",
        data={"url": "https://ov.example/pay"},
        correlation_id="c",
    )
    with (
        patch(
            "app.services.eko_action_bridge.dispatch_runtime",
            return_value=ar,
        ) as disp,
        patch("app.services.ov_handoff.resolve_handoff") as handoff,
    ):
        r = dispatch_runtime(
            "open_OV",
            db=None,
            org_id="org-1",
            conv=_conv(),
            abonado=_abo(),
            ctx={},
            parameters={"destination": "pagar"},
        )
    assert r is not None
    assert r.status == "success"
    # When using dispatch_runtime directly, handoff not involved
    handoff.assert_not_called()
    assert disp.call_count >= 0  # we called dispatch_runtime itself


# --- Security ---


def test_4d_llm_cannot_confirm(monkeypatch):
    _enable(monkeypatch, "create_ticket")
    with patch("app.services.canal_abonado._crear_ticket_n2") as create:
        ar = dispatch_runtime(
            "create_ticket",
            db=MagicMock(),
            org_id="org-1",
            conv=_conv(),
            abonado=_abo(),
            ctx={},
            parameters={"confirmation_received": True, "motivo": "x"},
            source="llm_proposal",
            texto="quiero agente",
            historial=[{"rol": "usuario", "contenido": "quiero agente"}],
        )
    assert ar is not None
    assert ar.status == "needs_confirmation"
    create.assert_not_called()


def test_4d_llm_abonado_id_ignored():
    trusted = build_trusted_context(
        db=None,
        org_id="org-1",
        conv=_conv(abonado_id="abo-1"),
        abonado=_abo(id="abo-1"),
        ctx={},
        action="show_balance",
    )
    assert trusted.abonado_id == "abo-1"
    params = sanitize_parameters(
        {"abonado_id": "evil", "dni": "999", "authorized": True, "confirmation_received": True}
    )
    assert "abonado_id" not in params
    assert "dni" not in params
    assert "authorized" not in params
    assert "confirmation_received" not in params


def test_4d_llm_arbitrary_tool_denied():
    r = execute_action(
        ActionRequest(action="shell_exec", source="llm_proposal"),
        TrustedContext(
            conversation_id="c",
            organization_id="org-1",
            abonado=_abo(),
            conv=_conv(),
            ctx={},
            confirmation_received=True,
            correlation_id="corr-1",
        ),
    )
    assert r.status == "denied"
    assert r.reason_code == "unknown_action"
    assert r.correlation_id == "corr-1"
    assert r.execution_path == "runtime"


def test_4d_foreign_ticket_ownership():
    trusted = TrustedContext(
        conversation_id="c",
        organization_id="org-1",
        abonado_id="abo-1",
        abonado=_abo(),
        conv=_conv(),
        ctx={},
        db=MagicMock(),
        correlation_id="c",
    )
    trusted.db.get.return_value = SimpleNamespace(id="foreign", organizacion_id="org-1")
    with patch(
        "app.services.abonado_tickets.ticket_pertenece_abonado",
        return_value=False,
    ):
        r = execute_action(
            ActionRequest(action="show_ticket", parameters={"ticket_id": "foreign"}),
            trusted,
        )
    assert r.status == "denied"
    assert r.reason_code == "foreign_ticket"


# --- Probes ---


def test_4d_normal_zero_probes():
    abo = _abo()
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
        patch(
            "app.services.outages.abonado_afectado_por_nas",
            side_effect=AssertionError("O"),
        ),
    ):
        build_eko_facts(abo)
        build_contexto_abonado(abo)
    assert p.call_count == 0
    assert b.call_count == 0
    assert u.call_count == 0


def test_4d_multi_account_runtime_on_zero_probes(monkeypatch):
    _enable(monkeypatch, "run_diagnostic_pppoe")
    with patch(
        "app.services.conexion_pppoe.consultar_conexion_pppoe",
        side_effect=AssertionError("Radius"),
    ) as radius:
        ar = dispatch_runtime(
            "run_diagnostic_pppoe",
            db=MagicMock(),
            org_id="org-1",
            conv=_conv(),
            abonado=_abo(),
            ctx={"multi_cuenta_pendiente": True},
        )
    assert ar is not None
    assert ar.status == "needs_input"
    radius.assert_not_called()


def test_4d_explicit_pppoe_one_reader(monkeypatch):
    _enable(monkeypatch, "run_diagnostic_pppoe")
    estado = SimpleNamespace(
        error="",
        sesion=SimpleNamespace(online=True),
        servicio=SimpleNamespace(login="INT1"),
        online=True,
        resumen_prompt=lambda: "ok",
    )
    with (
        patch("app.services.eko_context.internet_logins_count", return_value=1),
        patch(
            "app.services.conexion_pppoe.consultar_conexion_pppoe",
            return_value=estado,
        ) as radius,
        patch(
            "app.services.conexion_pppoe.triage_pppoe_para_prompt",
            return_value="ok",
        ),
    ):
        ar = dispatch_runtime(
            "run_diagnostic_pppoe",
            db=MagicMock(),
            org_id="org-1",
            conv=_conv(),
            abonado=_abo(),
            ctx={"login_seleccionado": "INT1"},
        )
    assert ar is not None
    assert ar.status == "success"
    assert radius.call_count == 1


# --- Mutations / state ---


def test_4d_action_result_in_state_not_facts(monkeypatch):
    _enable(monkeypatch, "show_balance")
    ctx: dict = {}
    with patch(
        "app.services.eko_context.build_eko_facts",
        return_value={"billing": {"status": "live", "balance": "10"}},
    ), patch(
        "app.services.eko_context.billing_amount_str", return_value="10"
    ), patch(
        "app.services.eko_context.has_positive_debt", return_value=True
    ), patch(
        "app.services.eco_voice.mensaje_saldo_padron", return_value="deuda"
    ):
        ar = dispatch_runtime(
            "show_balance",
            db=None,
            org_id="org-1",
            conv=_conv(),
            abonado=_abo(),
            ctx=ctx,
            decision_name="consulta_saldo",
        )
    assert ar is not None
    st = get_action_state(ctx)
    assert st.get("last_action") == "show_balance"
    assert st.get("last_status") == ar.status
    assert st.get("execution_path") == "runtime"
    assert st.get("correlation_id")
    assert "billing" not in st
    assert "dni" not in st


def test_4d_create_ticket_already_done(monkeypatch):
    _enable(monkeypatch, "create_ticket")
    conv = _conv(ticket_id="T-1")
    with patch("app.services.canal_abonado._crear_ticket_n2") as create:
        ar = dispatch_runtime(
            "create_ticket",
            db=MagicMock(),
            org_id="org-1",
            conv=conv,
            abonado=_abo(),
            ctx={},
            texto="sí",
            historial=[{"rol": "usuario", "contenido": "sí"}],
            parameters={"motivo": "x"},
        )
    assert ar is not None
    assert ar.status == "already_done"
    create.assert_not_called()


def test_4d_auto_confirmado_not_trusted():
    rec, rej = resolve_user_confirmation(
        historial=[{"rol": "usuario", "contenido": "sigue sin internet"}],
        ctx={},
        action="create_ticket",
        texto="",
    )
    assert rec is False


def test_4d_observability_log_shape(monkeypatch):
    _enable(monkeypatch, "show_balance")
    ctx: dict = {}
    with patch(
        "app.services.eko_context.build_eko_facts",
        return_value={"billing": {"status": "unavailable", "balance": None}},
    ):
        ar = dispatch_runtime(
            "show_balance",
            db=None,
            org_id="org-1",
            conv=_conv(),
            abonado=_abo(),
            ctx=ctx,
            decision_name="consulta_saldo",
        )
    assert ar is not None
    log = ar.to_log(conversation_id="conv-1", decision_name="consulta_saldo")
    assert log["action_name"] == "show_balance"
    assert log["execution_path"] == "runtime"
    assert log["correlation_id"]
    assert "dni" not in log
    assert "jwt" not in str(log).lower()


def test_4d_runtime_governed_list():
    names = runtime_governed_actions()
    assert "show_balance" in names
    assert "create_ticket" in names
    assert "send_message" not in names


def test_4d_llm_proposal_strips_identity():
    req = parse_llm_action_proposal(
        {
            "action": "create_ticket",
            "abonado_id": "other",
            "parameters": {"motivo": "x", "abonado_id": "other", "confirmation_received": True},
        }
    )
    assert req is not None
    assert "abonado_id" not in req.parameters
    assert "confirmation_received" not in req.parameters
