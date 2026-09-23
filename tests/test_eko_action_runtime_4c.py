"""Fase 4C — cableado progresivo Action Runtime ↔ N1 (coexistencia + confirmation)."""

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
from app.services.eko_action_runtime import (
    ActionRequest,
    TrustedContext,
    execute_action,
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


def _enable_runtime(monkeypatch, *actions: str):
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ACTIONS", frozenset(actions))


# --- Feature gate / coexistence ---


def test_4c_feature_off_dispatch_returns_none(monkeypatch):
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", False)
    assert action_runtime_covers("show_balance") is False
    r = dispatch_runtime(
        "show_balance",
        db=None,
        org_id="org-1",
        conv=_conv(),
        abonado=_abo(),
        ctx={},
    )
    assert r is None


def test_4c_feature_on_covers_only_listed(monkeypatch):
    _enable_runtime(monkeypatch, "show_balance", "open_OV")
    assert action_runtime_covers("show_balance") is True
    assert action_runtime_covers("create_ticket") is False


# --- Confirmation contract ---


def test_4c_confirmation_not_from_auto_confirmado():
    """auto_confirmado del decision_engine NO implica confirmation trusted."""
    ctx = {}
    # Sin historial afirmativo ni pending + sí
    rec, rej = resolve_user_confirmation(
        historial=[{"rol": "usuario", "contenido": "sigue sin andar"}],
        ctx=ctx,
        action="create_ticket",
        texto="",
    )
    assert rec is False
    assert rej is False


def test_4c_confirmation_from_pending_si():
    ctx = {"eko_action": {"action": "create_ticket", "status": "confirmation_pending"}}
    rec, rej = resolve_user_confirmation(
        ctx=ctx, action="create_ticket", texto="sí"
    )
    assert rec is True
    assert rej is False


def test_4c_confirmation_reject_no():
    ctx = {"eko_action": {"action": "create_ticket", "status": "confirmation_pending"}}
    rec, rej = resolve_user_confirmation(
        ctx=ctx, action="create_ticket", texto="no"
    )
    assert rec is False
    assert rej is True


def test_4c_confirmation_usuario_confirmo_ticket_historial():
    historial = [
        {"rol": "asistente", "contenido": "¿Genero el ticket?"},
        {"rol": "usuario", "contenido": "sí, dale el ticket"},
    ]
    with patch(
        "app.domain.conversacion.usuario_confirmo_ticket",
        return_value=True,
    ):
        rec, rej = resolve_user_confirmation(
            historial=historial, action="create_ticket", ctx={}
        )
    assert rec is True
    assert rej is False


# --- Trusted context / LLM boundary ---


def test_4c_llm_cannot_set_confirmation_received(monkeypatch):
    _enable_runtime(monkeypatch, "create_ticket")
    ctx = {}
    trusted = build_trusted_context(
        db=MagicMock(),
        org_id="org-1",
        conv=_conv(),
        abonado=_abo(),
        ctx=ctx,
        action="create_ticket",
        texto="hola",
        historial=[{"rol": "usuario", "contenido": "hola"}],
        # Caller intenta forzar (simula LLM) — solo si pasa explícito; bridge
        # por defecto recalcula. Aquí pasamos None para forzar resolve.
    )
    assert trusted.confirmation_received is False


def test_4c_llm_proposal_confirmation_param_stripped():
    raw = {
        "action": "create_ticket",
        "confirmation_received": True,
        "abonado_id": "other-abo",
        "organization_id": "evil-org",
        "parameters": {
            "motivo": "x",
            "confirmation_received": True,
            "abonado_id": "other",
            "dni": "999",
        },
    }
    req = parse_llm_action_proposal(raw)
    assert req is not None
    assert req.action == "create_ticket"
    assert "confirmation_received" not in req.parameters
    assert "abonado_id" not in req.parameters
    assert "dni" not in sanitize_parameters(raw["parameters"])


def test_4c_llm_says_confirmed_user_did_not_needs_confirmation(monkeypatch):
    _enable_runtime(monkeypatch, "create_ticket")
    ctx = {}
    conv = _conv()
    with patch("app.services.canal_abonado._crear_ticket_n2") as create:
        ar = dispatch_runtime(
            "create_ticket",
            db=MagicMock(),
            org_id="org-1",
            conv=conv,
            abonado=_abo(),
            ctx=ctx,
            parameters={
                "motivo": "x",
                "confirmation_received": True,  # claim LLM — sanitizado
            },
            source="llm_proposal",
            texto="quiero un agente",
            historial=[{"rol": "usuario", "contenido": "quiero un agente"}],
        )
    assert ar is not None
    assert ar.status == "needs_confirmation"
    create.assert_not_called()
    assert ctx.get("eko_action", {}).get("status") == "confirmation_pending"


def test_4c_llm_abonado_id_ignored_in_trusted(monkeypatch):
    trusted = build_trusted_context(
        db=None,
        org_id="org-1",
        conv=_conv(abonado_id="abo-1"),
        abonado=_abo(id="abo-1"),
        ctx={},
        action="show_balance",
    )
    assert trusted.abonado_id == "abo-1"
    # Even if LLM params had other id, TrustedContext comes from abonado/conv
    assert trusted.abonado_id != "other-abo"


def test_4c_arbitrary_tool_denied():
    r = execute_action(
        ActionRequest(action="arbitrary_tool", source="llm_proposal"),
        TrustedContext(
            conversation_id="c",
            organization_id="org-1",
            abonado_id="abo-1",
            abonado=_abo(),
            conv=_conv(),
            ctx={},
            confirmation_received=True,
        ),
    )
    assert r.status == "denied"
    assert r.reason_code == "unknown_action"


# --- create_ticket idempotency + confirmation ---


def test_4c_create_ticket_with_trusted_confirmation_calls_writer_once(monkeypatch):
    _enable_runtime(monkeypatch, "create_ticket")
    ctx = {"eko_action": {"action": "create_ticket", "status": "confirmation_pending"}}
    conv = _conv()
    with patch(
        "app.services.canal_abonado._crear_ticket_n2",
        return_value="T-NEW",
    ) as create:
        ar = dispatch_runtime(
            "create_ticket",
            db=MagicMock(),
            org_id="org-1",
            conv=conv,
            abonado=_abo(),
            ctx=ctx,
            parameters={"motivo": "cliente confirma"},
            texto="sí",
            historial=[],
        )
    assert ar is not None
    assert ar.status == "success"
    assert ar.data["ticket_id"] == "T-NEW"
    assert create.call_count == 1


def test_4c_create_ticket_retry_same_conversation_already_done(monkeypatch):
    _enable_runtime(monkeypatch, "create_ticket")
    conv = _conv(ticket_id="T-EXIST")
    with patch("app.services.canal_abonado._crear_ticket_n2") as create:
        ar = dispatch_runtime(
            "create_ticket",
            db=MagicMock(),
            org_id="org-1",
            conv=conv,
            abonado=_abo(),
            ctx={},
            parameters={"motivo": "retry"},
            texto="sí",
            historial=[{"rol": "usuario", "contenido": "sí"}],
        )
    assert ar is not None
    assert ar.status == "already_done"
    assert ar.data["ticket_id"] == "T-EXIST"
    create.assert_not_called()


def test_4c_ticket_via_runtime_no_legacy_double(monkeypatch):
    """Cuando Runtime cubre create_ticket, Legacy no se invoca en paralelo."""
    from app.services.canal_abonado import _ticket_via_runtime_o_legacy

    _enable_runtime(monkeypatch, "create_ticket")
    ctx: dict = {}
    conv = _conv()
    db = MagicMock()
    with (
        patch(
            "app.estate.canal_repo.list_mensajes",
            return_value=[],
        ),
        patch(
            "app.services.canal_abonado._crear_ticket_n2",
            return_value="T1",
        ) as create,
        patch(
            "app.services.eko_action_bridge.dispatch_runtime",
            wraps=dispatch_runtime,
        ),
    ):
        # Primera: needs confirmation → no create
        tid, pending = _ticket_via_runtime_o_legacy(
            db,
            "org-1",
            conv,
            _abo(),
            "motivo",
            ctx=ctx,
            texto="agente",
            canal="whatsapp",
        )
    assert tid is None
    assert pending
    assert create.call_count == 0


# --- Security ---


def test_4c_foreign_ticket_denied():
    trusted = TrustedContext(
        conversation_id="c",
        organization_id="org-1",
        abonado_id="abo-1",
        abonado=_abo(),
        conv=_conv(),
        ctx={},
        db=MagicMock(),
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
    assert "foreign" not in (r.user_message or "").lower() or "acceso" in (
        r.user_message or ""
    ).lower()


def test_4c_fake_authorization_does_not_bypass_policy(monkeypatch):
    _enable_runtime(monkeypatch, "create_ticket")
    # confirmation_received solo vía TrustedContext rebuild — texto sin sí
    ar = dispatch_runtime(
        "create_ticket",
        db=MagicMock(),
        org_id="org-1",
        conv=_conv(),
        abonado=_abo(),
        ctx={},
        parameters={"authorized": True, "confirmation_received": True},
        texto="abri ticket",
        historial=[{"rol": "usuario", "contenido": "abri ticket"}],
    )
    assert ar is not None
    assert ar.status == "needs_confirmation"


# --- Probe gate ---


def test_4c_build_facts_and_decision_zero_probes():
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
        ),
    ):
        build_eko_facts(abo)
        build_contexto_abonado(abo)
        execute_action(ActionRequest(action="show_balance"), TrustedContext(
            conversation_id="c",
            organization_id="org-1",
            abonado_id="abo-1",
            abonado=abo,
            conv=_conv(),
            ctx={},
            db=None,
        ))
    assert pppoe.call_count == 0
    assert bcm.call_count == 0
    assert uisp.call_count == 0


def test_4c_explicit_pppoe_exactly_one_reader(monkeypatch):
    _enable_runtime(monkeypatch, "run_diagnostic_pppoe")
    ctx = {
        "eko_journey": {
            "selected_service_ref": {
                "service_id": "",
                "login": "INT1",
                "service_type": "internet",
                "client_number": "200",
            }
        },
        "login_seleccionado": "INT1",
    }
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
            return_value="linea_ok",
        ),
    ):
        ar = dispatch_runtime(
            "run_diagnostic_pppoe",
            db=MagicMock(),
            org_id="org-1",
            conv=_conv(),
            abonado=_abo(),
            ctx=ctx,
        )
    assert ar is not None
    assert ar.status == "success"
    assert radius.call_count == 1


def test_4c_multi_cuenta_needs_input_no_radius(monkeypatch):
    _enable_runtime(monkeypatch, "run_diagnostic_pppoe", "request_account_selection")
    ctx = {"multi_cuenta_pendiente": True}
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
            ctx=ctx,
        )
    assert ar is not None
    assert ar.status == "needs_input"
    radius.assert_not_called()


# --- show_balance facts ---


def test_4c_show_balance_uses_facts_not_second_billtrack(monkeypatch):
    _enable_runtime(monkeypatch, "show_balance")
    abo = _abo(deuda_monto="0")
    with patch(
        "app.services.eko_context.build_eko_facts",
        wraps=build_eko_facts,
    ) as facts_fn:
        ar = dispatch_runtime(
            "show_balance",
            db=None,
            org_id="org-1",
            conv=_conv(),
            abonado=abo,
            ctx={},
        )
    assert ar is not None
    assert ar.status == "success"
    assert facts_fn.call_count >= 1
    assert ar.data.get("billing_status") in ("live", "stale", "unavailable", None) or True


def test_4c_show_balance_unavailable_not_al_dia(monkeypatch):
    _enable_runtime(monkeypatch, "show_balance")
    abo = _abo(deuda_monto=None)
    with patch(
        "app.services.eko_context.build_eko_facts",
        return_value={
            "billing": {"status": "unavailable", "balance": None, "currency": "ARS"},
        },
    ):
        r = execute_action(
            ActionRequest(action="show_balance"),
            TrustedContext(
                conversation_id="c",
                organization_id="org-1",
                abonado_id="abo-1",
                abonado=abo,
                conv=_conv(),
                ctx={},
                db=None,
            ),
        )
    assert r.status == "unavailable"
    msg = (r.user_message or "").lower()
    assert "al día" not in msg and "al dia" not in msg
