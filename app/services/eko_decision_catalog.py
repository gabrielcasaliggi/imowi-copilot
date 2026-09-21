"""Catálogo declarativo del Decision/Action Engine (Fase 4A).

NO ejecuta acciones. Solo inventaria decisiones y acciones existentes
para Agentic Ops (4B+). Fuente: código real al momento del audit.

Invariantes preservados:
- Facts → decisión factual (no ORM directo en N1)
- Conversation State ≠ Facts
- Technical Observations solo tras diagnóstico explícito
- LLM no ejecuta mutaciones sin capa de decisión
"""

from __future__ import annotations

from typing import Any, Literal

DecisionKind = Literal[
    "FACTUAL",
    "CONVERSATION_STATE",
    "TECHNICAL",
    "USER_CONFIRMATION",
    "SAFETY_SECURITY",
    "PRESENTATION",
    "LEGACY_MIXED",
]

DecisionStatus = Literal["READY", "PARTIAL", "LEGACY", "MIXED", "BLOCKED"]
SideEffect = Literal[
    "READ_ONLY",
    "USER_VISIBLE_NO_MUTATION",
    "MUTATING",
    "EXTERNAL_SIDE_EFFECT",
]
Idempotency = Literal["SAFE", "PROTECTED", "UNKNOWN", "RISK"]

# ---------------------------------------------------------------------------
# Flujo real (no aspiracional)
# ---------------------------------------------------------------------------

DECISION_FLOW = (
    "USER_INPUT"
    " → INTENCION/USER_ACT (clasificar_intencion | interpret_turn)"
    " → DOMAIN (domain_lifecycle / domain_adapter)"
    " → FACTS (build_eko_facts / accessors)"
    " + STATE (contexto_json / ConversationState)"
    " + TECHNICAL_OBS (extras post-diagnóstico)"
    " → DECISION (canal_abonado | conversation_motor | decision_engine | protocolo_mesa)"
    " → ACTION / PLAYBOOK"
    " → RESULT → USER_RESPONSE"
)

# Entrypoints reales por canal
ENTRYPOINTS = {
    "whatsapp_telegram_portal_bot": "app.services.canal_abonado",
    "helpdesk_chat": "app.services.motor_conversacional",
    "diagnostico_llm": "app.services.canal_diagnostico_ia",
    "pppoe_explicit": "app.services.canal_pppoe._talvez_mensaje_pppoe",
}

# ---------------------------------------------------------------------------
# Conversation State keys (no son Facts)
# ---------------------------------------------------------------------------

CONVERSATION_STATE_KEYS = frozenset(
    {
        "multi_cuenta_pendiente",
        "login_seleccionado",
        "pppoe_informado",
        "pppoe_rama",
        "wifi_rama_activada",
        "pasos_cubiertos",
        "paso_idx",
        "diag_turnos",
        "intencion",
        "intencion_tecnica_pendiente",
        "temas_pendientes",
        "phone_candidates",
        "ia_suggested_step",
        "ia_suggested_action",
        "encuesta_pendiente",
        "saludo",
        "identificado",
        "aviso_deuda",
        "cs",  # ConversationState hydrate key
    }
)

# ---------------------------------------------------------------------------
# Decision inventory
# ---------------------------------------------------------------------------

DECISIONS: list[dict[str, Any]] = [
    {
        "id": "intent_classify",
        "decision": "Clasificar intención N1 del texto",
        "source": "FACTUAL+STATE",
        "kind": "LEGACY_MIXED",
        "state": "texto; servicio_agregado vía Facts",
        "technical": False,
        "action": "set ctx.intencion / playbook",
        "side_effect": "READ_ONLY",
        "confirmation": False,
        "status": "PARTIAL",
        "impl": "flujos_abonado.clasificar_intencion + _servicio_abonado(Facts)",
        "mix_note": "Heurística de texto + Facts.servicio; no es puramente factual",
    },
    {
        "id": "user_act",
        "decision": "Interpretar user_act (ASK_CAUSE, CONFIRM_ACTION, …)",
        "source": "CONVERSATION_STATE",
        "kind": "CONVERSATION_STATE",
        "state": "ConversationState.pending_bot/last_bot_act",
        "technical": False,
        "action": "BotAction (ANSWER_USER / RESTATE / …)",
        "side_effect": "READ_ONLY",
        "confirmation": False,
        "status": "READY",
        "impl": "conversation_motor.interpret_turn / process_turn",
    },
    {
        "id": "domain_selection",
        "decision": "Seleccionar/cambiar dominio activo",
        "source": "CONVERSATION_STATE",
        "kind": "CONVERSATION_STATE",
        "state": "active_domain_id / slots",
        "technical": False,
        "action": "apply_domain_signal / lifecycle",
        "side_effect": "READ_ONLY",
        "confirmation": False,
        "status": "READY",
        "impl": "domain_lifecycle / domain_adapter",
    },
    {
        "id": "ask_cause_no_wifi",
        "decision": "ASK_CAUSE/HOW_TO no entra a playbook WiFi técnico",
        "source": "CONVERSATION_STATE",
        "kind": "CONVERSATION_STATE",
        "state": "domain + user_act",
        "technical": False,
        "action": "diagnóstico IA informativo o howto",
        "side_effect": "USER_VISIBLE_NO_MUTATION",
        "confirmation": False,
        "status": "READY",
        "impl": "canal_abonado._interceptar_domain_act_howto",
    },
    {
        "id": "debt_positive",
        "decision": "¿Hay deuda positiva?",
        "source": "facts.billing",
        "kind": "FACTUAL",
        "state": None,
        "technical": False,
        "action": "priorizar cobro / aviso",
        "side_effect": "READ_ONLY",
        "confirmation": False,
        "status": "READY",
        "impl": "eko_context.has_positive_debt / canal_abonado._deuda_positiva",
    },
    {
        "id": "account_cut",
        "decision": "¿Cuenta cortada/suspendida comercialmente?",
        "source": "facts.account.status",
        "kind": "FACTUAL",
        "state": None,
        "technical": False,
        "action": "rama corte_deuda / mensaje comercial",
        "side_effect": "READ_ONLY",
        "confirmation": False,
        "status": "READY",
        "impl": "eko_context.is_commercially_cut / clasificar_cuenta",
    },
    {
        "id": "service_has_internet",
        "decision": "¿Padron tiene internet fijo?",
        "source": "facts.account.servicio_agregado | services[]",
        "kind": "FACTUAL",
        "state": None,
        "technical": False,
        "action": "habilitar/bloquear diagnóstico PPPoE",
        "side_effect": "READ_ONLY",
        "confirmation": False,
        "status": "READY",
        "impl": "_servicio_abonado + tiene_internet_fijo",
    },
    {
        "id": "multi_account_gate",
        "decision": "¿Requiere selección de login Internet?",
        "source": "CONVERSATION_STATE + BillTrack logins",
        "kind": "CONVERSATION_STATE",
        "state": "multi_cuenta_pendiente / login_seleccionado",
        "technical": False,
        "action": "request_account_selection (no probe)",
        "side_effect": "USER_VISIBLE_NO_MUTATION",
        "confirmation": True,
        "status": "READY",
        "impl": "canal_pppoe._talvez_mensaje_pppoe",
    },
    {
        "id": "pppoe_diagnostic",
        "decision": "Ejecutar diagnóstico PPPoE/Radius",
        "source": "TECHNICAL",
        "kind": "TECHNICAL",
        "state": "login_seleccionado; intencion internet*",
        "technical": True,
        "action": "run_diagnostic_pppoe",
        "side_effect": "EXTERNAL_SIDE_EFFECT",
        "confirmation": False,
        "status": "READY",
        "impl": "canal_pppoe + conexion_pppoe.consultar_conexion_pppoe",
    },
    {
        "id": "bcm_uisp_branch",
        "decision": "Rama BCM/UISP tras PPPoE",
        "source": "TECHNICAL",
        "kind": "TECHNICAL",
        "state": "pppoe_informado / extras",
        "technical": True,
        "action": "run_diagnostic_bcm|uisp",
        "side_effect": "EXTERNAL_SIDE_EFFECT",
        "confirmation": False,
        "status": "READY",
        "impl": "canal_pppoe + conexion_bcm/uisp (explícito)",
    },
    {
        "id": "mesa_message",
        "decision": "Mensaje protocolo mesa (comercial vs planta)",
        "source": "FACTUAL+TECHNICAL",
        "kind": "LEGACY_MIXED",
        "state": None,
        "technical": True,
        "action": "send_message (presentation)",
        "side_effect": "USER_VISIBLE_NO_MUTATION",
        "confirmation": False,
        "status": "MIXED",
        "impl": "protocolo_mesa.decidir_mensaje_mesa",
        "mix_note": "Mezcla account Facts + observaciones técnicas + texto UI",
    },
    {
        "id": "ov_gesture",
        "decision": "Gesto OV (pagar/factura/talón)",
        "source": "USER_ACT → facts.ov + resolve_handoff",
        "kind": "LEGACY_MIXED",
        "state": "phone_candidates (handoff)",
        "technical": False,
        "action": "open_ov_link",
        "side_effect": "USER_VISIBLE_NO_MUTATION",
        "confirmation": False,
        "status": "PARTIAL",
        "impl": "ov_intencion.clasificar_gesto_ov + ov_handoff.resolve_handoff",
        "mix_note": "Facts.ov = links públicos; URL AUTH es handoff de turno (STATE/externo)",
    },
    {
        "id": "create_ticket_n2",
        "decision": "¿Crear ticket N2?",
        "source": "STATE + heurística persistencia",
        "kind": "USER_CONFIRMATION",
        "state": "historial; hechos; conv.ticket_id",
        "technical": False,
        "action": "create_ticket",
        "side_effect": "MUTATING",
        "confirmation": True,
        "status": "PARTIAL",
        "impl": "decision_engine.evaluar_crear_ticket + canal_abonado._crear_ticket_n2",
        "mix_note": "auto_confirmado=persistencia|solicita puede saltar confirmación explícita",
    },
    {
        "id": "escalate_human",
        "decision": "¿Escalar a agente humano?",
        "source": "CONVERSATION_STATE",
        "kind": "USER_CONFIRMATION",
        "state": "pending / authorize_escalate",
        "technical": False,
        "action": "escalate_human",
        "side_effect": "MUTATING",
        "confirmation": True,
        "status": "READY",
        "impl": "conversation_motor.authorize_escalate; canal_abonado cola",
    },
    {
        "id": "close_resolved",
        "decision": "¿Cerrar conversación como resuelta?",
        "source": "CONVERSATION_STATE",
        "kind": "USER_CONFIRMATION",
        "state": "authorize_resolved",
        "technical": False,
        "action": "close_conversation",
        "side_effect": "MUTATING",
        "confirmation": True,
        "status": "READY",
        "impl": "conversation_motor.authorize_resolved",
    },
    {
        "id": "ticket_ownership",
        "decision": "¿Ticket visible para este abonado?",
        "source": "SAFETY_SECURITY",
        "kind": "SAFETY_SECURITY",
        "state": None,
        "technical": False,
        "action": "show_ticket | deny",
        "side_effect": "READ_ONLY",
        "confirmation": False,
        "status": "READY",
        "impl": "abonado_tickets.ticket_pertenece_abonado",
    },
    {
        "id": "billing_message",
        "decision": "Texto de saldo / corte",
        "source": "facts.billing + facts.account",
        "kind": "PRESENTATION",
        "state": None,
        "technical": False,
        "action": "send_message",
        "side_effect": "USER_VISIBLE_NO_MUTATION",
        "confirmation": False,
        "status": "READY",
        "impl": "mensaje_saldo_padron / _responder_consulta_saldo",
    },
    {
        "id": "playbook_step",
        "decision": "Siguiente paso de playbook",
        "source": "CONVERSATION_STATE",
        "kind": "CONVERSATION_STATE",
        "state": "paso_idx / covered_steps / pending_bot",
        "technical": False,
        "action": "ask_next_step | provide_instruction",
        "side_effect": "USER_VISIBLE_NO_MUTATION",
        "confirmation": False,
        "status": "READY",
        "impl": "conversation_motor + playbooks_as_pasos",
    },
    {
        "id": "guardrail_planta",
        "decision": "Guardrail planta (enlace_ok / onu_offline) manda sobre LLM",
        "source": "TECHNICAL",
        "kind": "TECHNICAL",
        "state": "extras bcm/uisp",
        "technical": True,
        "action": "override_llm_response",
        "side_effect": "USER_VISIBLE_NO_MUTATION",
        "confirmation": False,
        "status": "READY",
        "impl": "guardrails_planta",
    },
]

# ---------------------------------------------------------------------------
# Action inventory
# ---------------------------------------------------------------------------

ACTIONS: list[dict[str, Any]] = [
    {
        "id": "send_message",
        "action": "send_message",
        "implementation": "canal_abonado._enviar_respuesta / crepo.add_mensaje",
        "type": "presentation",
        "side_effect": "USER_VISIBLE_NO_MUTATION",
        "confirmation": False,
        "authorization": "conversation ownership",
        "idempotency": "SAFE",
        "status": "READY",
    },
    {
        "id": "show_balance",
        "action": "show_balance",
        "implementation": "_responder_consulta_saldo → Facts.billing",
        "type": "read",
        "side_effect": "READ_ONLY",
        "confirmation": False,
        "authorization": "identified abonado",
        "idempotency": "SAFE",
        "status": "READY",
    },
    {
        "id": "open_ov",
        "action": "open_OV",
        "implementation": "resolve_handoff / plantilla_pago_qr / facts.ov links",
        "type": "navigation",
        "side_effect": "USER_VISIBLE_NO_MUTATION",
        "confirmation": False,
        "authorization": "abonado identity; JSAT optional AUTH",
        "idempotency": "UNKNOWN",
        "status": "PARTIAL",
        "note": "AUTH depende de JSAT externo (EXTERNAL)",
    },
    {
        "id": "request_account_selection",
        "action": "request_account_selection",
        "implementation": "billtrack.mensaje_seleccion_cuenta_internet",
        "type": "state",
        "side_effect": "USER_VISIBLE_NO_MUTATION",
        "confirmation": True,
        "authorization": "abonado owns logins",
        "idempotency": "SAFE",
        "status": "READY",
    },
    {
        "id": "run_diagnostic_pppoe",
        "action": "run_diagnostic_pppoe",
        "implementation": "conexion_pppoe.consultar_conexion_pppoe",
        "type": "technical",
        "side_effect": "EXTERNAL_SIDE_EFFECT",
        "confirmation": False,
        "authorization": "internet fijo + login seleccionado",
        "idempotency": "RISK",
        "status": "READY",
        "note": "No desde build_eko_facts/contexto normal",
    },
    {
        "id": "run_diagnostic_bcm",
        "action": "run_diagnostic_bcm",
        "implementation": "conexion_bcm.consultar_onu_bcm",
        "type": "technical",
        "side_effect": "EXTERNAL_SIDE_EFFECT",
        "confirmation": False,
        "authorization": "post-PPPoE FTTH path",
        "idempotency": "RISK",
        "status": "READY",
    },
    {
        "id": "run_diagnostic_uisp",
        "action": "run_diagnostic_uisp",
        "implementation": "conexion_uisp.consultar_cpe_uisp",
        "type": "technical",
        "side_effect": "EXTERNAL_SIDE_EFFECT",
        "confirmation": False,
        "authorization": "post-PPPoE radio path",
        "idempotency": "RISK",
        "status": "READY",
    },
    {
        "id": "create_ticket",
        "action": "create_ticket",
        "implementation": "canal_abonado._crear_ticket_n2 → ticket_bridge.crear_ticket",
        "type": "mutating",
        "side_effect": "MUTATING",
        "confirmation": True,
        "authorization": "org + conversation; idempotent if conv.ticket_id",
        "idempotency": "PROTECTED",
        "status": "PARTIAL",
        "note": "POLICY: auto_confirmado en persistencia puede omitir confirmación explícita",
    },
    {
        "id": "update_ticket_evidence",
        "action": "update_ticket",
        "implementation": "_append_evidencia_ticket",
        "type": "mutating",
        "side_effect": "MUTATING",
        "confirmation": False,
        "authorization": "ticket in org",
        "idempotency": "PROTECTED",
        "status": "READY",
    },
    {
        "id": "escalate_human",
        "action": "escalate_human",
        "implementation": "conv.estado=espera_agente / authorize_escalate",
        "type": "mutating",
        "side_effect": "MUTATING",
        "confirmation": True,
        "authorization": "conversation",
        "idempotency": "PROTECTED",
        "status": "READY",
    },
    {
        "id": "close_conversation",
        "action": "close_conversation",
        "implementation": "conv.estado=cerrado / ACT_CLOSE",
        "type": "mutating",
        "side_effect": "MUTATING",
        "confirmation": True,
        "authorization": "authorize_resolved",
        "idempotency": "PROTECTED",
        "status": "READY",
    },
    {
        "id": "show_ticket",
        "action": "show_ticket",
        "implementation": "facts.tickets / portal tickets",
        "type": "read",
        "side_effect": "READ_ONLY",
        "confirmation": False,
        "authorization": "ticket ownership",
        "idempotency": "SAFE",
        "status": "READY",
    },
    {
        "id": "llm_compose",
        "action": "llm_compose_response",
        "implementation": "canal_diagnostico_ia / eco_voice prompts",
        "type": "presentation",
        "side_effect": "USER_VISIBLE_NO_MUTATION",
        "confirmation": False,
        "authorization": "N1 context only",
        "idempotency": "SAFE",
        "status": "READY",
        "note": "LLM sugiere; no ejecuta tools/mutaciones directamente",
    },
]

# ---------------------------------------------------------------------------
# Playbook audit (referencias a suites)
# ---------------------------------------------------------------------------

PLAYBOOKS_AUDIT: list[dict[str, Any]] = [
    {
        "id": "eco_voice",
        "facts": True,
        "state": True,
        "technical": "via extras only",
        "actions": ["send_message", "llm_compose"],
        "mixed": False,
        "status": "READY",
    },
    {
        "id": "pppoe_wifi",
        "facts": True,
        "state": True,
        "technical": "explicit Radius/BCM/UISP",
        "actions": ["run_diagnostic_*", "request_account_selection", "send_message"],
        "mixed": False,
        "status": "READY",
    },
    {
        "id": "multi_cuenta",
        "facts": False,
        "state": True,
        "technical": False,
        "actions": ["request_account_selection"],
        "mixed": False,
        "status": "READY",
    },
    {
        "id": "wifi_bcm",
        "facts": False,
        "state": True,
        "technical": True,
        "actions": ["run_diagnostic_bcm", "send_message"],
        "mixed": False,
        "status": "READY",
    },
    {
        "id": "protocolo_mesa",
        "facts": True,
        "state": False,
        "technical": True,
        "actions": ["send_message"],
        "mixed": True,
        "status": "MIXED",
    },
    {
        "id": "pre_triaje",
        "facts": True,
        "state": False,
        "technical": True,
        "actions": ["send_message"],
        "mixed": False,
        "status": "READY",
    },
    {
        "id": "guardrails_planta",
        "facts": False,
        "state": False,
        "technical": True,
        "actions": ["override_llm_response"],
        "mixed": False,
        "status": "READY",
    },
    {
        "id": "cierre_pago",
        "facts": True,
        "state": True,
        "technical": False,
        "actions": ["open_ov", "send_message"],
        "mixed": False,
        "status": "READY",
    },
    {
        "id": "blindar_flujos",
        "facts": True,
        "state": True,
        "technical": False,
        "actions": ["send_message"],
        "mixed": False,
        "status": "READY",
    },
    {
        "id": "ticket_n2",
        "facts": "optional tickets[]",
        "state": True,
        "technical": False,
        "actions": ["create_ticket", "escalate_human"],
        "mixed": True,
        "status": "PARTIAL",
    },
]

# Error/fallback invariants (no implementar aquí; contrato)
ERROR_SEMANTICS = {
    "billtrack_unavailable": "≠ deuda=0",
    "billing_unavailable": "≠ deuda=0 / ≠ cuenta al día",
    "billing_stale": "≠ cuenta al día",
    "radius_unavailable": "≠ PPPoE disconnected",
    "bcm_unavailable": "≠ ONT offline",
    "uisp_unavailable": "≠ CPE offline",
    "ov_unavailable": "≠ invoice unavailable",
}

POLICY_GAPS = [
    {
        "id": "ticket_auto_confirm",
        "description": (
            "evaluar_crear_ticket puede setear auto_confirmado=True con persistencia/"
            "solicita; motor_conversacional también exige usuario_confirmo_ticket en "
            "algunos caminos. Política no unificada documentada."
        ),
        "status": "POLICY GAP",
    },
    {
        "id": "ov_auth_jsat",
        "description": "Handoff autenticado depende de JSAT externo; Facts solo links públicos.",
        "status": "EXTERNAL",
    },
]


def decision_by_id(decision_id: str) -> dict[str, Any] | None:
    for d in DECISIONS:
        if d["id"] == decision_id:
            return d
    return None


def action_by_id(action_id: str) -> dict[str, Any] | None:
    for a in ACTIONS:
        if a["id"] == action_id:
            return a
    return None


def mutating_actions() -> list[dict[str, Any]]:
    return [a for a in ACTIONS if a["side_effect"] in ("MUTATING", "EXTERNAL_SIDE_EFFECT")]


def decisions_requiring_confirmation() -> list[dict[str, Any]]:
    return [d for d in DECISIONS if d.get("confirmation")]
