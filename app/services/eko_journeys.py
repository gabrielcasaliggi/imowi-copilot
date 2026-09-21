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
    "billing_consulta",
    "ticket_consulta",
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
    "tengo deuda",
    "donde pago",
    "dónde pago",
    "quiero pagar",
    "consultar saldo",
    "mi saldo",
    "deuda",
)

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
    # Billing / ticket antes que connectivity genérico con "deuda" vs "internet"
    if any(p in t for p in _TICKET_PHRASES):
        return "ticket_consulta"
    if any(p in t for p in _BILLING_PHRASES) and "internet" not in t:
        return "billing_consulta"
    if any(p in t for p in _CONNECTIVITY_PHRASES):
        return "internet_sin_conectividad"
    if any(p in t for p in _BILLING_PHRASES):
        return "billing_consulta"
    return None


def _domain_for(name: JourneyName) -> str:
    if name == "billing_consulta":
        return "billing"
    if name == "ticket_consulta":
        return "support"
    return "internet"


def _intent_for(name: JourneyName) -> str:
    if name == "billing_consulta":
        return "facturacion"
    if name == "ticket_consulta":
        return "estado_ticket"
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
        "el internet",
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
        t in ("y el internet?", "¿y el internet?", "el internet?")
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
        _apply_service_selection(ctx, login, previous=prev_sel)

    selected = str(ctx.get("login_seleccionado") or get_journey(ctx).get("selected_service") or "").strip()
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

    if obs == "pppoe_session_down":
        _mark_confirmation_pending(ctx, corr=corr)
        set_journey(ctx, step="decide", last_user_message=msg)
        return JourneyTurn(
            handled=True,
            user_message=msg,
            journey="internet_sin_conectividad",
            step="decide",
            action="run_diagnostic_pppoe",
            action_status=ar.status,
            correlation_id=ar.correlation_id or corr,
            data={"observation": obs, "execution_path": path, "decision": "offer_escalate"},
        )

    if obs == "pppoe_session_up":
        set_journey(ctx, step="respond", next_required_input="", last_user_message=msg, pending_confirmation=False)
        ctx["pppoe_informado"] = True
        return JourneyTurn(
            handled=True,
            user_message=msg,
            journey="internet_sin_conectividad",
            step="respond",
            action="run_diagnostic_pppoe",
            action_status=ar.status,
            correlation_id=ar.correlation_id or corr,
            data={"observation": obs, "execution_path": path, "decision": "local_checks"},
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
        correlation_id=ar.correlation_id or corr,
        data={"observation": obs, "execution_path": path},
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
    prev = (previous or "").strip()
    login_n = (login or "").strip()
    set_journey(
        ctx,
        selected_service=login_n,
        next_required_input="",
        asked_selection=False,
    )
    ctx["login_seleccionado"] = login_n
    ctx.pop("multi_cuenta_pendiente", None)
    if prev and login_n and prev != login_n:
        # Contradicción: invalidar observación/diagnóstico del servicio anterior
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
    corr = str(get_journey(ctx).get("correlation_id") or uuid.uuid4())
    set_journey(ctx, correlation_id=corr, intent="facturacion", domain="billing", step="respond")
    if abonado is None:
        set_journey(ctx, step="identity", next_required_input="identity")
        return JourneyTurn(
            handled=True,
            user_message="Para consultar tu saldo necesito identificarte. ¿Me pasás tu DNI?",
            journey="billing_consulta",
            step="identity",
            correlation_id=corr,
        )
    if not _capability_allowed("show_balance"):
        return JourneyTurn(
            handled=True,
            user_message="No puedo consultar el saldo ahora.",
            journey="billing_consulta",
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
        # Legacy contractual: Facts via same Facts helpers as Runtime executor
        from app.services.eco_voice import mensaje_saldo_padron
        from app.services.eko_context import billing_amount_str, build_eko_facts

        facts = build_eko_facts(abonado, db=db, org_id=org_id)
        amount = billing_amount_str(facts)
        if amount is None:
            ar = ActionResult(
                action="show_balance",
                status="unavailable",
                reason_code="billing_unavailable",
                user_message="No puedo consultar el saldo en este momento.",
                execution_path="legacy",
            )
        else:
            ar = ActionResult(
                action="show_balance",
                status="success",
                data={"amount": amount, "billing_status": (facts.get("billing") or {}).get("status")},
                user_message=mensaje_saldo_padron(amount, incluir_ov=False),
                execution_path="legacy",
            )
        path = "legacy"
    _record_action(ctx, get_journey(ctx), ar, action="show_balance")

    msg = ar.user_message or ""
    # open_OV only if user asked to pay / where to pay
    t = (texto or "").lower()
    if any(k in t for k in ("pagar", "donde pago", "dónde pago", "quiero pagar")):
        if _capability_allowed("open_OV"):
            ov = dispatch_runtime(
                "open_OV",
                db=db,
                org_id=org_id,
                conv=conv,
                abonado=abonado,
                ctx=ctx,
                canal=canal,
                decision_name="journey_billing_ov",
                parameters={"destination": "pagar"},
                texto=texto,
            )
            if ov is not None and ov.status == "success":
                msg = f"{msg}\n{ov.user_message}".strip()
                _record_action(ctx, get_journey(ctx), ov, action="open_OV")

    set_journey(ctx, step="done" if ar.status == "success" else "respond")
    return JourneyTurn(
        handled=True,
        user_message=msg,
        journey="billing_consulta",
        step=get_journey(ctx).get("step") or "respond",
        action="show_balance",
        action_status=ar.status,
        reason_code=ar.reason_code,
        correlation_id=ar.correlation_id or corr,
        data={"execution_path": path},
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
    st = get_journey(ctx)
    active = str(st.get("name") or "").strip()
    started = False
    switched = False
    previous_journey = ""

    # Re-entry: volver a connectivity sin auto-diagnóstico
    if (
        active == "billing_consulta"
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
    name = str(get_journey(ctx).get("name") or active)

    # Domain contamination guard: no diagnostic from billing/ticket journeys
    if name == "billing_consulta" and detect_journey_name(texto) is None:
        # stay in billing
        pass

    turn: JourneyTurn | None = None
    if name == "internet_sin_conectividad":
        turn = _advance_connectivity(
            db=db, org_id=org_id, conv=conv, abonado=abonado, texto=texto, ctx=ctx, canal=canal
        )
    elif name == "billing_consulta":
        turn = _advance_billing(
            db=db, org_id=org_id, conv=conv, abonado=abonado, texto=texto, ctx=ctx, canal=canal
        )
    elif name == "ticket_consulta":
        turn = _advance_ticket(
            db=db, org_id=org_id, conv=conv, abonado=abonado, texto=texto, ctx=ctx, canal=canal
        )
    else:
        return None

    if turn is not None:
        completed = turn.step == "done" or (
            turn.journey in ("billing_consulta", "ticket_consulta")
            and turn.action_status == "success"
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
