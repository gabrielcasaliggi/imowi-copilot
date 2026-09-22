"""Journey Orchestration — Fase 5 Agentic Customer Operations.

Orquestación determinística de capabilities existentes.
NO es un nuevo Action Runtime / registry / policy engine / conversation motor.

LLM = interpret / propose / compose — nunca authority ni side effects.

State vive en ConversationState (ctx["eko_journey"]), no en Facts.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.services.eko_action_bridge import (
    dispatch_runtime,
    resolve_user_confirmation,
)
from app.services.eko_action_runtime import ActionResult, is_registered
from app.services.eko_capability_contract import build_capability

logger = logging.getLogger("operations_hub")

JOURNEY_KEY = "eko_journey"

JourneyName = Literal[
    "internet_sin_conectividad",
    "billing_self_service",
    "billing_consulta",  # alias legado → normaliza a billing_self_service
    "ticket_consulta",
    "service_catalog",
    "installation_status",
]

StepName = Literal[
    "start",
    "identity",
    "service_selection",
    "diagnostic",
    "interpret",
    "decide",
    "confirm_action",
    "respond",
    "done",
    "switched",
]


@dataclass
class JourneyTurn:
    """Resultado de un turno de Journey (no es ActionResult)."""

    handled: bool
    user_message: str = ""
    mode: str = "bot"
    journey: str = ""
    step: str = ""
    intent: str = ""
    domain: str = ""
    action: str = ""
    action_status: str = ""
    reason_code: str | None = None
    correlation_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Intent detection (deterministic; reuses phrasing already in product)
# ---------------------------------------------------------------------------

_CONNECTIVITY_PHRASES = (
    "no tengo internet",
    "sin internet",
    "estoy sin servicio",
    "no navega",
    "no navego",
    "no tengo conexion",
    "no tengo conexión",
    "se cayo internet",
    "se cayó internet",
    "internet no funciona",
    "no anda internet",
    "no funciona internet",
    "me quede sin internet",
    "me quedé sin internet",
    "sin conexion",
    "sin conexión",
    "internet cortado",
)

_BILLING_PHRASES = (
    "cuanto debo",
    "cuánto debo",
    "tengo que pagar",
    "tengo deuda",
    "donde pago",
    "dónde pago",
    "como pago",
    "cómo pago",
    "quiero pagar",
    "consultar saldo",
    "mi saldo",
    "cual es mi saldo",
    "cuál es mi saldo",
    "deuda",
    "mi factura",
    "la factura",
    "ver factura",
    "ver mi factura",
    "necesito la factura",
    "necesito mi factura",
    "factura pendiente",
    "que factura",
    "qué factura",
    "talon",
    "talón",
    "cuando vence",
    "cuándo vence",
    "vencimiento",
    "que pague",
    "qué pagué",
    "que pagué",
    "pagos hice",
    "historial de pago",
    "mis pagos",
)

# 2.2D: intención de seguimiento de instalación (sin fuente factual → honest unavailable)
_INSTALLATION_PHRASES = (
    "cuando me instalan",
    "cuándo me instalan",
    "cuando me instalan",
    "como esta mi instalacion",
    "cómo está mi instalación",
    "como está mi instalación",
    "estado de mi instalacion",
    "estado de mi instalación",
    "estado de la instalacion",
    "estado de la instalación",
    "que paso con mi instalacion",
    "qué pasó con mi instalación",
    "tengo turno de instalacion",
    "tengo turno de instalación",
    "turno de instalacion",
    "turno de instalación",
    "cuando viene el tecnico",
    "cuándo viene el técnico",
    "cuando viene el técnico",
    "ya esta programada la instalacion",
    "ya está programada la instalación",
    "programada la instalacion",
    "programada la instalación",
    "seguimiento de instalacion",
    "seguimiento de instalación",
    "mi instalacion",
    "mi instalación",
)

_JOURNEY_ALIAS = {
    "billing_consulta": "billing_self_service",
}


def _canonical_journey(name: str) -> str:
    n = (name or "").strip()
    return _JOURNEY_ALIAS.get(n, n)

_TICKET_PHRASES = (
    "estado del ticket",
    "mi ticket",
    "mi reclamo",
    "que paso con mi reclamo",
    "qué pasó con mi reclamo",
    "ya esta solucionado",
    "ya está solucionado",
    "como va el ticket",
    "cómo va el ticket",
)

# Catálogo comercial (Eko 2.2A). Antes que billing genérico con "servicio".
_SERVICE_CATALOG_PHRASES = (
    "que servicios tengo",
    "qué servicios tengo",
    "que servicios tengo contratados",
    "qué servicios tengo contratados",
    "servicios tengo contratados",
    "servicios contratados",
    "mis servicios",
    "mostrame mis servicios",
    "mostrame los servicios",
    "mostrar mis servicios",
    "lista de servicios",
    "listado de servicios",
    "que tengo contratado",
    "qué tengo contratado",
    "servicios activos",
    "que servicios tengo activos",
    "qué servicios tengo activos",
    "que servicios tengo con",
    "qué servicios tengo con",
)


def journeys_enabled(*, canal: str = "", org_id: str = "") -> bool:
    """Master + allowlists opcionales (Fase 7).

    - Master OFF → siempre False.
    - Master ON + allowlists vacías → True (global; no preferido en primer rollout).
    - Master ON + CHANNELS/ORG_IDS → solo segmentos listados.
    """
    from app import config as app_config

    if not bool(getattr(app_config, "EKO_JOURNEYS_ENABLED", False)):
        return False
    channels = getattr(app_config, "EKO_JOURNEYS_CHANNELS", frozenset()) or frozenset()
    orgs = getattr(app_config, "EKO_JOURNEYS_ORG_IDS", frozenset()) or frozenset()
    if channels:
        c = (canal or "").strip().lower()
        # alias wa → whatsapp
        if c == "wa":
            c = "whatsapp"
        if c not in channels:
            return False
    if orgs:
        if (org_id or "").strip() not in orgs:
            return False
    return True


def activation_snapshot() -> dict[str, object]:
    """Resumen operable de flags Journeys vs Runtime (sin secretos)."""
    from app import config as app_config
    from app.services.eko_action_bridge import action_runtime_master_enabled
    from app.services.eko_action_coverage import rollout_snapshot

    return {
        "eko_journeys_enabled": bool(getattr(app_config, "EKO_JOURNEYS_ENABLED", False)),
        "eko_journeys_channels": sorted(
            getattr(app_config, "EKO_JOURNEYS_CHANNELS", frozenset()) or []
        ),
        "eko_journeys_org_ids": sorted(
            getattr(app_config, "EKO_JOURNEYS_ORG_IDS", frozenset()) or []
        ),
        "action_runtime_enabled": action_runtime_master_enabled(),
        "runtime_rollout": rollout_snapshot(),
        "mutating_actions_default_off": True,
    }


def get_journey(ctx: dict[str, Any] | None) -> dict[str, Any]:
    raw = (ctx or {}).get(JOURNEY_KEY)
    return dict(raw) if isinstance(raw, dict) else {}


def set_journey(ctx: dict[str, Any], **fields: Any) -> None:
    st = get_journey(ctx)
    st.update(fields)
    # Campos canónicos de trazabilidad (sin PII)
    if "name" in fields:
        st["journey"] = fields["name"]
    if "step" in fields:
        st["current_step"] = fields["step"]
    ctx[JOURNEY_KEY] = st


def clear_journey(ctx: dict[str, Any]) -> None:
    ctx.pop(JOURNEY_KEY, None)


def detect_journey_name(texto: str) -> JourneyName | None:
    t = (texto or "").lower().strip()
    if not t:
        return None
    # Billing / ticket / catálogo antes que connectivity genérico
    if any(p in t for p in _TICKET_PHRASES):
        return "ticket_consulta"
    # 2.2D instalación: honest unavailable (sin agenda/órdenes)
    if any(p in t for p in _INSTALLATION_PHRASES):
        return "installation_status"
    if any(p in t for p in _SERVICE_CATALOG_PHRASES):
        return "service_catalog"
    # Re-entry a Internet ("¿y el Internet?") gana sobre selección lingüística
    if _is_resume_connectivity(t):
        return "internet_sin_conectividad"
    if any(p in t for p in _BILLING_PHRASES) and "internet" not in t:
        return "billing_self_service"
    if any(p in t for p in _CONNECTIVITY_PHRASES):
        return "internet_sin_conectividad"
    # Selección lingüística (después de connectivity para no robar "sin internet")
    try:
        from app.services.eko_service_selection import looks_like_selection_utterance

        if looks_like_selection_utterance(t):
            return "service_catalog"
    except Exception:
        pass
    if any(p in t for p in _BILLING_PHRASES):
        return "billing_self_service"
    return None


def _domain_for(name: JourneyName | str) -> str:
    n = _canonical_journey(str(name))
    if n == "billing_self_service":
        return "billing"
    if n == "ticket_consulta":
        return "support"
    if n == "service_catalog":
        return "services"
    if n == "installation_status":
        return "services"
    return "internet"


def _intent_for(name: JourneyName | str) -> str:
    n = _canonical_journey(str(name))
    if n == "billing_self_service":
        return "facturacion"
    if n == "ticket_consulta":
        return "estado_ticket"
    if n == "service_catalog":
        return "consulta_servicios"
    if n == "installation_status":
        return "seguimiento_instalacion"
    return "internet"


def _new_journey(name: JourneyName, *, correlation_id: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "journey": name,
        "step": "start",
        "current_step": "start",
        "domain": _domain_for(name),
        "intent": _intent_for(name),
        "selected_service": "",
        "diagnostic_started": False,
        "last_diagnostic_result": "",
        "pending_confirmation": False,
        "confirmation_correlation": "",
        "last_action": "",
        "last_action_status": "",
        "next_required_input": "",
        "asked_selection": False,
        "selection_options": [],
        "last_user_message": "",
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "previous_journey": "",
    }


def _clear_stale_confirmation(ctx: dict[str, Any]) -> None:
    """Invalida confirmaciones pendientes al cambiar de dominio/journey (C10)."""
    from app.services.eko_action_runtime import get_action_state, set_action_state

    set_journey(
        ctx,
        pending_confirmation=False,
        confirmation_correlation="",
    )
    st = get_action_state(ctx)
    if st.get("status") == "confirmation_pending":
        set_action_state(
            ctx,
            action=str(st.get("action") or ""),
            status="cleared_on_domain_switch",
            confirmation="CLEARED",
        )


def _is_resume_connectivity(texto: str) -> bool:
    t = (texto or "").lower().strip()
    if not t:
        return False
    cues = (
        "y el internet",
        "volvamos al internet",
        "volvamos con internet",
        "bueno volvamos al internet",
        "bueno, volvamos al internet",
        "seguir con internet",
        "lo del internet",
        "buenos y el internet",
        "bueno y el internet",
        "bueno, ¿y el internet",
        "bueno, y el internet",
    )
    return any(c in t for c in cues) or (
        t in ("y el internet?", "¿y el internet?", "¿y el internet")
    )


def _wants_rediagnose(texto: str) -> bool:
    """Pedido explícito de volver a diagnosticar (no bastan frases LLM)."""
    t = (texto or "").lower().strip()
    if not t:
        return False
    cues = (
        "volvé a revisar",
        "volve a revisar",
        "vuelve a revisar",
        "revisá de nuevo",
        "revisa de nuevo",
        "chequeá de nuevo",
        "chequea de nuevo",
        "volvé a chequear",
        "volve a chequear",
        "diagnóstico de nuevo",
        "diagnostico de nuevo",
        "otra vez la conexión",
        "otra vez la conexion",
        "probá de nuevo la línea",
        "proba de nuevo la linea",
        "revisá otra vez",
        "revisa otra vez",
    )
    return any(c in t for c in cues)


def _record_action(ctx: dict, st: dict, ar: ActionResult | None, *, action: str) -> None:
    status = ar.status if ar else "unavailable"
    set_journey(
        ctx,
        last_action=action,
        last_action_status=status,
        correlation_id=st.get("correlation_id") or (ar.correlation_id if ar else ""),
    )
    if ar is not None:
        set_journey(ctx, last_reason=ar.reason_code or "")


def _capability_allowed(name: str) -> bool:
    return is_registered(name) and build_capability(name) is not None


# ---------------------------------------------------------------------------
# Transitions from ActionResult
# ---------------------------------------------------------------------------


def transition_for_result(status: str) -> str:
    """Mapeo explícito ActionResult → siguiente paso lógico."""
    s = (status or "").strip()
    if s == "needs_input":
        return "service_selection"
    if s == "needs_confirmation":
        return "confirm_action"
    if s in ("denied", "failed", "unavailable"):
        return "respond"
    if s in ("success", "already_done"):
        return "interpret"
    return "respond"


def _confirmation_is_live(ctx: dict[str, Any]) -> bool:
    """True solo si hay confirmación pendiente del journey de connectivity actual."""
    st = get_journey(ctx)
    if st.get("name") != "internet_sin_conectividad":
        return False
    if not st.get("pending_confirmation"):
        return False
    corr = str(st.get("confirmation_correlation") or "")
    journey_corr = str(st.get("correlation_id") or "")
    if corr and journey_corr and corr != journey_corr:
        return False
    if st.get("step") not in ("confirm_action", "decide"):
        return False
    return True


def _mark_confirmation_pending(ctx: dict[str, Any], *, corr: str) -> None:
    set_journey(
        ctx,
        pending_confirmation=True,
        step="confirm_action",
        next_required_input="confirmation",
        confirmation_correlation=corr,
    )


# ---------------------------------------------------------------------------
# Connectivity journey
# ---------------------------------------------------------------------------


def _msg_selection() -> str:
    return (
        "Veo que tenés más de un servicio de Internet. "
        "¿Con cuál estás teniendo el problema? Indicame el usuario de conexión "
        "(por ejemplo el que empieza con INT)."
    )


def _interpret_pppoe(ar: ActionResult) -> tuple[str, str]:
    """(observation_code, user_safe_message). No inventa fallas de fibra/router."""
    data = ar.data or {}
    # 2.2C: resultado portal_connectivity (precedencia canónica)
    conn = data.get("connectivity") if isinstance(data.get("connectivity"), dict) else None
    if conn is not None or data.get("connectivity_status") or data.get("reason_code"):
        status = str(
            (conn or {}).get("status")
            or data.get("connectivity_status")
            or ""
        ).strip()
        reason = str(
            (conn or {}).get("reason_code")
            or data.get("reason_code")
            or ar.reason_code
            or ""
        ).strip()
        msg = str(
            ar.user_message
            or (conn or {}).get("message")
            or ""
        ).strip()
        if reason == "service_selection_required" or ar.status == "needs_input":
            return "needs_selection", msg or _msg_selection()
        if reason == "incident_active" or status == "outage":
            return "outage", msg or "Detectamos una incidencia que puede afectar tu servicio."
        if reason == "access_link_down":
            return "access_link_down", msg or "Detectamos un problema en tu acceso a Internet."
        if reason == "no_session":
            return "no_session", msg or (
                "Tu acceso responde, pero no hay una sesión activa en este momento."
            )
        if reason == "link_quality_poor":
            return "link_quality_poor", msg or (
                "Tu acceso muestra condiciones deficientes."
            )
        if status == "operational" and not reason:
            return "operational", msg or "No registramos problemas en tu acceso a Internet."
        if status == "unknown" or reason in (
            "sources_unavailable",
            "insufficient_data",
            "service_not_diagnosticable",
        ):
            return "unknown", msg or "No pudimos verificar tu servicio en este momento."
        if msg:
            return reason or status or "connectivity_observed", msg
        return "unknown", "Revisé tu línea pero no tengo un resultado completo ahora."

    estado = data.get("_estado")
    online = None
    if estado is not None:
        online = bool(getattr(estado, "online", None))
        if online is None and getattr(estado, "sesion", None) is not None:
            online = bool(getattr(estado.sesion, "online", False))
    if ar.status == "unavailable":
        return "pppoe_unavailable", (
            ar.user_message
            or "No pude consultar el estado de tu conexión ahora. ¿Probamos de nuevo o preferís un agente?"
        )
    if ar.status == "failed":
        return "pppoe_failed", (
            ar.user_message or "Hubo un error al consultar la conexión. ¿Seguimos o preferís un agente?"
        )
    if ar.status == "needs_input":
        return "needs_selection", ar.user_message or _msg_selection()
    if ar.status == "denied":
        return "denied", ar.user_message or "No puedo ejecutar ese diagnóstico."
    if online is True:
        return "pppoe_session_up", (
            "Veo una sesión de conexión activa en tu línea. "
            "Si igual no navegás, puede ser algo en el router o Wi‑Fi de tu casa. "
            "¿Querés que te guíe con unos chequeos, o preferís hablar con un agente?"
        )
    if online is False:
        return "pppoe_session_down", (
            "No veo una sesión de conexión activa en este momento. "
            "¿Confirmás que querés que derive el caso a un agente con un ticket?"
        )
    # success without clear online flag
    msg = (ar.user_message or "").strip()
    if msg:
        return "pppoe_observed", msg
    return "pppoe_unknown", (
        "Revisé tu línea pero no tengo un resultado completo ahora. "
        "¿Preferís que te derive con un agente?"
    )


def _advance_connectivity(
    *,
    db: Session | None,
    org_id: str,
    conv: Any,
    abonado: Any | None,
    texto: str,
    ctx: dict[str, Any],
    canal: str,
) -> JourneyTurn:
    st = get_journey(ctx)
    corr = str(st.get("correlation_id") or uuid.uuid4())
    set_journey(ctx, correlation_id=corr, intent="internet", domain="internet")

    # Identity
    if abonado is None:
        set_journey(ctx, step="identity", next_required_input="identity")
        return JourneyTurn(
            handled=True,
            user_message="Para revisar tu Internet necesito identificarte. ¿Me pasás tu DNI?",
            journey="internet_sin_conectividad",
            step="identity",
            intent="internet",
            domain="internet",
            correlation_id=corr,
        )

    # Sin servicio de Internet fijo en padrón → no probe técnico (piloto Batán)
    n_logins = _login_count(db, abonado)
    if n_logins <= 0:
        msg = (
            "En tu cuenta no veo un servicio de Internet fijo (fibra/radio/ADSL) "
            "para diagnosticar. "
            "Si tu consulta es por móvil IMOWI, Sensa/TV o factura, decime y te ayudo por ese lado."
        )
        set_journey(
            ctx,
            step="respond",
            last_action="run_diagnostic_pppoe",
            last_action_status="unavailable",
            last_diagnostic_result="no_fixed_internet",
            last_user_message=msg,
            next_required_input="",
            diagnostic_started=False,
        )
        ctx["eko_no_fixed_internet"] = True
        return JourneyTurn(
            handled=True,
            user_message=msg,
            journey="internet_sin_conectividad",
            step="respond",
            intent="internet",
            domain="internet",
            action="run_diagnostic_pppoe",
            action_status="unavailable",
            reason_code="no_fixed_internet",
            correlation_id=corr,
            data={"no_fixed_internet": True, "execution_path": "none"},
        )

    # Try capture login selection from user text (no probes)
    prev_sel = str(ctx.get("login_seleccionado") or st.get("selected_service") or "").strip()
    login = _try_capture_login(db, abonado, ctx, texto)
    if login:
        if not _enrich_login_to_ref(db, abonado, ctx, login, previous=prev_sel):
            _apply_service_selection(ctx, login, previous=prev_sel)

    # Auto-selección segura: un único login de Internet fijo (comportamiento ya existente)
    from app.services.eko_service_selection import (
        get_selected_ref,
        is_fixed_internet_diagnosticable,
        ownership_matches_ref,
    )

    if n_logins == 1 and not str(ctx.get("login_seleccionado") or "").strip():
        try:
            from app.services import billtrack as bt
            from app.services.canal_abonado import _servicios_conectividad_abonado

            svcs = _servicios_conectividad_abonado(db, abonado)
            opts = bt.listar_logins_conectividad(svcs)
            if len(opts) == 1:
                only = str(opts[0]).strip()
                if only and not _enrich_login_to_ref(db, abonado, ctx, only, previous=prev_sel):
                    _apply_service_selection(ctx, only, previous=prev_sel)
        except Exception:
            logger.debug("auto-select single login falló", exc_info=True)

    selected = str(ctx.get("login_seleccionado") or get_journey(ctx).get("selected_service") or "").strip()
    st = get_journey(ctx)
    ref = get_selected_ref(ctx)
    trusted_cn = str(getattr(abonado, "client_number", "") or "").strip()

    # Ownership: nunca diagnosticar ref ajeno
    if ref is not None and trusted_cn and not ownership_matches_ref(ref, trusted_cn):
        set_journey(ctx, step="respond", last_diagnostic_result="ownership_mismatch")
        return JourneyTurn(
            handled=True,
            user_message="No puedo diagnosticar un servicio que no pertenece a tu cuenta.",
            journey="internet_sin_conectividad",
            step="respond",
            intent="internet",
            domain="internet",
            action="run_diagnostic_pppoe",
            action_status="denied",
            reason_code="ownership_mismatch",
            correlation_id=corr,
            data={"execution_path": "none"},
        )

    # Servicio seleccionado no diagnosticable (Sensa/IMOWI/VoIP / sin login)
    if ref is not None and not is_fixed_internet_diagnosticable(ref):
        tip = (ref.service_type or ref.label or ref.product or "ese servicio").strip()
        msg = (
            f"Para «{tip}» no tengo un diagnóstico técnico de Internet disponible. "
            "Si el problema es tu Internet fijo (fibra/radio), elegí ese servicio "
            "y pedime revisar la conexión."
        )
        set_journey(
            ctx,
            step="respond",
            last_action="run_diagnostic_pppoe",
            last_action_status="unavailable",
            last_diagnostic_result="service_not_diagnosticable",
            last_user_message=msg,
            diagnostic_started=False,
        )
        return JourneyTurn(
            handled=True,
            user_message=msg,
            journey="internet_sin_conectividad",
            step="respond",
            intent="internet",
            domain="internet",
            action="run_diagnostic_pppoe",
            action_status="unavailable",
            reason_code="service_not_diagnosticable",
            correlation_id=corr,
            data={
                "selected_service_ref": ref.to_dict(),
                "execution_path": "none",
            },
        )

    st = get_journey(ctx)

    # Confirmation pending for ticket (trusted) — solo si sigue vigente en este journey
    if _confirmation_is_live(ctx):
        return _handle_ticket_confirmation(
            db=db,
            org_id=org_id,
            conv=conv,
            abonado=abonado,
            texto=texto,
            ctx=ctx,
            canal=canal,
            corr=corr,
        )

    # Ambiguous "sí"/"no" without live confirmation → no mutation
    t_low = (texto or "").strip().lower()
    if t_low in ("si", "sí", "no") and not _confirmation_is_live(ctx):
        if st.get("step") == "service_selection" or st.get("next_required_input") == "login":
            set_journey(ctx, step="service_selection", next_required_input="login")
            return JourneyTurn(
                handled=True,
                user_message=(
                    "Necesito que indiques la cuenta de Internet (usuario o dirección), "
                    "no alcanza con un «sí»."
                ),
                journey="internet_sin_conectividad",
                step="service_selection",
                intent="internet",
                domain="internet",
                correlation_id=corr,
                data={"stale_confirmation_guard": True},
            )
        # Sí/No suelto tras journey sin confirmación viva
        if t_low in ("si", "sí"):
            return JourneyTurn(
                handled=True,
                user_message=(
                    "No tengo una acción pendiente de confirmar. "
                    "Decime qué necesitás (Internet, saldo o un reclamo)."
                ),
                journey="internet_sin_conectividad",
                step=str(st.get("step") or "respond"),
                intent="internet",
                domain="internet",
                correlation_id=corr,
                data={"stale_confirmation_guard": True},
            )

    # Idempotency: diagnóstico ya informado → no re-probe salvo pedido explícito.
    # Incluye textos que no matchean connectivity (p.ej. frases LLM) para que
    # no reinterpreten autoridad ni disparen side effects.
    detected_here = detect_journey_name(texto)
    if (
        ctx.get("pppoe_informado")
        and st.get("last_diagnostic_result")
        and detected_here in (None, "internet_sin_conectividad")
        and not login
        and not _wants_rediagnose(texto)
        and st.get("step") in ("respond", "done", "interpret", "decide")
        and not st.get("pending_confirmation")
    ):
        prev_msg = str(st.get("last_user_message") or "").strip()
        msg = prev_msg or (
            "Ya revisé tu conexión en este chat. "
            "Si cambió algo o querés que vuelva a chequear, decime."
        )
        set_journey(ctx, step="respond", pending_confirmation=False)
        return JourneyTurn(
            handled=True,
            user_message=msg,
            journey="internet_sin_conectividad",
            step="respond",
            intent="internet",
            domain="internet",
            action=str(st.get("last_action") or ""),
            action_status="already_done",
            correlation_id=corr,
            data={"idempotent_skip": True},
        )

    # Avoid re-asking selection if already asked and still no login (loop gate)
    n = n_logins
    if (
        n > 1
        and not selected
        and (
            st.get("step") == "service_selection"
            or st.get("asked_selection")
            or st.get("next_required_input") == "login"
        )
        and st.get("asked_selection")
    ):
        set_journey(ctx, step="service_selection", next_required_input="login")
        return JourneyTurn(
            handled=True,
            user_message=(
                "Todavía necesito que indiques cuál cuenta de Internet revisar "
                "(usuario INT…). No puedo diagnosticar sin esa elección."
            ),
            journey="internet_sin_conectividad",
            step="service_selection",
            intent="internet",
            domain="internet",
            correlation_id=corr,
        )

    # Service selection gate — zero probes
    if n > 1 and not selected:
        set_journey(
            ctx,
            step="service_selection",
            next_required_input="login",
        )
        ctx["multi_cuenta_pendiente"] = True
        try:
            from app.services import billtrack as bt
            from app.services.canal_abonado import _servicios_conectividad_abonado

            svcs = _servicios_conectividad_abonado(db, abonado)
            opts = bt.listar_logins_conectividad(svcs)
            set_journey(ctx, selection_options=opts)
            sel_msg = bt.mensaje_seleccion_cuenta_internet(svcs, repregunta=bool(st.get("asked_selection")))
        except Exception:
            opts = []
            sel_msg = _msg_selection()
            set_journey(ctx, selection_options=opts)
        if not _capability_allowed("request_account_selection"):
            set_journey(ctx, asked_selection=True)
            return JourneyTurn(
                handled=True,
                user_message=sel_msg,
                journey="internet_sin_conectividad",
                step="service_selection",
                intent="internet",
                domain="internet",
                action="request_account_selection",
                action_status="needs_input",
                correlation_id=corr,
            )
        ar = dispatch_runtime(
            "request_account_selection",
            db=db,
            org_id=org_id,
            conv=conv,
            abonado=abonado,
            ctx=ctx,
            canal=canal,
            decision_name="journey_connectivity_selection",
            parameters={"message": sel_msg},
            texto=texto,
        )
        if ar is None:
            set_journey(
                ctx,
                asked_selection=True,
                last_action="request_account_selection",
                last_action_status="needs_input",
            )
            return JourneyTurn(
                handled=True,
                user_message=sel_msg,
                journey="internet_sin_conectividad",
                step="service_selection",
                intent="internet",
                domain="internet",
                action="request_account_selection",
                action_status="needs_input",
                correlation_id=corr,
                data={"execution_path": "legacy_contractual"},
            )
        _record_action(ctx, st, ar, action="request_account_selection")
        set_journey(ctx, asked_selection=True, step="service_selection")
        return JourneyTurn(
            handled=True,
            user_message=ar.user_message or sel_msg,
            journey="internet_sin_conectividad",
            step="service_selection",
            intent="internet",
            domain="internet",
            action="request_account_selection",
            action_status=ar.status,
            reason_code=ar.reason_code,
            correlation_id=ar.correlation_id or corr,
        )

    # Explicit diagnostic via capability (not direct Radius)
    if not _capability_allowed("run_diagnostic_pppoe"):
        set_journey(ctx, step="respond")
        return JourneyTurn(
            handled=True,
            user_message="No puedo ejecutar el diagnóstico de conexión en este momento.",
            journey="internet_sin_conectividad",
            step="respond",
            correlation_id=corr,
            data={"gap": "run_diagnostic_pppoe"},
        )

    # Safety net (Fase 7): probe multi-cuenta sin selección = unexpected_probe + gate
    if n > 1 and not selected:
        from app.services.eko_journey_observability import record_security_signal

        record_security_signal(
            "unexpected_probe",
            journey="internet_sin_conectividad",
            step="diagnostic",
            action="run_diagnostic_pppoe",
            correlation_id=corr,
            channel=canal,
        )
        set_journey(ctx, step="service_selection", next_required_input="login", asked_selection=True)
        return JourneyTurn(
            handled=True,
            user_message=_msg_selection(),
            journey="internet_sin_conectividad",
            step="service_selection",
            intent="internet",
            domain="internet",
            correlation_id=corr,
            data={"unexpected_probe_blocked": True},
        )

    set_journey(ctx, step="diagnostic", diagnostic_started=True)
    ar = dispatch_runtime(
        "run_diagnostic_pppoe",
        db=db,
        org_id=org_id,
        conv=conv,
        abonado=abonado,
        ctx=ctx,
        canal=canal,
        decision_name="journey_connectivity_pppoe",
        texto=texto,
    )
    if ar is None:
        # Contractual Legacy: canal_pppoe path (single execution when journey yields)
        ar = _legacy_pppoe_as_result(db, abonado, ctx, org_id=org_id)
        path = "legacy"
    else:
        path = "runtime"

    _record_action(ctx, get_journey(ctx), ar, action="run_diagnostic_pppoe")

    if ar.status == "needs_input":
        set_journey(ctx, step="service_selection", next_required_input="login", asked_selection=True)
        ctx["multi_cuenta_pendiente"] = True
        return JourneyTurn(
            handled=True,
            user_message=ar.user_message or _msg_selection(),
            journey="internet_sin_conectividad",
            step="service_selection",
            action="run_diagnostic_pppoe",
            action_status=ar.status,
            reason_code=ar.reason_code,
            correlation_id=ar.correlation_id or corr,
            data={"execution_path": path},
        )

    obs, msg = _interpret_pppoe(ar)
    set_journey(
        ctx,
        step="interpret",
        last_diagnostic_result=obs,
    )
    # BCM/UISP: no auto-ejecutar en Fase 5 (Legacy contractual en canal_pppoe fuera del journey).
    set_journey(ctx, step="decide", next_observation="bcm_uisp_legacy_out_of_scope_5")

    _sel = get_selected_ref(ctx)
    diag_meta = {
        "observation": obs,
        "execution_path": path,
        "login_used": (ar.data or {}).get("login_used") or selected,
        "service_id": (ar.data or {}).get("service_id")
        or (_sel.service_id if _sel else ""),
        "reason_code": ar.reason_code or (ar.data or {}).get("reason_code"),
        "connectivity_status": (ar.data or {}).get("connectivity_status"),
    }

    if ar.status == "denied":
        set_journey(ctx, step="respond", last_user_message=msg, diagnostic_started=False)
        return JourneyTurn(
            handled=True,
            user_message=msg,
            journey="internet_sin_conectividad",
            step="respond",
            action="run_diagnostic_pppoe",
            action_status="denied",
            reason_code=ar.reason_code,
            correlation_id=ar.correlation_id or corr,
            data={**diag_meta, "decision": "denied"},
        )

    # Sesión caída (Radius legacy) o no_session (portal): ofrecer escalamiento
    if obs in ("pppoe_session_down", "no_session"):
        _mark_confirmation_pending(ctx, corr=corr)
        set_journey(ctx, step="decide", last_user_message=msg)
        return JourneyTurn(
            handled=True,
            user_message=msg,
            journey="internet_sin_conectividad",
            step="decide",
            action="run_diagnostic_pppoe",
            action_status=ar.status,
            reason_code=ar.reason_code,
            correlation_id=ar.correlation_id or corr,
            data={**diag_meta, "decision": "offer_escalate"},
        )

    if obs in ("pppoe_session_up", "operational"):
        set_journey(ctx, step="respond", next_required_input="", last_user_message=msg, pending_confirmation=False)
        ctx["pppoe_informado"] = True
        return JourneyTurn(
            handled=True,
            user_message=msg,
            journey="internet_sin_conectividad",
            step="respond",
            action="run_diagnostic_pppoe",
            action_status=ar.status,
            reason_code=ar.reason_code,
            correlation_id=ar.correlation_id or corr,
            data={**diag_meta, "decision": "local_checks"},
        )

    set_journey(ctx, step="respond", last_user_message=msg)
    ctx["pppoe_informado"] = True
    return JourneyTurn(
        handled=True,
        user_message=msg,
        journey="internet_sin_conectividad",
        step="respond",
        action="run_diagnostic_pppoe",
        action_status=ar.status,
        reason_code=ar.reason_code,
        correlation_id=ar.correlation_id or corr,
        data=diag_meta,
    )


def _handle_ticket_confirmation(
    *,
    db: Session | None,
    org_id: str,
    conv: Any,
    abonado: Any | None,
    texto: str,
    ctx: dict[str, Any],
    canal: str,
    corr: str,
) -> JourneyTurn:
    from app.services.canal_abonado import _ticket_via_runtime_o_legacy

    rec, rej = resolve_user_confirmation(
        ctx=ctx,
        action="create_ticket",
        texto=texto,
        intencion=str(ctx.get("intencion") or "internet"),
    )
    if rej:
        set_journey(
            ctx,
            pending_confirmation=False,
            step="respond",
            next_required_input="",
            last_action="create_ticket",
            last_action_status="rejected",
        )
        return JourneyTurn(
            handled=True,
            user_message="Perfecto, no genero el ticket. ¿En qué más te ayudo con el Internet?",
            journey="internet_sin_conectividad",
            step="respond",
            action="create_ticket",
            action_status="denied",
            reason_code="confirmation_rejected",
            correlation_id=corr,
        )
    if not rec:
        # Still waiting — do not re-open menu; no stale mutation
        _mark_confirmation_pending(ctx, corr=corr)
        return JourneyTurn(
            handled=True,
            user_message=(
                "Para derivar con un agente y generar un ticket, confirmame con un «sí». "
                "Si preferís seguir en el chat, decime «no»."
            ),
            journey="internet_sin_conectividad",
            step="confirm_action",
            correlation_id=corr,
        )

    if not _capability_allowed("create_ticket"):
        set_journey(ctx, step="respond")
        return JourneyTurn(
            handled=True,
            user_message="No puedo generar el ticket por esta vía ahora.",
            journey="internet_sin_conectividad",
            step="respond",
            data={"gap": "create_ticket"},
            correlation_id=corr,
        )

    tid, pending = _ticket_via_runtime_o_legacy(
        db,
        org_id,
        conv,
        abonado,
        "Journey internet_sin_conectividad: sin sesión / escalamiento confirmado",
        intencion="internet",
        paso_idx=int(ctx.get("paso_idx") or 0),
        ctx=ctx,
        canal=canal,
        texto=texto,
        decision_name="journey_connectivity_create_ticket",
    )
    if pending:
        _mark_confirmation_pending(ctx, corr=corr)
        set_journey(
            ctx,
            last_action="create_ticket",
            last_action_status="needs_confirmation",
        )
        return JourneyTurn(
            handled=True,
            user_message=pending,
            journey="internet_sin_conectividad",
            step="confirm_action",
            action="create_ticket",
            action_status="needs_confirmation",
            correlation_id=corr,
        )
    if tid:
        set_journey(
            ctx,
            pending_confirmation=False,
            step="done",
            last_action="create_ticket",
            last_action_status="success",
            next_required_input="",
        )
        return JourneyTurn(
            handled=True,
            user_message=(
                f"Dale, te derivo con un agente. Ticket {tid}. Quedate en este chat."
            ),
            mode="espera_agente",
            journey="internet_sin_conectividad",
            step="done",
            action="create_ticket",
            action_status="success",
            correlation_id=corr,
            data={"ticket_id": tid},
        )
    set_journey(ctx, step="respond", pending_confirmation=False)
    return JourneyTurn(
        handled=True,
        user_message="No pude generar el ticket ahora.",
        journey="internet_sin_conectividad",
        step="respond",
        action="create_ticket",
        action_status="failed",
        correlation_id=corr,
    )


def _login_count(db: Session | None, abonado: Any | None) -> int:
    from app.services.eko_context import internet_logins_count

    return int(internet_logins_count(db, abonado) or 0)


def _try_capture_login(db: Session | None, abonado: Any | None, ctx: dict, texto: str) -> str:
    """Resuelve selección de cuenta sin probes. Reusa BillTrack + ordinales."""
    if db is None or abonado is None:
        return ""
    try:
        from app.services import billtrack as bt
        from app.services.canal_abonado import _servicios_conectividad_abonado

        servicios = _servicios_conectividad_abonado(db, abonado)
        login = bt.extraer_login_en_texto(texto, servicios) or ""
        if login:
            return str(login).strip()
        m = re.search(r"\b(INT\d[\w.-]{1,})\b", texto or "", re.I)
        if m:
            return m.group(1)
        # Ordinal / etiqueta frente a opciones ya listadas en el journey
        opts = list(get_journey(ctx).get("selection_options") or [])
        if not opts:
            opts = bt.listar_logins_conectividad(servicios)
        ordinal = _ordinal_index(texto)
        if ordinal is not None and 0 <= ordinal < len(opts):
            return str(opts[ordinal]).strip()
        label = _label_login_guess(texto, servicios, opts)
        if label:
            return label
    except Exception:
        logger.debug("journey login capture falló", exc_info=True)
    # No devolver login_ctx previo aquí: permite contradicción explícita sin sticky silencioso
    return ""


def _ordinal_index(texto: str) -> int | None:
    t = (texto or "").lower().strip()
    mapping = (
        (("primer", "primero", "primera", "1", "uno", "el 1", "la 1"), 0),
        (("segund", "segundo", "segunda", "2", "dos", "el 2", "la 2"), 1),
        (("tercer", "tercero", "tercera", "3", "tres", "el 3"), 2),
    )
    for keys, idx in mapping:
        if any(k in t for k in keys):
            return idx
    return None


def _label_login_guess(texto: str, servicios: list[Any], opts: list[str]) -> str:
    """casa/local solo si hay match inequívoco en locality/product o en labels."""
    t = (texto or "").lower()
    if not t:
        return ""
    casa_keys = ("casa", "hogar", "domicilio", "vivienda")
    local_keys = ("local", "comercio", "negocio", "oficina", "trabajo")
    want_casa = any(k in t for k in casa_keys)
    want_local = any(k in t for k in local_keys)
    if not want_casa and not want_local:
        return ""
    hits: list[str] = []
    for svc in servicios or []:
        login = str(getattr(svc, "login", "") or "").strip()
        if not login:
            continue
        blob = " ".join(
            [
                str(getattr(svc, "locality", "") or ""),
                str(getattr(svc, "product", "") or ""),
                str(getattr(svc, "label", "") or ""),
                login,
            ]
        ).lower()
        if want_casa and any(k in blob for k in casa_keys):
            hits.append(login)
        if want_local and any(k in blob for k in local_keys):
            hits.append(login)
    uniq = list(dict.fromkeys(hits))
    if len(uniq) == 1:
        return uniq[0]
    # Sin metadata: si hay exactamente 2 opciones y el usuario dijo «casa»/«local»,
    # no adivinar — devolver vacío (sigue NEEDS_INPUT).
    return ""


def _apply_service_selection(ctx: dict, login: str, *, previous: str = "") -> None:
    """Compat: selección solo por login (connectivity). Delega a apply_service_ref."""
    from app.services.eko_service_selection import ServiceRef, get_selected_ref

    login_n = (login or "").strip()
    if not login_n:
        return
    prev_ref = get_selected_ref(ctx)
    # previous string may be login from old selected_service
    prev_login = (previous or "").strip() or (prev_ref.login if prev_ref else "")
    ref = ServiceRef(
        service_id=(prev_ref.service_id if prev_ref and prev_ref.login == login_n else ""),
        login=login_n,
        service_type=(prev_ref.service_type if prev_ref and prev_ref.login == login_n else ""),
        client_number=(prev_ref.client_number if prev_ref and prev_ref.login == login_n else ""),
        label="",
        product="",
        active=None,
    )
    apply_service_ref(ctx, ref, previous_login=prev_login)


def apply_service_ref(
    ctx: dict,
    ref: Any,
    *,
    previous_login: str = "",
) -> None:
    """Persiste selección única: selected_service_ref + proyecciones compat."""
    from app.services.eko_service_selection import ServiceRef, get_selected_ref, selection_changed

    if not isinstance(ref, ServiceRef):
        return
    prev = get_selected_ref(ctx)
    login_n = (ref.login or "").strip()
    # Compat: selected_service sigue siendo el login cuando existe; si no, service_id.
    compat_key = login_n or ref.service_id
    set_journey(
        ctx,
        selected_service=compat_key,
        selected_service_ref=ref.to_dict(),
        next_required_input="",
        asked_selection=False,
    )
    if login_n:
        ctx["login_seleccionado"] = login_n
    else:
        # Servicio sin login técnico (p.ej. Sensa): no dejar login ajeno sticky
        ctx.pop("login_seleccionado", None)
    ctx.pop("multi_cuenta_pendiente", None)

    changed = selection_changed(prev, ref)
    if not changed and previous_login and login_n and previous_login != login_n:
        changed = True
    if changed:
        set_journey(
            ctx,
            diagnostic_started=False,
            last_diagnostic_result="",
            pending_confirmation=False,
            confirmation_correlation="",
            step="service_selection",
        )
        ctx.pop("pppoe_informado", None)
        ctx.pop("pppoe_triage", None)
        try:
            from app.services.connectivity_eko import limpiar_tss_de_ctx

            limpiar_tss_de_ctx(ctx)
        except Exception:
            for k in (
                "tss_status",
                "tss_reason_code",
                "tss_message_key",
                "tss_service_id",
                "tss_access_technology",
                "tss_freshness",
                "tss_checked_at",
                "tss_incident_id",
                "tss_eko_branch",
            ):
                ctx.pop(k, None)


def _enrich_login_to_ref(
    db: Session | None,
    abonado: Any | None,
    ctx: dict,
    login: str,
    *,
    previous: str = "",
) -> bool:
    """Resuelve login → selected_service_ref vía catálogo. Sin probes."""
    if db is None or abonado is None:
        return False
    cn = str(getattr(abonado, "client_number", "") or "").strip()
    if not cn:
        return False
    try:
        from app.services.eko_service_selection import resolve_service_selection
        from app.services.portal_services import catalog_for_selection

        cat = catalog_for_selection(db, abonado=abonado)
        if cat.get("status") != "ok":
            return False
        result = resolve_service_selection(
            texto="",
            catalog=list(cat.get("services") or []),
            client_number=cn,
            proposed_login=login,
        )
        if result.status == "selected" and result.ref is not None:
            apply_service_ref(ctx, result.ref, previous_login=previous)
            return True
    except Exception:
        logger.debug("enrich login→ref falló", exc_info=True)
    return False


def _legacy_pppoe_as_result(
    db: Session | None,
    abonado: Any | None,
    ctx: dict,
    *,
    org_id: str = "",
) -> ActionResult:
    """Fallback contractual único (XOR): Legacy canal_pppoe, no Runtime+Legacy."""
    try:
        from app.services.canal_pppoe import _talvez_mensaje_pppoe

        msg = _talvez_mensaje_pppoe(
            db, abonado, ctx, "internet", org_id=org_id
        )
        if not msg:
            return ActionResult(
                action="run_diagnostic_pppoe",
                status="unavailable",
                reason_code="legacy_no_message",
                execution_path="legacy",
                user_message="No pude obtener el estado de conexión.",
            )
        # Infer online/offline only from ctx triage already set by Legacy path
        triage = str(ctx.get("pppoe_triage") or "")
        online = "ok" in triage.lower() or "online" in triage.lower() or "conectado" in triage.lower()
        offline = "offline" in triage.lower() or "down" in triage.lower() or "sin_sesion" in triage.lower()
        estado = SimpleOnline(online=True) if online and not offline else (
            SimpleOnline(online=False) if offline else SimpleOnline(online=None)
        )
        return ActionResult(
            action="run_diagnostic_pppoe",
            status="success",
            user_message=msg,
            data={"_estado": estado, "legacy_msg": True},
            execution_path="legacy",
        )
    except Exception:
        logger.exception("legacy pppoe journey fallback falló")
        return ActionResult(
            action="run_diagnostic_pppoe",
            status="failed",
            reason_code="legacy_exception",
            execution_path="legacy",
            user_message="No pude consultar la conexión ahora.",
        )


class SimpleOnline:
    def __init__(self, online: bool | None):
        self.online = online
        self.sesion = type("S", (), {"online": online})()


# ---------------------------------------------------------------------------
# Billing / ticket journeys
# ---------------------------------------------------------------------------


def _billing_user_act(texto: str) -> str:
    """Clasificación determinística del pedido billing (no LLM)."""
    t = (texto or "").lower().strip()
    if any(
        k in t
        for k in (
            "cuando vence",
            "cuándo vence",
            "fecha de vencimiento",
            "vencimiento",
            "vence mi",
        )
    ):
        return "due_date"
    if any(
        k in t
        for k in (
            "que pagué",
            "qué pagué",
            "que pague",
            "pagos hice",
            "historial de pago",
            "mis pagos",
            "comprobante de pago que hice",
        )
    ):
        return "payment_history"
    if any(
        k in t
        for k in (
            "talon",
            "talón",
            "talon de pago",
            "talón de pago",
            "qr de pago",
        )
    ):
        return "payment_slip"
    if any(
        k in t
        for k in (
            "cuanto tengo que pagar",
            "cuánto tengo que pagar",
            "cuanto debo",
            "cuánto debo",
            "cual es mi saldo",
            "cuál es mi saldo",
            "mi saldo",
            "consultar saldo",
            "tengo deuda",
        )
    ):
        return "balance"
    # pay antes que invoice: "pagar la factura" no debe abrir show_invoice
    if any(
        k in t
        for k in (
            "quiero pagar",
            "donde pago",
            "dónde pago",
            "como pago",
            "cómo pago",
            "pagar",
        )
    ):
        return "pay"
    if any(
        k in t
        for k in (
            "ver factura",
            "ver mi factura",
            "mi factura",
            "la factura",
            "necesito la factura",
            "necesito mi factura",
            "mostrame la factura",
            "mostrar factura",
            "factura pendiente",
            "que factura",
            "qué factura",
        )
    ):
        return "invoice"
    return "balance"


def _open_ov_destination(
    *,
    db: Session | None,
    org_id: str,
    conv: Any,
    abonado: Any | None,
    ctx: dict[str, Any],
    canal: str,
    texto: str,
    destination: str,
    corr: str,
) -> tuple[ActionResult | None, str]:
    """Runtime open_OV o Legacy link público. destination: pagar|my|talon-de-pago."""
    path = "runtime"
    if _capability_allowed("open_OV"):
        ar = dispatch_runtime(
            "open_OV",
            db=db,
            org_id=org_id,
            conv=conv,
            abonado=abonado,
            ctx=ctx,
            canal=canal,
            decision_name="journey_billing_ov",
            parameters={"destination": destination},
            texto=texto,
        )
        if ar is not None:
            _record_action(ctx, get_journey(ctx), ar, action="open_OV")
            return ar, path
    # Legacy contractual: Facts OV links
    from app.services.eko_context import build_eko_facts

    facts = build_eko_facts(abonado, db=db, org_id=org_id)
    links = ((facts.get("ov") or {}).get("links") or {})
    key_map = {"pagar": "pay", "my": "invoice", "talon-de-pago": "payment_slip"}
    url = str(links.get(key_map.get(destination, ""), "") or "")
    if not url:
        ar = ActionResult(
            action="open_OV",
            status="unavailable",
            reason_code="ov_unavailable",
            user_message="No pude armar el enlace a la Oficina Virtual ahora.",
            execution_path="legacy",
            correlation_id=corr,
        )
        path = "legacy"
        _record_action(ctx, get_journey(ctx), ar, action="open_OV")
        return ar, path
    ar = ActionResult(
        action="open_OV",
        status="success",
        data={"url": url, "destination": destination, "auth": "external"},
        user_message=f"Podés continuar en la Oficina Virtual:\n{url}",
        execution_path="legacy",
        correlation_id=corr,
    )
    path = "legacy"
    _record_action(ctx, get_journey(ctx), ar, action="open_OV")
    return ar, path


def _advance_billing_invoice(
    *,
    db: Session | None,
    org_id: str,
    conv: Any,
    abonado: Any | None,
    texto: str,
    ctx: dict[str, Any],
    canal: str,
    corr: str,
    journey: str,
) -> JourneyTurn:
    """Invoice header READ (FC) + OV opcional. Sin due_date/period/PDF/líneas."""
    # Multi-cuenta telefónica ya resolvió NEEDS_INPUT arriba; no adivinar acá.
    if ctx.get("phone_candidates") and abonado is None:
        set_journey(ctx, step="identity", next_required_input="account_selection")
        return JourneyTurn(
            handled=True,
            user_message=(
                "Encontré más de una cuenta asociada a este número. "
                "Indicame el DNI de la cuenta que querés consultar."
            ),
            journey=journey,
            step="identity",
            intent="facturacion",
            domain="billing",
            action_status="needs_input",
            reason_code="identity_ambiguous",
            correlation_id=corr,
            data={"needs_input": "account_selection", "billing_act": "invoice"},
        )

    client_number = str(getattr(abonado, "client_number", "") or "").strip() if abonado else ""

    # Ownership no resuelto: no despachar ni consultar BillTrack.
    if not client_number:
        set_journey(ctx, step="identity", next_required_input="client_number")
        return JourneyTurn(
            handled=True,
            user_message="No tengo el número de cuenta para consultar facturas.",
            journey=journey,
            step="identity",
            intent="facturacion",
            domain="billing",
            action="show_invoice",
            action_status="needs_input",
            reason_code="missing_client_number",
            correlation_id=corr,
            data={
                "needs_input": "client_number",
                "billing_act": "invoice",
                "execution_path": "none",
            },
        )

    ar: ActionResult | None = None
    path = "runtime"
    if _capability_allowed("show_invoice"):
        ar = dispatch_runtime(
            "show_invoice",
            db=db,
            org_id=org_id,
            conv=conv,
            abonado=abonado,
            ctx=ctx,
            canal=canal,
            decision_name="journey_billing_invoice",
            parameters={"client_number": client_number},
            texto=texto,
        )
    if ar is None:
        from app.services.eko_invoice_reader import (
            format_invoice_headers_message,
            read_invoices_fc,
        )

        path = "legacy"
        result = read_invoices_fc(client_number=client_number, db=db, limit=5)
        if result.status == "invalid_input":
            ar = ActionResult(
                action="show_invoice",
                status="needs_input",
                reason_code=result.reason_code,
                user_message=result.message,
                execution_path="legacy",
            )
        elif result.status in ("unavailable", "error"):
            ar = ActionResult(
                action="show_invoice",
                status="unavailable",
                reason_code=result.reason_code,
                user_message=result.message,
                execution_path="legacy",
                data={"invoice_read_status": result.status},
            )
        elif result.status == "empty":
            ar = ActionResult(
                action="show_invoice",
                status="success",
                reason_code="no_fc_invoices",
                user_message=result.message,
                execution_path="legacy",
                data={"invoices": [], "count": 0},
            )
        else:
            ar = ActionResult(
                action="show_invoice",
                status="success",
                user_message=format_invoice_headers_message(result.invoices),
                execution_path="legacy",
                data={
                    "invoices": [i.to_dict() for i in result.invoices],
                    "count": len(result.invoices),
                },
            )

    _record_action(ctx, get_journey(ctx), ar, action="show_invoice")
    msg = ar.user_message or ""

    # OV como complemento (PDF/detalle fuera de Eko), no como sustituto del reader
    if ar.status in ("success", "unavailable") and _capability_allowed("open_OV"):
        ov_ar, ov_path = _open_ov_destination(
            db=db,
            org_id=org_id,
            conv=conv,
            abonado=abonado,
            ctx=ctx,
            canal=canal,
            texto=texto,
            destination="my",
            corr=corr,
        )
        if ov_ar and ov_ar.status == "success" and ov_ar.user_message:
            if ar.reason_code == "no_fc_invoices":
                msg = (
                    f"{msg}\nPodés revisar en la Oficina Virtual:\n{ov_ar.user_message}"
                )
            elif ar.status == "success" and (ar.data or {}).get("count"):
                msg = (
                    f"{msg}\n\nSi necesitás el PDF u otro detalle, "
                    f"continúa en la Oficina Virtual:\n{ov_ar.user_message}"
                )
            elif ar.status == "unavailable":
                msg = f"{msg}\nTambién podés intentar en la Oficina Virtual:\n{ov_ar.user_message}"
            path = f"{path}+{ov_path}"

    set_journey(ctx, step="done" if ar.status == "success" else "respond", last_user_message=msg)
    return JourneyTurn(
        handled=True,
        user_message=msg,
        journey=journey,
        step=get_journey(ctx).get("step") or "respond",
        intent="facturacion",
        domain="billing",
        action="show_invoice",
        action_status=ar.status,
        reason_code=ar.reason_code,
        correlation_id=ar.correlation_id or corr,
        data={
            "execution_path": path,
            "billing_act": "invoice",
            "invoices": (ar.data or {}).get("invoices"),
            "count": (ar.data or {}).get("count"),
        },
    )


def _advance_billing(
    *,
    db: Session | None,
    org_id: str,
    conv: Any,
    abonado: Any | None,
    texto: str,
    ctx: dict[str, Any],
    canal: str,
) -> JourneyTurn:
    """Eko 2.1 billing_self_service: READ balance + invoice header + NAVIGATION OV."""
    journey = "billing_self_service"
    corr = str(get_journey(ctx).get("correlation_id") or uuid.uuid4())
    set_journey(
        ctx,
        name=journey,
        journey=journey,
        correlation_id=corr,
        intent="facturacion",
        domain="billing",
        step="respond",
    )

    # Identidad / desambiguación multi-cuenta telefónica
    if abonado is None:
        if ctx.get("phone_candidates"):
            set_journey(ctx, step="identity", next_required_input="account_selection")
            return JourneyTurn(
                handled=True,
                user_message=(
                    "Encontré más de una cuenta asociada a este número. "
                    "Indicame el DNI de la cuenta que querés consultar."
                ),
                journey=journey,
                step="identity",
                intent="facturacion",
                domain="billing",
                action_status="needs_input",
                reason_code="identity_ambiguous",
                correlation_id=corr,
                data={"needs_input": "account_selection"},
            )
        set_journey(ctx, step="identity", next_required_input="identity")
        return JourneyTurn(
            handled=True,
            user_message="Para consultar tu saldo o factura necesito identificarte. ¿Me pasás tu DNI?",
            journey=journey,
            step="identity",
            intent="facturacion",
            domain="billing",
            action_status="needs_input",
            correlation_id=corr,
        )

    act = _billing_user_act(texto)

    # --- Invoice fields / due / payment history: honest unavailable + OV ---
    if act == "due_date":
        ov_ar, path = _open_ov_destination(
            db=db,
            org_id=org_id,
            conv=conv,
            abonado=abonado,
            ctx=ctx,
            canal=canal,
            texto=texto,
            destination="my",
            corr=corr,
        )
        base = (
            "No tengo disponible desde Eko la fecha de vencimiento de tu factura. "
            "Podés consultarla en la Oficina Virtual."
        )
        msg = base
        if ov_ar and ov_ar.status == "success" and ov_ar.user_message:
            msg = f"{base}\n{ov_ar.user_message}"
        set_journey(ctx, step="done", last_user_message=msg)
        return JourneyTurn(
            handled=True,
            user_message=msg,
            journey=journey,
            step="done",
            intent="facturacion",
            domain="billing",
            action="open_OV",
            action_status=(ov_ar.status if ov_ar else "unavailable"),
            correlation_id=corr,
            data={
                "execution_path": path,
                "billing_act": act,
                "honest_unavailable": "due_date",
            },
        )

    if act == "payment_history":
        msg = (
            "Desde Eko no tengo el historial de pagos. "
            "Podés revisarlo en la Oficina Virtual."
        )
        ov_ar, path = _open_ov_destination(
            db=db,
            org_id=org_id,
            conv=conv,
            abonado=abonado,
            ctx=ctx,
            canal=canal,
            texto=texto,
            destination="my",
            corr=corr,
        )
        if ov_ar and ov_ar.status == "success" and ov_ar.user_message:
            msg = f"{msg}\n{ov_ar.user_message}"
        set_journey(ctx, step="done", last_user_message=msg)
        return JourneyTurn(
            handled=True,
            user_message=msg,
            journey=journey,
            step="done",
            intent="facturacion",
            domain="billing",
            action="open_OV",
            action_status=(ov_ar.status if ov_ar else "unavailable"),
            correlation_id=corr,
            data={
                "execution_path": path,
                "billing_act": act,
                "honest_unavailable": "payment_history",
            },
        )

    if act == "invoice":
        return _advance_billing_invoice(
            db=db,
            org_id=org_id,
            conv=conv,
            abonado=abonado,
            texto=texto,
            ctx=ctx,
            canal=canal,
            corr=corr,
            journey=journey,
        )

    if act in ("pay", "payment_slip"):
        dest = {"pay": "pagar", "payment_slip": "talon-de-pago"}[act]
        preface = {
            "pay": "Para pagar, usá la Oficina Virtual (el cobro se hace allá, no en este chat).",
            "payment_slip": "Te dejo el acceso al talón de pago en la Oficina Virtual.",
        }[act]
        ov_ar, path = _open_ov_destination(
            db=db,
            org_id=org_id,
            conv=conv,
            abonado=abonado,
            ctx=ctx,
            canal=canal,
            texto=texto,
            destination=dest,
            corr=corr,
        )
        msg = preface
        if ov_ar and ov_ar.status == "success" and ov_ar.user_message:
            msg = f"{preface}\n{ov_ar.user_message}"
        elif ov_ar and ov_ar.status != "success":
            msg = f"{preface}\n{ov_ar.user_message or ''}".strip()
        set_journey(ctx, step="done", last_user_message=msg)
        return JourneyTurn(
            handled=True,
            user_message=msg,
            journey=journey,
            step="done",
            intent="facturacion",
            domain="billing",
            action="open_OV",
            action_status=(ov_ar.status if ov_ar else "unavailable"),
            correlation_id=corr,
            data={"execution_path": path, "billing_act": act, "ov_destination": dest},
        )

    # --- Balance (default) ---
    if not _capability_allowed("show_balance"):
        return JourneyTurn(
            handled=True,
            user_message="No puedo consultar el saldo ahora.",
            journey=journey,
            step="respond",
            data={"gap": "show_balance"},
            correlation_id=corr,
        )
    ar = dispatch_runtime(
        "show_balance",
        db=db,
        org_id=org_id,
        conv=conv,
        abonado=abonado,
        ctx=ctx,
        canal=canal,
        decision_name="journey_billing_balance",
        texto=texto,
    )
    path = "runtime"
    if ar is None:
        from app.services.eco_voice import mensaje_saldo_padron
        from app.services.eko_context import billing_amount_str, build_eko_facts

        facts = build_eko_facts(abonado, db=db, org_id=org_id)
        billing = facts.get("billing") or {}
        amount = billing_amount_str(facts)
        if amount is None or (
            billing.get("status") == "unavailable" and billing.get("balance") is None
        ):
            ar = ActionResult(
                action="show_balance",
                status="unavailable",
                reason_code="billing_unavailable",
                user_message="No puedo consultar el saldo en este momento.",
                execution_path="legacy",
            )
        else:
            note = ""
            if billing.get("status") == "stale":
                note = " (dato de padrón; puede no estar al instante)."
            ar = ActionResult(
                action="show_balance",
                status="success",
                data={
                    "amount": amount,
                    "billing_status": billing.get("status"),
                    "capabilities_hint": billing.get("capabilities_hint"),
                },
                user_message=mensaje_saldo_padron(amount, incluir_ov=False) + note,
                execution_path="legacy",
            )
        path = "legacy"
    _record_action(ctx, get_journey(ctx), ar, action="show_balance")
    msg = ar.user_message or ""
    set_journey(ctx, step="done" if ar.status == "success" else "respond", last_user_message=msg)
    return JourneyTurn(
        handled=True,
        user_message=msg,
        journey=journey,
        step=get_journey(ctx).get("step") or "respond",
        intent="facturacion",
        domain="billing",
        action="show_balance",
        action_status=ar.status,
        reason_code=ar.reason_code,
        correlation_id=ar.correlation_id or corr,
        data={"execution_path": path, "billing_act": "balance"},
    )


def _advance_installation_status(
    *,
    db: Session | None,
    org_id: str,
    conv: Any,
    abonado: Any | None,
    texto: str,
    ctx: dict[str, Any],
    canal: str,
) -> JourneyTurn:
    """Eko 2.2D: honest unavailable — no hay agenda/órdenes estructuradas.

    Discovery: sin fuente factual de instalación. No inventar fechas/turnos/estados.
    """
    journey = "installation_status"
    corr = str(get_journey(ctx).get("correlation_id") or uuid.uuid4())
    set_journey(
        ctx,
        name=journey,
        correlation_id=corr,
        intent="seguimiento_instalacion",
        domain="services",
        step="respond",
    )
    msg = (
        "Actualmente no tengo información verificable de la instalación "
        "para mostrarte (fecha, turno o estado). "
        "Si tenés un número de ticket de visita, pedime el estado del ticket; "
        "si no, un agente puede ayudarte a consultarlo."
    )
    path = "none"
    ar: ActionResult | None = None
    if _capability_allowed("installation_status"):
        ar = dispatch_runtime(
            "installation_status",
            db=db,
            org_id=org_id,
            conv=conv,
            abonado=abonado,
            ctx=ctx,
            canal=canal,
            decision_name="journey_installation_status",
            texto=texto,
        )
        if ar is not None:
            path = "runtime"
            msg = ar.user_message or msg
            _record_action(ctx, get_journey(ctx), ar, action="installation_status")
    set_journey(ctx, step="done", last_user_message=msg, last_action="installation_status")
    return JourneyTurn(
        handled=True,
        user_message=msg,
        journey=journey,
        step="done",
        intent="seguimiento_instalacion",
        domain="services",
        action="installation_status",
        action_status=(ar.status if ar else "unavailable"),
        reason_code=(ar.reason_code if ar else "source_unavailable"),
        correlation_id=(ar.correlation_id if ar else None) or corr,
        data={
            "execution_path": path,
            "honest_unavailable": "installation_status",
            "capability": "unavailable",
            # Campos ausentes de forma explícita (no inventados)
            "installation_id": None,
            "status": None,
            "scheduled_at": None,
            "visit_at": None,
            "technician": None,
            "ticket_id": None,
        },
    )


def _advance_ticket(
    *,
    db: Session | None,
    org_id: str,
    conv: Any,
    abonado: Any | None,
    texto: str,
    ctx: dict[str, Any],
    canal: str,
) -> JourneyTurn:
    corr = str(get_journey(ctx).get("correlation_id") or uuid.uuid4())
    set_journey(ctx, correlation_id=corr, intent="estado_ticket", domain="support", step="respond")
    if abonado is None:
        return JourneyTurn(
            handled=True,
            user_message="Para ver tu ticket necesito identificarte. ¿Me pasás tu DNI?",
            journey="ticket_consulta",
            step="identity",
            correlation_id=corr,
        )
    tid = str(getattr(conv, "ticket_id", "") or "").strip()
    if not tid:
        m = re.search(
            r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
            texto or "",
            re.I,
        )
        tid = m.group(1) if m else ""
    if not tid:
        set_journey(ctx, next_required_input="ticket_id", step="respond")
        return JourneyTurn(
            handled=True,
            user_message="No tengo un ticket asociado a este chat. ¿Me pasás el número?",
            journey="ticket_consulta",
            step="respond",
            correlation_id=corr,
        )
    if not _capability_allowed("show_ticket"):
        return JourneyTurn(
            handled=True,
            user_message="No puedo consultar el ticket ahora.",
            journey="ticket_consulta",
            data={"gap": "show_ticket"},
            correlation_id=corr,
        )
    ar = dispatch_runtime(
        "show_ticket",
        db=db,
        org_id=org_id,
        conv=conv,
        abonado=abonado,
        ctx=ctx,
        canal=canal,
        decision_name="journey_ticket_show",
        parameters={"ticket_id": tid},
        texto=texto,
    )
    if ar is None:
        # Legacy: ownership via same reader
        from app.estate.models import Ticket
        from app.services.abonado_tickets import ticket_pertenece_abonado

        t = db.get(Ticket, tid) if db is not None else None
        if t is None or not ticket_pertenece_abonado(db, org_id, abonado, t):
            ar = ActionResult(
                action="show_ticket",
                status="denied",
                reason_code="foreign_ticket" if t is not None else "ticket_not_found",
                user_message="No tenés acceso a ese ticket." if t else "No encuentro ese ticket.",
                execution_path="legacy",
            )
        else:
            ar = ActionResult(
                action="show_ticket",
                status="success",
                data={"ticket": {"id": tid, "state": t.estado}},
                user_message=f"Ticket {tid}: estado {t.estado or '(sin dato)'}.",
                execution_path="legacy",
            )
    _record_action(ctx, get_journey(ctx), ar, action="show_ticket")
    set_journey(ctx, step="done" if ar.status == "success" else "respond")
    return JourneyTurn(
        handled=True,
        user_message=ar.user_message or "",
        journey="ticket_consulta",
        step=get_journey(ctx).get("step") or "respond",
        action="show_ticket",
        action_status=ar.status,
        reason_code=ar.reason_code,
        correlation_id=ar.correlation_id or corr,
    )


# ---------------------------------------------------------------------------
# Service catalog (Eko 2.2A list + 2.2B selection) — no probes / EFFECT
# ---------------------------------------------------------------------------


def _wants_service_list(texto: str) -> bool:
    t = (texto or "").lower().strip()
    return any(p in t for p in _SERVICE_CATALOG_PHRASES)


def _advance_service_catalog(
    *,
    db: Session | None,
    org_id: str,
    conv: Any,
    abonado: Any | None,
    texto: str,
    ctx: dict[str, Any],
    canal: str,
) -> JourneyTurn:
    """Lista servicios (2.2A) y selección determinística service_id↔login (2.2B)."""
    from app.services.eko_service_selection import (
        format_selection_options,
        looks_like_selection_utterance,
        option_from_row,
        resolve_service_selection,
    )
    from app.services.portal_services import catalog_for_selection

    journey = "service_catalog"
    corr = str(get_journey(ctx).get("correlation_id") or uuid.uuid4())
    set_journey(
        ctx,
        name=journey,
        journey=journey,
        domain="services",
        intent="consulta_servicios",
        correlation_id=corr,
        step="respond",
    )

    if abonado is None:
        if ctx.get("phone_candidates"):
            set_journey(ctx, step="identity", next_required_input="account_selection")
            return JourneyTurn(
                handled=True,
                user_message=(
                    "Encontré más de una cuenta asociada a este número. "
                    "Indicame el DNI de la cuenta que querés consultar."
                ),
                journey=journey,
                step="identity",
                intent="consulta_servicios",
                domain="services",
                action_status="needs_input",
                reason_code="identity_ambiguous",
                correlation_id=corr,
                data={"needs_input": "account_selection"},
            )
        set_journey(ctx, step="identity", next_required_input="identity")
        return JourneyTurn(
            handled=True,
            user_message="Para listar tus servicios necesito identificarte. ¿Me pasás tu DNI?",
            journey=journey,
            step="identity",
            intent="consulta_servicios",
            domain="services",
            action_status="needs_input",
            correlation_id=corr,
        )

    client_number = str(getattr(abonado, "client_number", "") or "").strip()
    if not client_number:
        set_journey(ctx, step="identity", next_required_input="client_number")
        return JourneyTurn(
            handled=True,
            user_message="No tengo el número de cuenta para listar tus servicios.",
            journey=journey,
            step="identity",
            intent="consulta_servicios",
            domain="services",
            action="service_list",
            action_status="needs_input",
            reason_code="missing_client_number",
            correlation_id=corr,
            data={
                "needs_input": "client_number",
                "execution_path": "none",
            },
        )

    wants_list = _wants_service_list(texto)
    pending_opts = list(get_journey(ctx).get("selection_options") or [])
    wants_sel = (not wants_list) and (
        looks_like_selection_utterance(texto)
        or bool(pending_opts and re.fullmatch(r"\s*\d{1,2}\s*", (texto or "")))
    )

    # --- 2.2B selection path (no probes) ---
    if wants_sel and db is not None:
        cat = catalog_for_selection(db, abonado=abonado)
        if cat.get("status") != "ok":
            return JourneyTurn(
                handled=True,
                user_message="No puedo consultar tus servicios en este momento.",
                journey=journey,
                step="respond",
                intent="consulta_servicios",
                domain="services",
                action="service_selection",
                action_status="unavailable",
                reason_code=str(cat.get("reason_code") or "source_unavailable"),
                correlation_id=corr,
            )
        rows = list(cat.get("services") or [])
        result = resolve_service_selection(
            texto=texto,
            catalog=rows,
            client_number=client_number,
            pending_options=pending_opts or None,
        )
        if result.status == "selected" and result.ref is not None:
            apply_service_ref(ctx, result.ref)
            ref = result.ref
            name = ref.product or ref.label or ref.service_type or ref.service_id
            msg = f"Listo: seleccioné «{name}»."
            if ref.login:
                msg += f" (cuenta {ref.login})"
            set_journey(
                ctx,
                step="done",
                last_user_message=msg,
                selection_options=pending_opts or [option_from_row(r) for r in rows],
            )
            return JourneyTurn(
                handled=True,
                user_message=msg,
                journey=journey,
                step="done",
                intent="consulta_servicios",
                domain="services",
                action="service_selection",
                action_status="success",
                correlation_id=corr,
                data={
                    "selected_service_ref": ref.to_dict(),
                    "execution_path": "deterministic",
                },
            )
        if result.status == "denied":
            set_journey(ctx, step="respond", next_required_input="service_selection")
            return JourneyTurn(
                handled=True,
                user_message=result.message or "No puedo seleccionar ese servicio.",
                journey=journey,
                step="respond",
                intent="consulta_servicios",
                domain="services",
                action="service_selection",
                action_status="denied",
                reason_code=result.reason_code,
                correlation_id=corr,
                data={"execution_path": "deterministic"},
            )
        # needs_input / no_match / ambiguous
        options = result.options or [option_from_row(r) for r in rows]
        set_journey(
            ctx,
            step="service_selection",
            next_required_input="service_selection",
            selection_options=options,
            asked_selection=True,
        )
        return JourneyTurn(
            handled=True,
            user_message=result.message or format_selection_options(options),
            journey=journey,
            step="service_selection",
            intent="consulta_servicios",
            domain="services",
            action="service_selection",
            action_status="needs_input",
            reason_code=result.reason_code or "service_selection_required",
            correlation_id=corr,
            data={
                "needs_input": "service_selection",
                "selection_options": options,
                "execution_path": "deterministic",
            },
        )

    # --- 2.2A list path ---
    ar: ActionResult | None = None
    path = "runtime"
    if _capability_allowed("service_list"):
        ar = dispatch_runtime(
            "service_list",
            db=db,
            org_id=org_id,
            conv=conv,
            abonado=abonado,
            ctx=ctx,
            canal=canal,
            decision_name="journey_service_catalog",
            parameters={},
            texto=texto,
        )
    if ar is None:
        from app.services.eko_action_runtime import (
            format_service_list_message,
            public_service_row,
        )
        from app.services.portal_services import evaluar_servicios_portal

        path = "legacy"
        if db is None:
            ar = ActionResult(
                action="service_list",
                status="unavailable",
                reason_code="db_unavailable",
                user_message="No puedo consultar tus servicios en este momento.",
                execution_path="legacy",
            )
        else:
            try:
                raw = evaluar_servicios_portal(db, abonado=abonado)
            except Exception:
                logger.exception("service_catalog legacy: portal_services falló")
                raw = {"status": "unavailable", "reason_code": "source_error", "services": []}
            if str(raw.get("status") or "") != "ok":
                ar = ActionResult(
                    action="service_list",
                    status="unavailable",
                    reason_code=str(raw.get("reason_code") or "source_unavailable"),
                    user_message="No puedo consultar tus servicios en este momento.",
                    execution_path="legacy",
                )
            else:
                items = [
                    public_service_row(s)
                    for s in list(raw.get("services") or [])
                    if isinstance(s, dict) and str(s.get("id") or "").strip()
                ]
                ar = ActionResult(
                    action="service_list",
                    status="success",
                    reason_code=("empty_catalog" if not items else None),
                    user_message=format_service_list_message(items),
                    execution_path="legacy",
                    data={"services": items, "count": len(items)},
                )

    _record_action(ctx, get_journey(ctx), ar, action="service_list")
    msg = ar.user_message or ""

    # Guardar opciones estructuradas para selección posterior (2.2B); sin auto-select.
    if ar.status == "success" and db is not None:
        try:
            cat = catalog_for_selection(db, abonado=abonado)
            if cat.get("status") == "ok":
                opts = [option_from_row(r) for r in list(cat.get("services") or [])]
                set_journey(ctx, selection_options=opts)
        except Exception:
            logger.debug("service_catalog: no pude persistir selection_options", exc_info=True)

    set_journey(ctx, step="done" if ar.status == "success" else "respond", last_user_message=msg)
    return JourneyTurn(
        handled=True,
        user_message=msg,
        journey=journey,
        step=get_journey(ctx).get("step") or "respond",
        intent="consulta_servicios",
        domain="services",
        action="service_list",
        action_status=ar.status,
        reason_code=ar.reason_code,
        correlation_id=ar.correlation_id or corr,
        data={
            "execution_path": path,
            "services": (ar.data or {}).get("services"),
            "count": (ar.data or {}).get("count"),
        },
    )


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def maybe_handle_journey_turn(
    db: Session | None,
    org_id: str,
    conv: Any,
    abonado: Any | None,
    texto: str,
    *,
    canal: str,
    ctx: dict[str, Any],
) -> JourneyTurn | None:
    """Avanza Journey si está habilitado. None → continuar Legacy N1.

    Domain switch: nuevo intent explícito invalida el journey anterior
    y limpia confirmaciones stale.
    """
    if not journeys_enabled(canal=canal, org_id=org_id):
        return None

    from app.services.eko_journey_observability import (
        observe_journey_turn,
        record_security_signal,
    )

    detected = detect_journey_name(texto)
    if detected:
        detected = _canonical_journey(detected)  # type: ignore[assignment]
    st = get_journey(ctx)
    active = _canonical_journey(str(st.get("name") or "").strip())
    started = False
    switched = False
    previous_journey = ""

    # No robar selección de Internet multi-cuenta hacia service_catalog.
    # "el segundo" / "el de casa" deben resolverse en internet_sin_conectividad.
    if (
        active == "internet_sin_conectividad"
        and detected == "service_catalog"
        and not _wants_service_list(texto)
        and (
            str(st.get("next_required_input") or "") == "login"
            or str(st.get("step") or "") == "service_selection"
            or bool(st.get("asked_selection"))
            or bool(ctx.get("multi_cuenta_pendiente"))
        )
    ):
        detected = None

    # Re-entry: volver a connectivity sin auto-diagnóstico
    if (
        active == "billing_self_service"
        and _is_resume_connectivity(texto)
        and not detected
    ):
        detected = "internet_sin_conectividad"

    # Domain switch
    if detected and active and detected != active:
        prev_sel = str(ctx.get("login_seleccionado") or st.get("selected_service") or "")
        previous_journey = active
        switched = True
        had_no_fixed = (
            str(st.get("last_diagnostic_result") or "") == "no_fixed_internet"
            or bool(ctx.get("eko_no_fixed_internet"))
        )
        _clear_stale_confirmation(ctx)
        set_journey(
            ctx,
            previous_journey=active,
            name=detected,
            journey=detected,
            step="switched",
            domain=_domain_for(detected),
            intent=_intent_for(detected),
            diagnostic_started=False,
            last_diagnostic_result=(
                "no_fixed_internet" if had_no_fixed and detected == "internet_sin_conectividad" else ""
            ),
            pending_confirmation=False,
            confirmation_correlation="",
            next_required_input="",
            asked_selection=False,
            selected_service=prev_sel,
            correlation_id=str(uuid.uuid4()),
        )
        ctx["intencion"] = _intent_for(detected)
        active = detected

        # Re-entry connectivity: nunca auto-probe (con o sin selected_service)
        if detected == "internet_sin_conectividad":
            if prev_sel:
                set_journey(
                    ctx,
                    step="respond",
                    selected_service=prev_sel,
                    last_user_message="",
                )
                ctx["login_seleccionado"] = prev_sel
                msg = (
                    f"Volvemos al Internet (cuenta {prev_sel}). "
                    "¿Querés que vuelva a revisar la conexión, o contame qué sigue fallando?"
                )
            elif had_no_fixed:
                set_journey(ctx, step="respond", last_user_message="")
                msg = (
                    "Volvemos al tema de Internet. "
                    "En tu cuenta no veo un servicio de Internet fijo para diagnosticar. "
                    "Si es por móvil, Sensa/TV o factura, decime."
                )
            else:
                set_journey(ctx, step="respond", last_user_message="")
                msg = (
                    "Volvemos al Internet. "
                    "¿Querés que revise la conexión, o contame qué necesitás?"
                )
            set_journey(ctx, last_user_message=msg, next_required_input="")
            turn = JourneyTurn(
                handled=True,
                user_message=msg,
                journey="internet_sin_conectividad",
                step="respond",
                intent="internet",
                domain="internet",
                correlation_id=str(get_journey(ctx).get("correlation_id") or ""),
                data={"reentry": True, "no_auto_diagnostic": True},
            )
            observe_journey_turn(
                turn,
                canal=canal,
                switched=True,
                previous_journey=previous_journey,
            )
            return turn
    elif detected and not active:
        set_journey(ctx, **_new_journey(detected))
        ctx["intencion"] = _intent_for(detected)
        active = detected
        started = True
    elif not active:
        return None

    # Continuity: preserve intent/domain on subsequent turns
    ctx["intencion"] = str(get_journey(ctx).get("intent") or ctx.get("intencion") or "")
    name = _canonical_journey(str(get_journey(ctx).get("name") or active))

    # Domain contamination guard: no diagnostic from billing/ticket/catalog journeys
    if name in ("billing_self_service", "service_catalog") and detect_journey_name(texto) is None:
        # stay in current domain
        pass

    turn: JourneyTurn | None = None
    if name == "internet_sin_conectividad":
        turn = _advance_connectivity(
            db=db, org_id=org_id, conv=conv, abonado=abonado, texto=texto, ctx=ctx, canal=canal
        )
    elif name == "billing_self_service":
        turn = _advance_billing(
            db=db, org_id=org_id, conv=conv, abonado=abonado, texto=texto, ctx=ctx, canal=canal
        )
    elif name == "service_catalog":
        turn = _advance_service_catalog(
            db=db, org_id=org_id, conv=conv, abonado=abonado, texto=texto, ctx=ctx, canal=canal
        )
    elif name == "ticket_consulta":
        turn = _advance_ticket(
            db=db, org_id=org_id, conv=conv, abonado=abonado, texto=texto, ctx=ctx, canal=canal
        )
    elif name == "installation_status":
        turn = _advance_installation_status(
            db=db, org_id=org_id, conv=conv, abonado=abonado, texto=texto, ctx=ctx, canal=canal
        )
    else:
        return None

    if turn is not None:
        completed = turn.step == "done" or (
            turn.journey
            in (
                "billing_self_service",
                "ticket_consulta",
                "service_catalog",
                "installation_status",
            )
            and turn.action_status in ("success", "unavailable")
            and turn.step in ("done", "respond")
        )
        observe_journey_turn(
            turn,
            canal=canal,
            started=started,
            switched=switched,
            previous_journey=previous_journey,
            completed=completed and turn.step == "done",
        )
        # Ambiguous "sí" without live confirmation → signal (no mutation)
        t_low = (texto or "").strip().lower()
        if t_low in ("si", "sí") and not get_journey(ctx).get("pending_confirmation"):
            if turn.data.get("stale_confirmation_guard"):
                record_security_signal(
                    "stale_confirmation",
                    journey=turn.journey,
                    step=turn.step,
                    correlation_id=turn.correlation_id,
                    channel=canal,
                )
    return turn


def journey_turn_to_response(
    turn: JourneyTurn,
    *,
    conv: Any,
    ctx: dict[str, Any],
) -> dict[str, Any]:
    """Adapta JourneyTurn al shape de respuesta N1."""
    out: dict[str, Any] = {
        "ok": True,
        "modo": turn.mode,
        "conversacion_id": getattr(conv, "id", ""),
        "respuesta": turn.user_message,
        "estado": getattr(conv, "estado", ""),
        "intencion": turn.intent or get_journey(ctx).get("intent"),
        "journey": turn.journey,
        "journey_step": turn.step,
        "eko_journey": True,
    }
    if turn.data.get("ticket_id"):
        out["ticket_id"] = turn.data["ticket_id"]
    return out
