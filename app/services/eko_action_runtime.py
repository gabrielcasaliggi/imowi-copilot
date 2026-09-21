"""Action Runtime controlado — Fase 4B Agentic Ops.

```
Decision / LLM proposal
    → ActionRequest (validated)
    → Policy / Authorization / Confirmation
    → Allowlisted Executor
    → ActionResult
```

El LLM NUNCA ejecuta funciones. Solo puede proponer un nombre de acción
del allowlist; identidad y autorización salen del TrustedContext backend.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy.orm import Session

logger = logging.getLogger("operations_hub")

ActionStatus = Literal[
    "success",
    "failed",
    "denied",
    "needs_confirmation",
    "needs_input",
    "unavailable",
    "already_done",
]

PolicyVerdict = Literal[
    "ALLOW",
    "DENY",
    "NEEDS_CONFIRMATION",
    "NEEDS_INPUT",
    "UNAVAILABLE",
]

ConfirmationState = Literal[
    "NOT_REQUIRED",
    "REQUIRED",
    "CONFIRMED",
    "REJECTED",
]

IdempotencyClass = Literal["SAFE", "PROTECTED", "RISK", "UNKNOWN"]

# ---------------------------------------------------------------------------
# Trust boundary
# ---------------------------------------------------------------------------

# Campos que el LLM / input no confiable NUNCA puede imponer.
_UNTRUSTED_PARAM_KEYS = frozenset(
    {
        "abonado_id",
        "organization_id",
        "org_id",
        "dni",
        "client_number",
        "authorization",
        "authorized",
        "confirmation",
        "confirmation_received",
        "ticket_owner",
        "jwt",
        "sid",
        "tsid",
    }
)

# Destinos OV allowlisted (mismo set que handoff).
_OV_DESTINATIONS = frozenset(
    {
        "pagar",
        "my",
        "talon-de-pago",
        "comprar-pack",
        "portabilidad",
        "cuenta",
        "servicio",
        "aviso-de-pago",
        "pay",
        "invoice",
        "payment_slip",
    }
)

_OV_INTENT_MAP = {
    "pay": "pagar",
    "invoice": "my",
    "payment_slip": "talon-de-pago",
}


@dataclass
class TrustedContext:
    """Contexto autorizado reconstruido por el backend. No proviene del LLM."""

    conversation_id: str = ""
    organization_id: str = ""
    abonado_id: str | None = None
    abonado: Any | None = None
    conv: Any | None = None
    ctx: dict[str, Any] = field(default_factory=dict)
    db: Session | None = None
    canal: str = ""
    # Confirmación derivada de STATE / historial backend, nunca del LLM.
    confirmation_received: bool = False
    confirmation_rejected: bool = False
    # Quién originó el request (auditoría).
    decision_name: str = ""
    correlation_id: str = ""


@dataclass
class ActionRequest:
    action: str
    parameters: dict[str, Any] = field(default_factory=dict)
    source: str = "decision"  # decision | playbook | llm_proposal


@dataclass
class ActionResult:
    action: str
    status: ActionStatus
    data: dict[str, Any] = field(default_factory=dict)
    user_message: str = ""
    reason_code: str | None = None
    policy: PolicyVerdict | None = None
    correlation_id: str = ""
    execution_path: str = "runtime"  # runtime | legacy (auditoría)

    def to_log(self, *, conversation_id: str = "", decision_name: str = "") -> dict[str, Any]:
        """Observabilidad mínima sin PII (sin DNI/JWT/MSISDN/secrets)."""
        return {
            "conversation_id": conversation_id or "",
            "decision_name": decision_name or "",
            "action_name": self.action,
            "execution_path": self.execution_path or "runtime",
            "result_status": self.status,
            "reason_code": self.reason_code,
            "correlation_id": self.correlation_id or "",
            "policy": self.policy,
            "timestamp": datetime.now(UTC).isoformat(),
        }


@dataclass
class ActionSpec:
    name: str
    executor: Callable[[ActionRequest, TrustedContext], ActionResult]
    confirmation_required: bool = False
    requires_abonado: bool = True
    idempotency: IdempotencyClass = "SAFE"
    # RISK/UNKNOWN no se ejecutan salvo allow_execution_when_risk=True en policy de decisión.
    allow_when_risk: bool = False
    description: str = ""


# ---------------------------------------------------------------------------
# Registry (allowlist)
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, ActionSpec] = {}


def register_action(spec: ActionSpec) -> None:
    if not spec.name or not callable(spec.executor):
        raise ValueError("ActionSpec inválido")
    _REGISTRY[spec.name] = spec


def get_action(name: str) -> ActionSpec | None:
    return _REGISTRY.get((name or "").strip())


def list_registered_actions() -> list[str]:
    return sorted(_REGISTRY.keys())


def is_registered(name: str) -> bool:
    return (name or "").strip() in _REGISTRY


# ---------------------------------------------------------------------------
# Sanitize / LLM boundary
# ---------------------------------------------------------------------------


def sanitize_parameters(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Elimina claves de autoridad que puedan venir del LLM/input."""
    out: dict[str, Any] = {}
    for k, v in (raw or {}).items():
        key = str(k)
        if key.lower() in _UNTRUSTED_PARAM_KEYS:
            continue
        out[key] = v
    return out


def parse_llm_action_proposal(raw: Any) -> ActionRequest | None:
    """Convierte propuesta LLM en ActionRequest. No ejecuta nada.

    Solo acepta action del allowlist. Descarta campos de autorización.
    """
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("action") or "").strip()
    if not name or not is_registered(name):
        return None
    params = sanitize_parameters(raw.get("parameters") if isinstance(raw.get("parameters"), dict) else {})
    # Ignorar cualquier intento de inyectar identidad
    for k in list(raw.keys()):
        if str(k).lower() in _UNTRUSTED_PARAM_KEYS:
            continue
    return ActionRequest(action=name, parameters=params, source="llm_proposal")


# ---------------------------------------------------------------------------
# Confirmation helpers (STATE, no Facts)
# ---------------------------------------------------------------------------

_CTX_ACTION_KEY = "eko_action"


def get_action_state(ctx: dict[str, Any] | None) -> dict[str, Any]:
    raw = (ctx or {}).get(_CTX_ACTION_KEY)
    return dict(raw) if isinstance(raw, dict) else {}


def set_action_state(ctx: dict[str, Any], **fields: Any) -> None:
    """Persiste eko_action.* en Conversation State (nunca en Facts)."""
    st = get_action_state(ctx)
    st.update(fields)
    # Campos canónicos de auditoría operativa (sin PII).
    if "action" in fields:
        st["last_action"] = fields["action"]
    if "status" in fields:
        st["last_status"] = fields["status"]
        st["last_result"] = fields["status"]
    if fields.get("status") == "confirmation_pending":
        st["confirmation_pending"] = True
        st["input_required"] = False
    elif fields.get("status") == "needs_input":
        st["input_required"] = True
        st["confirmation_pending"] = False
    elif fields.get("status") in (
        "success",
        "already_done",
        "denied",
        "failed",
        "unavailable",
        "rejected",
    ):
        st["confirmation_pending"] = False
        if fields.get("status") != "needs_input":
            st["input_required"] = False
    ctx[_CTX_ACTION_KEY] = st


def confirmation_state_for(
    spec: ActionSpec,
    trusted: TrustedContext,
) -> ConfirmationState:
    if not spec.confirmation_required:
        return "NOT_REQUIRED"
    if trusted.confirmation_rejected:
        return "REJECTED"
    if trusted.confirmation_received:
        return "CONFIRMED"
    # Pendiente explícito en Conversation State
    st = get_action_state(trusted.ctx)
    if st.get("action") == spec.name and st.get("status") == "confirmation_pending":
        return "REQUIRED"
    return "REQUIRED"


# ---------------------------------------------------------------------------
# Policy gate
# ---------------------------------------------------------------------------


@dataclass
class PolicyDecision:
    verdict: PolicyVerdict
    reason_code: str | None = None
    confirmation: ConfirmationState = "NOT_REQUIRED"


def evaluate_policy(request: ActionRequest, trusted: TrustedContext) -> PolicyDecision:
    """Evalúa si la acción puede ejecutarse. No lanza excepciones de flujo."""
    name = (request.action or "").strip()
    if not name or not is_registered(name):
        return PolicyDecision("DENY", "unknown_action")

    spec = _REGISTRY[name]

    if spec.idempotency in ("UNKNOWN",) and not spec.allow_when_risk:
        # UNKNOWN: solo open_OV con allow_when_risk=True en registry
        return PolicyDecision("DENY", "idempotency_unknown")

    if spec.idempotency == "RISK" and not spec.allow_when_risk:
        return PolicyDecision("DENY", "idempotency_risk_blocked")

    if spec.requires_abonado and trusted.abonado is None:
        return PolicyDecision("DENY", "missing_abonado")

    if not trusted.organization_id and spec.requires_abonado:
        # create_ticket / update necesitan org
        if name in ("create_ticket", "update_ticket", "escalate_human", "close_conversation"):
            return PolicyDecision("DENY", "missing_organization")

    # Multi-cuenta: acciones técnicas requieren login seleccionado
    if name in ("run_diagnostic_pppoe", "run_diagnostic_bcm", "run_diagnostic_uisp"):
        ctx = trusted.ctx or {}
        if ctx.get("multi_cuenta_pendiente") and not str(ctx.get("login_seleccionado") or "").strip():
            return PolicyDecision("NEEDS_INPUT", "account_selection_required")
        # También: si hay >1 y sin selección (sin flag aún) — executor revalida

    conf = confirmation_state_for(spec, trusted)
    if conf == "REJECTED":
        return PolicyDecision("DENY", "confirmation_rejected", confirmation=conf)
    if conf == "REQUIRED":
        return PolicyDecision(
            "NEEDS_CONFIRMATION",
            "confirmation_required",
            confirmation=conf,
        )

    return PolicyDecision("ALLOW", None, confirmation=conf)


# ---------------------------------------------------------------------------
# Runtime entry
# ---------------------------------------------------------------------------


def execute_action(request: ActionRequest, trusted: TrustedContext) -> ActionResult:
    """Único punto de ejecución: registry → policy → executor."""
    name = (request.action or "").strip()
    corr = (trusted.correlation_id or "").strip()
    # Re-sanitize siempre
    request = ActionRequest(
        action=name,
        parameters=sanitize_parameters(request.parameters),
        source=request.source or "decision",
    )

    def _stamp(result: ActionResult) -> ActionResult:
        result.correlation_id = corr or result.correlation_id
        result.execution_path = "runtime"
        return result

    if not is_registered(name):
        result = _stamp(
            ActionResult(
                action=name or "unknown",
                status="denied",
                reason_code="unknown_action",
                policy="DENY",
                user_message="Acción no permitida.",
            )
        )
        _log_result(result, trusted)
        return result

    policy = evaluate_policy(request, trusted)
    if policy.verdict == "DENY":
        result = _stamp(
            ActionResult(
                action=name,
                status="denied",
                reason_code=policy.reason_code,
                policy="DENY",
                user_message="No autorizado.",
            )
        )
        _log_result(result, trusted)
        return result

    if policy.verdict == "NEEDS_CONFIRMATION":
        set_action_state(
            trusted.ctx,
            action=name,
            status="confirmation_pending",
            confirmation="REQUIRED",
        )
        result = _stamp(
            ActionResult(
                action=name,
                status="needs_confirmation",
                reason_code=policy.reason_code,
                policy="NEEDS_CONFIRMATION",
                user_message="¿Confirmás que querés continuar con esta acción?",
                data={"confirmation": "REQUIRED"},
            )
        )
        _log_result(result, trusted)
        return result

    if policy.verdict == "NEEDS_INPUT":
        set_action_state(
            trusted.ctx,
            action=name,
            status="needs_input",
            reason=policy.reason_code,
        )
        result = _stamp(
            ActionResult(
                action=name,
                status="needs_input",
                reason_code=policy.reason_code,
                policy="NEEDS_INPUT",
                user_message="Necesito que elijas una cuenta antes de continuar.",
            )
        )
        _log_result(result, trusted)
        return result

    if policy.verdict == "UNAVAILABLE":
        result = _stamp(
            ActionResult(
                action=name,
                status="unavailable",
                reason_code=policy.reason_code,
                policy="UNAVAILABLE",
            )
        )
        _log_result(result, trusted)
        return result

    spec = _REGISTRY[name]
    try:
        result = spec.executor(request, trusted)
    except Exception:
        logger.exception("eko_action_runtime: executor falló action=%s", name)
        result = ActionResult(
            action=name,
            status="failed",
            reason_code="executor_exception",
            policy="ALLOW",
            user_message="No pude completar la acción.",
        )

    result.policy = "ALLOW"
    _stamp(result)
    # Persistir estado de ejecución en Conversation State (no Facts)
    if result.status == "success":
        set_action_state(
            trusted.ctx,
            action=name,
            status="success",
            result_reference=str((result.data or {}).get("ticket_id") or "") or None,
            correlation_id=result.correlation_id or None,
        )
    elif result.status == "already_done":
        set_action_state(
            trusted.ctx,
            action=name,
            status="already_done",
            correlation_id=result.correlation_id or None,
        )
    elif result.status in ("failed", "unavailable", "denied"):
        set_action_state(
            trusted.ctx,
            action=name,
            status=result.status,
            reason=result.reason_code,
            correlation_id=result.correlation_id or None,
        )

    _log_result(result, trusted)
    return result


def _log_result(result: ActionResult, trusted: TrustedContext) -> None:
    try:
        if not result.correlation_id and trusted.correlation_id:
            result.correlation_id = trusted.correlation_id
        if not result.execution_path:
            result.execution_path = "runtime"
        logger.info(
            "eko_action %s",
            result.to_log(
                conversation_id=trusted.conversation_id,
                decision_name=trusted.decision_name,
            ),
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Executors (reusan writers/readers existentes)
# ---------------------------------------------------------------------------


def _exec_send_message(req: ActionRequest, trusted: TrustedContext) -> ActionResult:
    msg = str(req.parameters.get("text") or req.parameters.get("message") or "").strip()
    if not msg:
        return ActionResult(
            action="send_message",
            status="failed",
            reason_code="missing_message",
        )
    return ActionResult(
        action="send_message",
        status="success",
        data={"text": msg},
        user_message=msg,
    )


def _exec_show_balance(req: ActionRequest, trusted: TrustedContext) -> ActionResult:
    from app.services.eco_voice import mensaje_saldo_padron
    from app.services.eko_context import billing_amount_str, build_eko_facts, has_positive_debt

    facts = build_eko_facts(trusted.abonado, db=trusted.db, org_id=trusted.organization_id)
    billing = facts.get("billing") or {}
    if billing.get("status") == "unavailable" and billing.get("balance") is None:
        return ActionResult(
            action="show_balance",
            status="unavailable",
            reason_code="billing_unavailable",
            user_message="No puedo consultar el saldo en este momento.",
            data={"billing_status": "unavailable"},
        )
    amount = billing_amount_str(facts)
    if amount is None:
        return ActionResult(
            action="show_balance",
            status="unavailable",
            reason_code="billing_unavailable",
            user_message="No puedo consultar el saldo en este momento.",
        )
    msg = mensaje_saldo_padron(amount, incluir_ov=False)
    return ActionResult(
        action="show_balance",
        status="success",
        data={
            "amount": amount,
            "billing_status": billing.get("status"),
            "has_positive_debt": has_positive_debt(facts),
        },
        user_message=msg,
    )


def _exec_show_ticket(req: ActionRequest, trusted: TrustedContext) -> ActionResult:
    from app.estate.models import Ticket
    from app.services.abonado_tickets import load_ticket_facts, ticket_pertenece_abonado

    ticket_id = str(req.parameters.get("ticket_id") or "").strip()
    if not ticket_id:
        return ActionResult(
            action="show_ticket",
            status="needs_input",
            reason_code="missing_ticket_id",
            user_message="Indicame el número de ticket.",
        )
    if trusted.db is None or trusted.abonado is None:
        return ActionResult(
            action="show_ticket",
            status="denied",
            reason_code="missing_abonado",
        )
    t = trusted.db.get(Ticket, ticket_id)
    if t is None:
        return ActionResult(
            action="show_ticket",
            status="denied",
            reason_code="ticket_not_found",
            user_message="No encuentro ese ticket.",
        )
    if not ticket_pertenece_abonado(
        trusted.db, trusted.organization_id, trusted.abonado, t
    ):
        return ActionResult(
            action="show_ticket",
            status="denied",
            reason_code="foreign_ticket",
            user_message="No tenés acceso a ese ticket.",
        )
    block = load_ticket_facts(
        trusted.abonado, db=trusted.db, org_id=trusted.organization_id
    )
    item = next((i for i in (block.get("items") or []) if i.get("id") == ticket_id), None)
    return ActionResult(
        action="show_ticket",
        status="success",
        data={"ticket": item or {"id": ticket_id, "state": t.estado}},
        user_message=f"Ticket {ticket_id}: estado {t.estado or '(sin dato)'}.",
    )


def _exec_open_ov(req: ActionRequest, trusted: TrustedContext) -> ActionResult:
    """Links públicos allowlisted. No JSAT/sid/tsid."""
    from app.services.eko_context import load_ov_facts
    from app.services.ov_handoff import public_url_for_destination

    dest_raw = str(
        req.parameters.get("destination") or req.parameters.get("intent") or "pagar"
    ).strip()
    dest = _OV_INTENT_MAP.get(dest_raw, dest_raw)
    if dest not in _OV_DESTINATIONS:
        return ActionResult(
            action="open_OV",
            status="denied",
            reason_code="destination_forbidden",
            user_message="Destino OV no permitido.",
        )
    # Normalizar intents → destination canónico
    dest = _OV_INTENT_MAP.get(dest, dest)

    ov = load_ov_facts(db=trusted.db)
    if not ov.get("available"):
        return ActionResult(
            action="open_OV",
            status="unavailable",
            reason_code="ov_unavailable",
            user_message="La oficina virtual no está disponible ahora.",
        )
    links = ov.get("links") or {}
    key_map = {"pagar": "pay", "my": "invoice", "talon-de-pago": "payment_slip"}
    link_key = key_map.get(dest)
    url = str(links.get(link_key) or "") if link_key else ""
    if not url:
        try:
            url = public_url_for_destination(dest)
        except Exception:
            return ActionResult(
                action="open_OV",
                status="unavailable",
                reason_code="ov_unavailable",
            )
    return ActionResult(
        action="open_OV",
        status="success",
        data={"url": url, "destination": dest, "auth": "external"},
        user_message=f"Podés continuar acá:\n{url}",
    )


def _exec_request_account_selection(req: ActionRequest, trusted: TrustedContext) -> ActionResult:
    trusted.ctx["multi_cuenta_pendiente"] = True
    msg = str(req.parameters.get("message") or "¿Cuál de tus cuentas de internet querés revisar?").strip()
    return ActionResult(
        action="request_account_selection",
        status="success",
        data={"multi_cuenta_pendiente": True},
        user_message=msg,
    )


def _internet_login_count(trusted: TrustedContext) -> int:
    from app.services.eko_context import internet_logins_count

    return internet_logins_count(trusted.db, trusted.abonado)


def _exec_run_diagnostic_pppoe(req: ActionRequest, trusted: TrustedContext) -> ActionResult:
    """Diagnóstico explícito Radius. No corre en build_eko_facts."""
    ctx = trusted.ctx
    login = str(ctx.get("login_seleccionado") or "").strip()
    if ctx.get("multi_cuenta_pendiente") and not login:
        return ActionResult(
            action="run_diagnostic_pppoe",
            status="needs_input",
            reason_code="account_selection_required",
            user_message="Elegí una cuenta antes del diagnóstico.",
        )
    n = _internet_login_count(trusted)
    if n > 1 and not login:
        ctx["multi_cuenta_pendiente"] = True
        return ActionResult(
            action="run_diagnostic_pppoe",
            status="needs_input",
            reason_code="account_selection_required",
            user_message="Tenés más de una cuenta. ¿Cuál querés que revise?",
        )
    if trusted.db is None or trusted.abonado is None:
        return ActionResult(
            action="run_diagnostic_pppoe",
            status="unavailable",
            reason_code="missing_abonado",
        )
    try:
        from app.services.conexion_pppoe import (
            consultar_conexion_pppoe,
            triage_pppoe_para_prompt,
        )

        dni = str(getattr(trusted.abonado, "dni", "") or "")
        cn = str(getattr(trusted.abonado, "client_number", "") or "")
        estado = consultar_conexion_pppoe(
            dni=dni,
            client_number=cn,
            login=login,
            db=trusted.db,
        )
        if (estado.error or "").strip() and estado.sesion is None and not estado.servicio:
            return ActionResult(
                action="run_diagnostic_pppoe",
                status="unavailable",
                reason_code="radius_unavailable",
                data={"error": (estado.error or "")[:120]},
                user_message="No pude consultar el estado de conexión ahora.",
            )
        extras: dict[str, str] = {
            "pppoe_resumen": estado.resumen_prompt() if hasattr(estado, "resumen_prompt") else "",
            "pppoe_triage": triage_pppoe_para_prompt(estado),
        }
        if estado.servicio:
            extras["pppoe_login"] = str(estado.servicio.login or "")
        if estado.sesion:
            if estado.online is True:
                extras["pppoe_estado"] = "conectado"
            elif estado.online is False:
                extras["pppoe_estado"] = "desconectado"
        for k, v in extras.items():
            if str(v or "").strip():
                ctx[k] = str(v).strip()
        ctx["pppoe_informado"] = True
        resumen = extras.get("pppoe_resumen") or ""
        return ActionResult(
            action="run_diagnostic_pppoe",
            status="success",
            data={
                "pppoe_resumen": resumen,
                "observation_keys": list(extras.keys()),
                "_estado": estado,  # in-process only; avoids re-probe in canal_pppoe
            },
            user_message=resumen or "Revisé tu conexión PPPoE.",
        )
    except Exception:
        logger.exception("run_diagnostic_pppoe falló")
        return ActionResult(
            action="run_diagnostic_pppoe",
            status="unavailable",
            reason_code="radius_unavailable",
            user_message="No pude consultar el estado de conexión ahora.",
        )


def _exec_run_diagnostic_bcm(req: ActionRequest, trusted: TrustedContext) -> ActionResult:
    ctx = trusted.ctx
    if ctx.get("multi_cuenta_pendiente") and not str(ctx.get("login_seleccionado") or "").strip():
        return ActionResult(
            action="run_diagnostic_bcm",
            status="needs_input",
            reason_code="account_selection_required",
        )
    try:
        from app.services.conexion_bcm import contexto_bcm_para_abonado

        extras = contexto_bcm_para_abonado(trusted.abonado, db=trusted.db) or {}
        for k, v in extras.items():
            if str(v or "").strip():
                ctx[k] = str(v).strip()
        return ActionResult(
            action="run_diagnostic_bcm",
            status="success",
            data={"bcm_resumen": extras.get("bcm_resumen") or ""},
            user_message=extras.get("bcm_resumen") or "Revisé el estado óptico.",
        )
    except Exception:
        logger.exception("run_diagnostic_bcm falló")
        return ActionResult(
            action="run_diagnostic_bcm",
            status="unavailable",
            reason_code="bcm_unavailable",
            user_message="No pude consultar el estado de la ONU ahora.",
        )


def _exec_run_diagnostic_uisp(req: ActionRequest, trusted: TrustedContext) -> ActionResult:
    ctx = trusted.ctx
    if ctx.get("multi_cuenta_pendiente") and not str(ctx.get("login_seleccionado") or "").strip():
        return ActionResult(
            action="run_diagnostic_uisp",
            status="needs_input",
            reason_code="account_selection_required",
        )
    try:
        from app.services.conexion_uisp import contexto_uisp_para_abonado

        login = str(ctx.get("login_seleccionado") or ctx.get("pppoe_login") or "")
        extras = contexto_uisp_para_abonado(trusted.abonado, login=login, db=trusted.db) or {}
        for k, v in extras.items():
            if str(v or "").strip():
                ctx[k] = str(v).strip()
        return ActionResult(
            action="run_diagnostic_uisp",
            status="success",
            data={"uisp_resumen": extras.get("uisp_resumen") or ""},
            user_message=extras.get("uisp_resumen") or "Revisé el estado de la antena.",
        )
    except Exception:
        logger.exception("run_diagnostic_uisp falló")
        return ActionResult(
            action="run_diagnostic_uisp",
            status="unavailable",
            reason_code="uisp_unavailable",
            user_message="No pude consultar el estado de la antena ahora.",
        )


def _exec_create_ticket(req: ActionRequest, trusted: TrustedContext) -> ActionResult:
    """Gate + reuso de _crear_ticket_n2. Confirmation debe venir del TrustedContext."""
    from app.services.canal_abonado import _crear_ticket_n2

    if trusted.conv is None or trusted.db is None:
        return ActionResult(
            action="create_ticket",
            status="failed",
            reason_code="missing_conversation",
        )
    # Idempotencia: ticket ya ligado
    existing = str(getattr(trusted.conv, "ticket_id", "") or "").strip()
    if existing:
        return ActionResult(
            action="create_ticket",
            status="already_done",
            data={"ticket_id": existing},
            reason_code="ticket_already_exists",
            user_message=f"Ya tenés el ticket {existing} en curso.",
        )
    motivo = str(req.parameters.get("motivo") or req.parameters.get("reason") or "Escalamiento N2").strip()
    intencion = str(
        req.parameters.get("intencion")
        or (trusted.ctx or {}).get("intencion")
        or ""
    ).strip()
    try:
        tid = _crear_ticket_n2(
            trusted.db,
            trusted.organization_id,
            trusted.conv,
            trusted.abonado,
            motivo,
            intencion=intencion,
            paso_idx=int((trusted.ctx or {}).get("paso_idx") or 0),
            ctx=trusted.ctx,
        )
    except Exception:
        logger.exception("create_ticket falló")
        return ActionResult(
            action="create_ticket",
            status="failed",
            reason_code="ticket_db_failure",
            user_message="No pude crear el ticket ahora.",
        )
    return ActionResult(
        action="create_ticket",
        status="success",
        data={"ticket_id": tid},
        user_message=f"Listo, generé el ticket {tid}. Un agente va a continuar.",
    )


def _exec_update_ticket(req: ActionRequest, trusted: TrustedContext) -> ActionResult:
    from app.estate.models import Ticket
    from app.services.abonado_tickets import ticket_pertenece_abonado
    from app.services.canal_abonado import _append_evidencia_ticket

    ticket_id = str(req.parameters.get("ticket_id") or getattr(trusted.conv, "ticket_id", "") or "").strip()
    nota = str(req.parameters.get("nota") or req.parameters.get("note") or "").strip()
    if not ticket_id or not nota:
        return ActionResult(
            action="update_ticket",
            status="needs_input",
            reason_code="missing_ticket_or_note",
        )
    if trusted.db is None or trusted.abonado is None:
        return ActionResult(action="update_ticket", status="denied", reason_code="missing_abonado")
    t = trusted.db.get(Ticket, ticket_id)
    if t is None or not ticket_pertenece_abonado(
        trusted.db, trusted.organization_id, trusted.abonado, t
    ):
        return ActionResult(
            action="update_ticket",
            status="denied",
            reason_code="foreign_ticket",
        )
    _append_evidencia_ticket(trusted.db, trusted.organization_id, ticket_id, nota)
    return ActionResult(
        action="update_ticket",
        status="success",
        data={"ticket_id": ticket_id},
        user_message="Actualicé la información del ticket.",
    )


def _exec_escalate_human(req: ActionRequest, trusted: TrustedContext) -> ActionResult:
    if trusted.conv is None or trusted.db is None:
        return ActionResult(
            action="escalate_human",
            status="failed",
            reason_code="missing_conversation",
        )
    conv = trusted.conv
    if (conv.estado or "") in ("espera_agente", "con_agente"):
        return ActionResult(
            action="escalate_human",
            status="already_done",
            data={"estado": conv.estado},
            user_message="Ya estás en espera con un agente.",
        )
    prev = conv.estado or ""
    conv.estado = "espera_agente"
    trusted.db.commit()
    try:
        from app.services.handoff_notify import notify_espera_agente

        notify_espera_agente(trusted.db, conv, prev_estado=prev)
    except Exception:
        logger.debug("notify escalate falló", exc_info=True)
    return ActionResult(
        action="escalate_human",
        status="success",
        data={"estado": "espera_agente"},
        user_message="Te derivo con un agente. En breve te responden.",
    )


def _exec_close_conversation(req: ActionRequest, trusted: TrustedContext) -> ActionResult:
    if trusted.conv is None or trusted.db is None:
        return ActionResult(
            action="close_conversation",
            status="failed",
            reason_code="missing_conversation",
        )
    conv = trusted.conv
    if (conv.estado or "") == "cerrado":
        return ActionResult(
            action="close_conversation",
            status="already_done",
            data={"estado": "cerrado"},
        )
    conv.estado = "cerrado"
    trusted.db.commit()
    return ActionResult(
        action="close_conversation",
        status="success",
        data={"estado": "cerrado"},
        user_message="Cerramos la consulta. Si necesitás algo más, escribinos.",
    )


def bootstrap_registry() -> None:
    """Registra el allowlist. Idempotente."""
    if _REGISTRY:
        return
    specs = [
        ActionSpec("send_message", _exec_send_message, requires_abonado=False, idempotency="SAFE"),
        ActionSpec("show_balance", _exec_show_balance, idempotency="SAFE"),
        ActionSpec("show_ticket", _exec_show_ticket, idempotency="SAFE"),
        ActionSpec(
            "open_OV",
            _exec_open_ov,
            requires_abonado=False,
            idempotency="UNKNOWN",
            allow_when_risk=True,  # solo links públicos allowlisted
            description="OV public links only; no JSAT",
        ),
        ActionSpec(
            "request_account_selection",
            _exec_request_account_selection,
            idempotency="SAFE",
        ),
        ActionSpec(
            "run_diagnostic_pppoe",
            _exec_run_diagnostic_pppoe,
            idempotency="RISK",
            allow_when_risk=True,  # explícito; policy bloquea sin selección
        ),
        ActionSpec(
            "run_diagnostic_bcm",
            _exec_run_diagnostic_bcm,
            idempotency="RISK",
            allow_when_risk=True,
        ),
        ActionSpec(
            "run_diagnostic_uisp",
            _exec_run_diagnostic_uisp,
            idempotency="RISK",
            allow_when_risk=True,
        ),
        ActionSpec(
            "create_ticket",
            _exec_create_ticket,
            confirmation_required=True,
            idempotency="PROTECTED",
        ),
        ActionSpec(
            "update_ticket",
            _exec_update_ticket,
            idempotency="PROTECTED",
        ),
        ActionSpec(
            "escalate_human",
            _exec_escalate_human,
            confirmation_required=True,
            idempotency="PROTECTED",
        ),
        ActionSpec(
            "close_conversation",
            _exec_close_conversation,
            confirmation_required=True,
            idempotency="PROTECTED",
        ),
    ]
    for s in specs:
        register_action(s)


# Bootstrap al importar
bootstrap_registry()
