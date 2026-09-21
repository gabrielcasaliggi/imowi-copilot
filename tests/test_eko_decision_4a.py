"""Fase 4A — contrato Decision/Action Engine (audit, sin autonomía)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.radius.contract import ServicioConectividad
from app.services.canal_abonado import (
    _crear_ticket_n2,
    _deuda_positiva,
    _servicio_abonado,
)
from app.services.canal_pppoe import _talvez_mensaje_pppoe
from app.services.eco_voice import build_contexto_abonado
from app.services.eko_context import build_eko_facts, has_positive_debt
from app.services.eko_decision_catalog import (
    ACTIONS,
    CONVERSATION_STATE_KEYS,
    DECISION_FLOW,
    DECISIONS,
    ERROR_SEMANTICS,
    PLAYBOOKS_AUDIT,
    POLICY_GAPS,
    action_by_id,
    decision_by_id,
    decisions_requiring_confirmation,
    mutating_actions,
)


def _abonado(**kwargs):
    defaults = {
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
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# --- Catalog integrity ---


def test_4a_catalog_has_flow_and_inventories():
    assert "FACTS" in DECISION_FLOW
    assert "STATE" in DECISION_FLOW or "Conversation" in DECISION_FLOW or "STATE" in DECISION_FLOW
    assert len(DECISIONS) >= 10
    assert len(ACTIONS) >= 8
    assert len(PLAYBOOKS_AUDIT) >= 5
    assert "multi_cuenta_pendiente" in CONVERSATION_STATE_KEYS
    assert "login_seleccionado" in CONVERSATION_STATE_KEYS


def test_4a_mixed_decisions_have_mix_note():
    for d in DECISIONS:
        if d["kind"] == "LEGACY_MIXED" or d["status"] == "MIXED":
            assert d.get("mix_note"), f"{d['id']} MIXED sin mix_note"


def test_4a_mutating_actions_identified():
    mut = mutating_actions()
    ids = {a["id"] for a in mut}
    assert "create_ticket" in ids
    assert "run_diagnostic_pppoe" in ids
    conf = {d["id"] for d in decisions_requiring_confirmation()}
    assert "create_ticket_n2" in conf
    assert "multi_account_gate" in conf


def test_4a_error_semantics_contract():
    assert ERROR_SEMANTICS["billing_unavailable"].startswith("≠")
    assert ERROR_SEMANTICS["radius_unavailable"].startswith("≠")
    assert any(p["status"] == "POLICY GAP" for p in POLICY_GAPS)


# --- Facts → Decision (not ORM) ---


def test_4a_debt_decision_uses_facts_not_orm_attr_in_helper():
    """_deuda_positiva lee Facts (eko_context), no abonado.deuda_monto en su cuerpo."""
    src = inspect.getsource(_deuda_positiva)
    assert "has_positive_debt" in src or "build_eko_facts" in src or "_eko_facts" in src
    assert "abonado.deuda_monto" not in src
    assert _deuda_positiva(_abonado(deuda_monto="10")) is True
    assert has_positive_debt(build_eko_facts(_abonado(deuda_monto="0"))) is False


def test_4a_service_decision_uses_facts():
    src = inspect.getsource(_servicio_abonado)
    assert "servicio_agregado" in src or "build_eko_facts" in src or "_eko_facts" in src
    assert 'getattr(abonado, "servicio"' not in src
    assert _servicio_abonado(_abonado(servicio="movil")) == "movil"


def test_4a_canal_abonado_no_direct_factual_orm_reads():
    """Regresión 3C: canal_abonado no usa abonado.deuda_monto/estado/servicio directo."""
    path = Path(__file__).resolve().parents[1] / "app/services/canal_abonado.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "abonado" and node.attr in (
                "deuda_monto",
                "estado",
                "servicio",
            ):
                forbidden.add(node.attr)
    assert not forbidden, f"ORM factual directo en canal_abonado: {forbidden}"


# --- State: multi-account ---


def test_4a_multi_account_requires_selection_no_probe():
    abo = _abonado()
    ctx: dict = {}
    s1 = ServicioConectividad(
        login="A", service_type_code="INTFO", state="Habilitado",
        service_on=True, id="1", base_account_number="200",
    )
    s2 = ServicioConectividad(
        login="B", service_type_code="INTFO", state="Habilitado",
        service_on=True, id="2", base_account_number="201",
    )
    with (
        patch("app.services.billtrack.lookup_servicios_conectividad", return_value=[s1, s2]),
        patch("app.services.conexion_pppoe.consultar_conexion_pppoe") as radius,
        patch(
            "app.services.billtrack.mensaje_seleccion_cuenta_internet",
            return_value="¿Cuál?",
        ),
    ):
        msg = _talvez_mensaje_pppoe(MagicMock(), abo, ctx, "internet")
    assert msg == "¿Cuál?"
    assert ctx.get("multi_cuenta_pendiente") is True
    assert not ctx.get("login_seleccionado")
    radius.assert_not_called()
    d = decision_by_id("multi_account_gate")
    assert d and d["status"] == "READY"


# --- Technical: zero probes on context ---


def test_4a_normal_context_zero_probes():
    abo = _abonado()
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
        # Decisión factual no dispara probe
        assert _deuda_positiva(abo) is True

    assert pppoe.call_count == 0
    assert bcm.call_count == 0
    assert uisp.call_count == 0
    assert outage.call_count == 0


# --- Actions: read-only / mutating / confirmation / failed ---


def test_4a_read_only_show_balance_catalog():
    a = action_by_id("show_balance")
    assert a
    assert a["side_effect"] == "READ_ONLY"
    assert a["confirmation"] is False


def test_4a_mutating_create_ticket_idempotent_if_exists():
    """_crear_ticket_n2 no crea otro si conv.ticket_id ya existe (PROTECTED)."""
    conv = SimpleNamespace(
        ticket_id="existing-tkt",
        telefono="2235551234",
        canal="whatsapp",
        id="conv-1",
        servicio_detectado="",
    )
    with patch("app.services.canal_abonado.ticket_bridge.crear_ticket") as create:
        tid = _crear_ticket_n2(
            MagicMock(),
            "org-1",
            conv,
            _abonado(),
            "motivo",
        )
    assert tid == "existing-tkt"
    create.assert_not_called()
    a = action_by_id("create_ticket")
    assert a and a["idempotency"] == "PROTECTED"
    assert a["confirmation"] is True


def test_4a_confirmation_required_actions_listed():
    conf_actions = [a for a in ACTIONS if a["confirmation"]]
    ids = {a["id"] for a in conf_actions}
    assert "create_ticket" in ids
    assert "escalate_human" in ids
    assert "request_account_selection" in ids


def test_4a_llm_compose_is_not_mutating():
    a = action_by_id("llm_compose")
    assert a
    assert a["side_effect"] == "USER_VISIBLE_NO_MUTATION"
    assert "no ejecuta tools" in (a.get("note") or "").lower() or a["type"] == "presentation"


# --- Security ---


def test_4a_ticket_ownership_decision_is_security():
    d = decision_by_id("ticket_ownership")
    assert d
    assert d["kind"] == "SAFETY_SECURITY"
    assert d["status"] == "READY"


def test_4a_facts_are_not_authorization():
    """Un Fact disponible no implica permiso de mutación (contrato catalog)."""
    facts = build_eko_facts(_abonado())
    assert facts["billing"]["balance"] is not None
    # create_ticket sigue requiriendo confirmation + ownership — no auto por Facts
    a = action_by_id("create_ticket")
    assert a["confirmation"] is True
    assert a["authorization"]
