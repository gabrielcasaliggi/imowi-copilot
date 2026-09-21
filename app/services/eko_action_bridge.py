"""Bridge Action Runtime ↔ canal N1 (Fases 4C/4D).

Coexistencia: si el feature gate cubre la acción → Runtime solamente.
Si no → caller usa Legacy. Nunca Runtime + Legacy del mismo side effect.

Confirmation trusted: solo input/estado conversacional (usuario_confirmo_ticket,
USER_CONFIRM_ACTION, rechazo explícito). Nunca auto_confirmado ni LLM.

4D: correlation_id + execution_path en logs; sin PII.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.config import ACTION_RUNTIME_ACTIONS, ACTION_RUNTIME_ENABLED
from app.services.eko_action_runtime import (
    ActionRequest,
    ActionResult,
    TrustedContext,
    execute_action,
    get_action_state,
    sanitize_parameters,
    set_action_state,
)

logger = logging.getLogger("operations_hub")


def action_runtime_master_enabled() -> bool:
    return bool(ACTION_RUNTIME_ENABLED)


def action_runtime_covers(action: str) -> bool:
    """True si esta acción debe ejecutarse vía Runtime (no Legacy)."""
    if not ACTION_RUNTIME_ENABLED:
        return False
    name = (action or "").strip()
    return name in ACTION_RUNTIME_ACTIONS


def resolve_user_confirmation(
    *,
    historial: list[dict] | None = None,
    ctx: dict[str, Any] | None = None,
    intencion: str = "",
    action: str = "",
    texto: str = "",
) -> tuple[bool, bool]:
    """Deriva confirmación confiable del usuario.

    Returns:
        (confirmation_received, confirmation_rejected)

    Fuentes trusted:
    - usuario_confirmo_ticket(historial) — afirmación del usuario en canal
    - Conversation State tras confirmation_pending + afirmación en ``texto``
    - rechazo explícito (no / cancelar) tras confirmation_pending

    NO usa:
    - auto_confirmado del decision_engine
    - campos del LLM / ActionRequest
    """
    ctx = ctx if isinstance(ctx, dict) else {}
    historial = list(historial or [])
    action_n = (action or "").strip()
    st = get_action_state(ctx)

    # Rechazo tras pending
    t = (texto or "").strip().lower()
    pending = (
        st.get("status") == "confirmation_pending"
        and (not action_n or st.get("action") == action_n)
    )
    if pending and t:
        if t in ("no", "nop", "nel", "cancelar", "cancelá", "cancela", "mejor no"):
            return False, True
        # Afirmación corta sobre pending
        if t in ("si", "sí", "ok", "dale", "bueno", "confirmo", "de acuerdo", "sí quiero", "si quiero"):
            return True, False

    # Historial: confirmación explícita de ticket (solo para create_ticket / escalate)
    if action_n in ("create_ticket", "escalate_human", ""):
        try:
            from app.domain.conversacion import usuario_confirmo_ticket

            if usuario_confirmo_ticket(historial, intencion):
                return True, False
        except Exception:
            logger.debug("resolve_user_confirmation historial falló", exc_info=True)

    return False, False


def build_trusted_context(
    *,
    db: Session | None,
    org_id: str,
    conv: Any | None,
    abonado: Any | None,
    ctx: dict[str, Any] | None,
    canal: str = "",
    decision_name: str = "",
    historial: list[dict] | None = None,
    action: str = "",
    texto: str = "",
    confirmation_received: bool | None = None,
    confirmation_rejected: bool | None = None,
    correlation_id: str = "",
) -> TrustedContext:
    """Reconstruye TrustedContext desde backend. Ignora claims del LLM."""
    ctx = ctx if isinstance(ctx, dict) else {}
    if confirmation_received is None or confirmation_rejected is None:
        rec, rej = resolve_user_confirmation(
            historial=historial,
            ctx=ctx,
            intencion=str(ctx.get("intencion") or ""),
            action=action,
            texto=texto,
        )
        if confirmation_received is None:
            confirmation_received = rec
        if confirmation_rejected is None:
            confirmation_rejected = rej

    abo_id = None
    if abonado is not None:
        abo_id = str(getattr(abonado, "id", "") or "") or None
    elif conv is not None:
        abo_id = str(getattr(conv, "abonado_id", "") or "") or None

    return TrustedContext(
        conversation_id=str(getattr(conv, "id", "") or ""),
        organization_id=str(org_id or ""),
        abonado_id=abo_id,
        abonado=abonado,
        conv=conv,
        ctx=ctx,
        db=db,
        canal=canal or str(getattr(conv, "canal", "") or ""),
        confirmation_received=bool(confirmation_received),
        confirmation_rejected=bool(confirmation_rejected),
        decision_name=decision_name or "",
        correlation_id=correlation_id or str(uuid.uuid4()),
    )


def dispatch_runtime(
    action: str,
    *,
    db: Session | None,
    org_id: str,
    conv: Any | None,
    abonado: Any | None,
    ctx: dict[str, Any],
    canal: str = "",
    decision_name: str = "",
    parameters: dict[str, Any] | None = None,
    historial: list[dict] | None = None,
    texto: str = "",
    source: str = "decision",
) -> ActionResult | None:
    """Ejecuta vía Runtime si el gate cubre la acción.

    Returns:
        ActionResult si Runtime manejó la acción (caller NO debe ejecutar Legacy).
        None si Legacy debe manejar (feature off o acción no cubierta).
    """
    name = (action or "").strip()
    if not action_runtime_covers(name):
        return None

    corr = str(uuid.uuid4())
    trusted = build_trusted_context(
        db=db,
        org_id=org_id,
        conv=conv,
        abonado=abonado,
        ctx=ctx,
        canal=canal,
        decision_name=decision_name,
        historial=historial,
        action=name,
        texto=texto,
        correlation_id=corr,
    )
    req = ActionRequest(
        action=name,
        parameters=sanitize_parameters(parameters),
        source=source if source in ("decision", "playbook", "llm_proposal") else "decision",
    )
    result = execute_action(req, trusted)
    # Persistencia mínima de traza en STATE (sin PII)
    set_action_state(
        ctx,
        last_action=name,
        last_status=result.status,
        last_result=result.status,
        last_reason=result.reason_code,
        last_decision=decision_name or "",
        correlation_id=result.correlation_id or corr,
        execution_path="runtime",
    )
    logger.info(
        "eko_action_bridge decision=%s action=%s status=%s reason=%s "
        "path=runtime corr=%s",
        decision_name,
        name,
        result.status,
        result.reason_code,
        result.correlation_id or corr,
    )
    return result


def confirmation_prompt_for(action: str) -> str:
    if action == "create_ticket":
        return (
            "Para escalar con un agente y generar un ticket, confirmame con un «sí». "
            "Si preferís seguir en el chat, decime «no»."
        )
    if action == "escalate_human":
        return "¿Confirmás que querés hablar con un agente? Respondé «sí» o «no»."
    if action == "close_conversation":
        return "¿Cerramos la consulta? Respondé «sí» o «no»."
    return "¿Confirmás esta acción? Respondé «sí» o «no»."


def apply_needs_confirmation_to_ctx(ctx: dict[str, Any], result: ActionResult) -> str:
    """Persiste pending en STATE y devuelve mensaje al usuario."""
    set_action_state(
        ctx,
        action=result.action,
        status="confirmation_pending",
        confirmation="REQUIRED",
        correlation_id=result.correlation_id or None,
    )
    return result.user_message or confirmation_prompt_for(result.action)
