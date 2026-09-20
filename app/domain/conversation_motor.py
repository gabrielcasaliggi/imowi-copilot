"""Motor conversacional común (Fase 7).

El significado del turno sale de TurnInterpretation + ConversationState,
no de `paso_idx` ni de `idx + 1`. El LLM puede sugerir; no cubre pasos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.domain.conversation_state import (
    CS_KEY,
    ConversationState,
    Fact,
    LastBotAct,
    PendingBot,
    PendingUser,
    enforce_invariants,
    hydrate_conversation_state,
    upsert_fact,
)
from app.domain.flujos_abonado import (
    PLAYBOOKS,
    es_pregunta_howto_o_causal,
    es_saludo_corto,
    ids_paso_wifi_incompatibles,
    interpreta_alcance_dispositivos,
    primer_paso_pendiente,
)

# --- actos ---------------------------------------------------------------

USER_ANSWER = "ANSWER"
USER_CONFIRM_ACTION = "CONFIRM_ACTION"
USER_REPORT_PERSISTENCE = "REPORT_PERSISTENCE"
USER_REPORT_FACT = "REPORT_FACT"
USER_ASK_HOW_TO = "ASK_HOW_TO"
USER_ASK_CAUSE = "ASK_CAUSE"
USER_ASK_FOLLOWUP = "ASK_FOLLOWUP"
USER_ASK_CLARIFY = "ASK_CLARIFY"
USER_CORRECT_FACT = "CORRECT_FACT"
USER_SIGNAL_DOMAIN = "SIGNAL_DOMAIN"

BOT_ASK_ACTION = "ASK_ACTION"
BOT_ASK_FACT = "ASK_FACT"
BOT_ASK_CONFIRMATION = "ASK_CONFIRMATION"
BOT_ASK_SYMPTOM = "ASK_SYMPTOM"
BOT_OFFER_DERIVATION = "OFFER_DERIVATION"
BOT_PROVIDE_INSTRUCTION = "PROVIDE_INSTRUCTION"
BOT_PROVIDE_INFORMATION = "PROVIDE_INFORMATION"

ACT_ANSWER_USER = "ANSWER_USER"
ACT_RESTATE_PENDING = "RESTATE_PENDING"
ACT_ACK_AND_HOLD = "ACK_AND_HOLD"
ACT_ASK_NEXT_STEP = "ASK_NEXT_STEP"
ACT_PROVIDE_INFO = "PROVIDE_INFO"
ACT_OFFER_DERIVE = "OFFER_DERIVE"
ACT_CLOSE = "CLOSE"
ACT_ESCALATE = "ESCALATE"
ACT_DEFER = "DEFER"

DISCOURSE_INTERCEPT_ACTS = frozenset(
    {
        USER_CONFIRM_ACTION,
        USER_REPORT_PERSISTENCE,
        USER_ASK_CLARIFY,
        USER_ASK_FOLLOWUP,
    }
)

DISCURSO_INTENCIONES = frozenset(
    {
        "internet",
        "internet_ftth",
        "internet_adsl",
        "internet_radio",
        "internet_lento",
        "internet_intermitente",
        "wifi",
        "cambio_clave_wifi",
        "movil",
        "movil_datos",
        "movil_llamadas",
    }
)

_FACT_STEP_COVERS = {
    "alcance_wifi": ("otros_dispositivos_wifi",),
    "dispositivo_sin_ethernet": ("conexion_cableada",),
    "zona_wifi": ("zona_wifi",),
    "luces_ont": ("energia_ont", "luces_los"),
}

_REFERENT_HOWTO_TABLET = "conexion_cableada_tablet"


@dataclass
class TurnInterpretation:
    user_act: str = USER_ANSWER
    referenced: dict[str, Any] | None = None
    domain_signal: str | None = None
    fact_updates: list[tuple[str, Any]] = field(default_factory=list)
    user_question: str | None = None
    proposed_covers: list[str] = field(default_factory=list)
    ia_suggested_step: str | None = None
    ia_suggested_action: str | None = None


@dataclass
class BotAction:
    type: str
    domain_id: str | None = None
    step_id: str | None = None
    referent: str | None = None
    cover_steps: list[str] = field(default_factory=list)


@dataclass
class TurnResult:
    interpretation: TurnInterpretation
    state: ConversationState
    action: BotAction

    def state_patch(self) -> dict[str, Any]:
        return self.state.to_dict()


def classify_step_act(step_id: str, pregunta: str = "") -> str:
    """Clasifica pending.act por step_id estructurado (Gate 11E).

    ``pregunta`` es copy para el usuario (LLM o playbook) y NO aporta semántica
    operacional: COPY ≠ SEMÁNTICA. Se conserva el parámetro por compatibilidad.
    """
    _ = pregunta  # intencional: no clasificar por texto libre
    sid = (step_id or "").strip().lower()
    if not sid:
        return BOT_ASK_FACT
    if (
        "derivar" in sid
        or "turno_campo" in sid
        or sid.startswith("persistencia")
        or sid in ("comparar_plan",)
    ):
        return BOT_OFFER_DERIVATION
    if sid.startswith("reinicio") or "reinici" in sid:
        return BOT_ASK_ACTION
    if any(
        x in sid
        for x in (
            "confirmar_clave",
            "confirmar_ssid",
            "modo_avion",
            "desenchuf",
        )
    ):
        return BOT_ASK_ACTION
    if "sintoma" in sid:
        return BOT_ASK_SYMPTOM
    if sid.startswith("confirmacion") or "confirmacion_" in sid:
        return BOT_ASK_CONFIRMATION
    return BOT_ASK_FACT


def _norm(texto: str) -> str:
    t = (texto or "").lower().strip()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")):
        t = t.replace(a, b)
    t = re.sub(r"[¿?¡!.,;:]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _active_fact_value(cs: ConversationState, key: str) -> Any:
    did = cs.active_domain_id
    for fact in cs.facts:
        if fact.domain_id == did and fact.key == key and fact.status == "active":
            return fact.value
    return None


def _ref_from_pending_bot(cs: ConversationState) -> dict[str, Any] | None:
    pb = cs.pending_bot
    if not pb:
        return None
    return {
        "source": "pending.bot",
        "act": pb.act,
        "step_id": pb.step_id,
        "referent": pb.referent or pb.step_id,
        "domain_id": pb.domain_id,
    }


def _ref_from_pending_user(cs: ConversationState) -> dict[str, Any] | None:
    pu = cs.pending_user
    if not pu or pu.status != "open":
        return None
    return {
        "source": "pending.user",
        "act": pu.act,
        "step_id": None,
        "referent": pu.referent,
        "domain_id": pu.domain_id,
    }


def _ref_from_last_bot(cs: ConversationState) -> dict[str, Any] | None:
    last = cs.last_bot_act
    if not last:
        return None
    return {
        "source": "last_bot_act",
        "act": last.act,
        "step_id": last.step_id,
        "referent": last.referent or last.step_id,
        "domain_id": last.domain_id,
    }


def _es_confirm_action(t: str, cs: ConversationState) -> bool:
    if any(
        k in t
        for k in (
            "ya lo hice",
            "ya la hice",
            "ya lo reinici",
            "ya la reinici",
            "ya reinici",
        )
    ):
        return True
    pending = cs.pending_bot
    if pending and pending.act == BOT_ASK_ACTION:
        if t in ("listo", "hecho", "reinicie", "reinicio"):
            return True
        if t.startswith("si ") and any(k in t for k in ("ya lo hice", "ya la hice", "listo")):
            return True
    return False


def _tiene_referente_accion(cs: ConversationState) -> bool:
    if cs.pending_bot:
        return True
    last = cs.last_bot_act
    return bool(last and last.act in (BOT_ASK_ACTION, BOT_ASK_CONFIRMATION, BOT_ASK_FACT))


def _es_persistencia(t: str) -> bool:
    return any(
        k in t
        for k in (
            "sigue igual",
            "todavia no",
            "sigue sin",
            "no mejoro",
            "sigue fallando",
            "igual no anda",
            "igual no funciona",
        )
    )


def _es_ask_clarify(t: str, raw: str) -> bool:
    if t in ("que cosa", "que", "a que te referis", "a que", "como"):
        return True
    if "que cosa" in t:
        return True
    compact = _norm(raw)
    return compact in ("que", "eh") and ("?" in (raw or "") or "¿" in (raw or ""))


def _es_ask_followup(t: str) -> bool:
    return any(
        k in t
        for k in (
            "entonces que hago",
            "entonces que hago",
            "y ahora que hago",
            "que hago entonces",
            "y ahora que",
        )
    ) or t in ("entonces que hago", "y ahora")


def _es_correccion_alcance_explicita(texto: str) -> bool:
    t = _norm(texto)
    return any(
        k in t
        for k in (
            "tambien",
            "ninguno funciona",
            "ningun equipo",
            "ninguno anda",
            "me referia a todos",
            "me refiero a todos",
            "todos los equipos",
            "todos los dispositivo",
        )
    )


def _signal_domain(t: str, cs: ConversationState) -> str | None:
    slot = cs.active_slot()
    kind = slot.kind if slot else None
    if kind == "tecnico" and any(
        k in t for k in ("cuanto debo", "la factura", "mi saldo", "el saldo")
    ):
        return "administrativo"
    if kind == "administrativo" and any(
        k in t
        for k in (
            "sigo sin internet",
            "no tengo internet",
            "no me anda el wifi",
            "sin internet",
        )
    ):
        return "tecnico"
    return None


def _luces_fact(t: str) -> tuple[str, Any] | None:
    if re.search(r"\bpon\b", t) and "rojo" in t:
        return ("luces_ont", "pon_rojo")
    if re.search(r"\bpon\b", t) and "verde" in t:
        return ("luces_ont", "pon_verde")
    return None


def _kind_signal_for_turn(raw: str, t: str, cs: ConversationState) -> str | None:
    from app.domain.domain_lifecycle import domain_spans_in_order

    spans = domain_spans_in_order(raw)
    active = cs.active_slot()
    active_kind = active.kind if active else None
    if spans:
        primary = spans[0]
        if primary != active_kind:
            return primary
        return None
    return _signal_domain(t, cs)


def interpret_turn(
    texto: str,
    cs: ConversationState,
    ctx: dict | None = None,
) -> TurnInterpretation:
    """Normaliza señales existentes. No es un NLP paralelo."""
    ctx = ctx if isinstance(ctx, dict) else {}
    raw = texto or ""
    t = _norm(raw)
    interp = TurnInterpretation()

    luces = _luces_fact(t)
    alcance = interpreta_alcance_dispositivos(raw)
    prev_alcance = _active_fact_value(cs, "alcance_wifi")
    if prev_alcance is None and isinstance(ctx.get("hechos"), dict):
        prev_alcance = ctx["hechos"].get("alcance_wifi")

    domain = _kind_signal_for_turn(raw, t, cs)
    interp.domain_signal = domain
    other_kind = bool(domain and cs.active_slot() and domain != cs.active_slot().kind)

    if not other_kind:
        if _es_confirm_action(t, cs) and _tiene_referente_accion(cs):
            interp.user_act = USER_CONFIRM_ACTION
            interp.referenced = _ref_from_pending_bot(cs) or _ref_from_last_bot(cs)
            step = (interp.referenced or {}).get("step_id")
            if step:
                interp.proposed_covers = [step]
            return interp

        if _es_persistencia(t) and (
            (cs.pending_bot and cs.pending_bot.act in (BOT_ASK_ACTION, BOT_ASK_CONFIRMATION))
            or (cs.last_bot_act and cs.last_bot_act.act in (BOT_ASK_ACTION, BOT_PROVIDE_INSTRUCTION))
        ):
            interp.user_act = USER_REPORT_PERSISTENCE
            interp.referenced = _ref_from_pending_bot(cs) or _ref_from_last_bot(cs)
            step = (interp.referenced or {}).get("step_id")
            if step:
                interp.proposed_covers = [step]
            return interp

        if _es_ask_clarify(t, raw) and (cs.pending_bot or cs.last_bot_act):
            interp.user_act = USER_ASK_CLARIFY
            interp.referenced = _ref_from_pending_bot(cs) or _ref_from_last_bot(cs)
            interp.user_question = raw.strip()[:200]
            return interp

        if _es_ask_followup(t):
            interp.user_act = USER_ASK_FOLLOWUP
            interp.referenced = _ref_from_pending_user(cs) or _ref_from_last_bot(cs)
            interp.user_question = raw.strip()[:200]
            return interp

    if es_pregunta_howto_o_causal(raw):
        causal = any(k in t for k in ("por que", "porque"))
        interp.user_act = USER_ASK_CAUSE if causal else USER_ASK_HOW_TO
        interp.user_question = raw.strip()[:200]
        hechos = ctx.get("hechos") if isinstance(ctx.get("hechos"), dict) else {}
        if hechos.get("dispositivo_sin_ethernet") or "tablet" in t or "celular" in t:
            if any(k in t for k in ("cable", "ethernet", "conecto")):
                interp.referenced = {
                    "source": "hechos",
                    "referent": _REFERENT_HOWTO_TABLET,
                    "step_id": "conexion_cableada",
                }
        return interp

    if domain:
        interp.user_act = USER_SIGNAL_DOMAIN
        return interp

    if alcance and prev_alcance and alcance != prev_alcance:
        interp.user_act = USER_CORRECT_FACT
        interp.fact_updates = [("alcance_wifi", alcance)]
        interp.proposed_covers = list(_FACT_STEP_COVERS.get("alcance_wifi") or ())
        return interp

    if luces:
        interp.user_act = USER_REPORT_FACT
        interp.fact_updates = [luces]
        interp.proposed_covers = list(_FACT_STEP_COVERS.get("luces_ont") or ())
        return interp

    if alcance:
        interp.user_act = USER_REPORT_FACT
        interp.fact_updates = [("alcance_wifi", alcance)]
        interp.proposed_covers = list(_FACT_STEP_COVERS.get("alcance_wifi") or ())
        return interp

    if cs.pending_bot:
        pb = cs.pending_bot
        # Respuesta sustantiva a ASK_FACT: el Motor cubre el step (no el LLM).
        # Evitar meta-continuaciones ("dale, seguimos…") que no aportan el dato.
        if (
            pb.act in (BOT_ASK_FACT, BOT_ASK_SYMPTOM)
            and pb.step_id
            and _texto_responde_ask_fact(raw)
        ):
            interp.user_act = USER_REPORT_FACT
            interp.referenced = _ref_from_pending_bot(cs)
            interp.proposed_covers = [str(pb.step_id)]
            return interp
        interp.user_act = USER_ANSWER
        interp.referenced = _ref_from_pending_bot(cs)
        return interp

    interp.user_act = USER_ANSWER
    return interp


def _texto_responde_ask_fact(texto: str) -> bool:
    """True si el turno aporta un dato (no saludo ni 'seguí vos')."""
    raw = (texto or "").strip()
    if not raw or es_saludo_corto(raw):
        return False
    if es_pregunta_howto_o_causal(raw):
        return False
    t = _norm(raw)
    if t.startswith("seguimos") or " seguimos " in f" {t} ":
        return False
    # Queja de corte / reiteración de síntoma ≠ respuesta al ASK_FACT pendiente.
    if any(
        k in t
        for k in (
            "no tengo internet",
            "no hay internet",
            "sin internet",
            "dejo de funcionar",
            "dejó de funcionar",
            "me dejo de funcionar",
            "me dejó de funcionar",
            "internet dejo de",
            "internet dejó de",
            "sigo sin",
            "sigue sin",
            "anda mal",
            "anda lento",
            "internet anda",
            "wifi anda",
            "wi-fi anda",
            "no anda",
            "no funciona",
            "mal el internet",
            "mal el wifi",
            "internet mal",
            "wifi mal",
        )
    ):
        return False
    meta = (
        "segui vos",
        "seguí vos",
        "dale, seguí",
        "dale segui",
        "dale, sigue",
        "contame que",
        "contame qué",
        "decime el proximo",
        "decime el próximo",
        "que mas necesit",
        "qué más necesit",
        "abramos visita",
        "probemos reiniciar",
        "prefiero seguir",
        "seguir aca",
        "seguir acá",
        "un poco mas",
        "un poco más",
    )
    if any(m in t for m in meta):
        return False
    from app.domain.flujos_abonado import respuesta_paso_ok

    ok = respuesta_paso_ok(raw)
    if ok is True:
        return True
    # ok is False (p.ej. «sigue igual») sigue siendo respuesta sustantiva al ASK_FACT:
    # el cover avanza al siguiente paso. La reiteración de síntoma ya se filtró arriba.
    tokens = [w for w in t.split() if w not in {"si", "sí", "no", "ok", "dale"}]
    return len(tokens) >= 2


def interpretation_from_ia(
    ia_result: dict | None,
    texto: str,
    cs: ConversationState,
    ctx: dict | None = None,
) -> TurnInterpretation:
    """Adapter: la IA sugiere; el acto lo decide interpret_turn. No copia covers del LLM."""
    interp = interpret_turn(texto, cs, ctx)
    raw = ia_result if isinstance(ia_result, dict) else {}
    interp.ia_suggested_step = str(raw.get("paso_cubierto") or "").strip() or None
    interp.ia_suggested_action = str(raw.get("accion") or "").strip() or None
    return interp


def cover_step(cs: ConversationState, step_id: str | None) -> None:
    if not step_id:
        return
    slot = cs.active_slot()
    if slot is None:
        return
    sid = str(step_id).strip()
    if sid and sid not in slot.covered_steps:
        slot.covered_steps.append(sid)


def _hechos_para_omitir(cs: ConversationState, ctx: dict | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(ctx, dict) and isinstance(ctx.get("hechos"), dict):
        out.update(ctx["hechos"])
    did = cs.active_domain_id
    for fact in cs.facts:
        if fact.domain_id == did and fact.status == "active":
            out[fact.key] = fact.value
    return out


def _next_uncovered_step(
    cs: ConversationState,
    playbook_steps: list | None,
    ctx: dict | None,
) -> str | None:
    slot = cs.active_slot()
    if slot is None:
        return None
    pasos = playbook_steps
    if not pasos:
        pasos = PLAYBOOKS.get(slot.playbook) or []
    if not pasos:
        return None
    extra = ids_paso_wifi_incompatibles(_hechos_para_omitir(cs, ctx))
    idx = primer_paso_pendiente(pasos, slot.covered_steps, extra_omitir=extra)
    if idx < 0 or idx >= len(pasos):
        return None
    return str(getattr(pasos[idx], "id", "") or "") or None


def _apply_facts(cs: ConversationState, interp: TurnInterpretation) -> None:
    did = cs.active_domain_id or "tec-1"
    as_correction = interp.user_act == USER_CORRECT_FACT
    for key, value in interp.fact_updates:
        upsert_fact(
            cs,
            Fact(
                key=str(key),
                value=value,
                domain_id=did,
                source_turn=cs.turn,
                status="active",
            ),
            as_correction=as_correction,
        )
    for step_id in interp.proposed_covers:
        cover_step(cs, step_id)


def _action_next(cs: ConversationState, steps: list | None, ctx: dict | None) -> BotAction:
    nxt = _next_uncovered_step(cs, steps, ctx)
    if not nxt:
        return BotAction(
            type=ACT_OFFER_DERIVE,
            domain_id=cs.active_domain_id,
        )
    return BotAction(
        type=ACT_ASK_NEXT_STEP,
        domain_id=cs.active_domain_id,
        step_id=nxt,
        referent=nxt,
    )


@dataclass
class ResolvedAuthorization:
    """Resultado de autorizar un cierre propuesto. Sin I/O."""

    allow: bool
    action: BotAction
    reason: str = ""
    message: str = ""
    proposal_source: str = ""


def authorize_resolved(
    cs: ConversationState,
    proposal: Any,
    mensaje_cliente: str,
    legacy_ctx: dict | None = None,
) -> ResolvedAuthorization:
    """Motor: autoriza CLOSE o demota a ASK. No cierra hilos ni envía encuesta.

    step_hint del proposal se ignora como cover (contrato 10B).
    """
    from app.domain.action_proposal import (
        ACTION_RESOLVED,
        ActionProposal,
        evaluate_resolved,
    )

    enforce_invariants(cs)
    if not isinstance(proposal, ActionProposal):
        proposal = ActionProposal(
            action=str(getattr(proposal, "action", "") or ACTION_RESOLVED),
            source=str(getattr(proposal, "source", "") or "llm"),
            reason=str(getattr(proposal, "reason", "") or ""),
            message=str(getattr(proposal, "message", "") or ""),
            step_hint=getattr(proposal, "step_hint", None),
        )
    decision = evaluate_resolved(proposal, mensaje_cliente)
    # Evidencia de dominio activo solo se lee; no se muta active_domain_id.
    _ = legacy_ctx
    did = cs.active_domain_id
    if decision.allow:
        return ResolvedAuthorization(
            allow=True,
            action=BotAction(type=ACT_CLOSE, domain_id=did),
            reason=decision.reason,
            message=decision.message or proposal.message,
            proposal_source=proposal.source,
        )
    return ResolvedAuthorization(
        allow=False,
        action=BotAction(type=ACT_ASK_NEXT_STEP, domain_id=did),
        reason=decision.reason,
        message=decision.message or proposal.message,
        proposal_source=proposal.source,
    )


@dataclass
class EscalateAuthorization:
    """Resultado de autorizar una escalación propuesta. Sin I/O."""

    allow: bool
    action: BotAction
    reason: str = ""
    message: str = ""
    proposal_source: str = ""


def authorize_escalate(
    cs: ConversationState,
    proposal: Any,
    mensaje_cliente: str,
    legacy_ctx: dict | None = None,
    *,
    turnos_diagnostico: int = 0,
    intencion: str = "",
) -> EscalateAuthorization:
    """Motor: autoriza ESCALATE o demota a ASK. No crea tickets ni notifica.

    step_hint del proposal se ignora como cover (contrato 10B).
    No muta active_domain_id.
    """
    from app.domain.action_proposal import (
        ACTION_ESCALATE,
        ActionProposal,
        evaluate_escalate,
    )

    enforce_invariants(cs)
    if not isinstance(proposal, ActionProposal):
        proposal = ActionProposal(
            action=str(getattr(proposal, "action", "") or ACTION_ESCALATE),
            source=str(getattr(proposal, "source", "") or "llm"),
            reason=str(getattr(proposal, "reason", "") or ""),
            message=str(getattr(proposal, "message", "") or ""),
            step_hint=getattr(proposal, "step_hint", None),
        )
    ctx = legacy_ctx if isinstance(legacy_ctx, dict) else {}
    turnos = turnos_diagnostico
    if not turnos:
        try:
            turnos = int(ctx.get("diag_turnos") or 0)
        except (TypeError, ValueError):
            turnos = 0
    intent = (intencion or str(ctx.get("intencion") or "")).strip()
    decision = evaluate_escalate(
        proposal,
        mensaje_cliente,
        turnos_diagnostico=turnos,
        intencion=intent,
    )
    did = cs.active_domain_id
    if decision.allow:
        return EscalateAuthorization(
            allow=True,
            action=BotAction(type=ACT_ESCALATE, domain_id=did),
            reason=decision.reason,
            message=decision.message or proposal.message,
            proposal_source=proposal.source,
        )
    return EscalateAuthorization(
        allow=False,
        action=BotAction(type=ACT_ASK_NEXT_STEP, domain_id=did),
        reason=decision.reason,
        message=decision.message or proposal.message,
        proposal_source=proposal.source,
    )


def process_turn(
    cs: ConversationState,
    interpretation: TurnInterpretation,
    legacy_ctx: dict | None = None,
    *,
    playbook_steps: list | None = None,
) -> TurnResult:
    """Decide BotAction. El cursor no es la semántica del turno."""
    ctx = legacy_ctx if isinstance(legacy_ctx, dict) else {}
    enforce_invariants(cs)
    _apply_facts(cs, interpretation)
    act = interpretation.user_act
    ref = interpretation.referenced or {}

    if act in (USER_CORRECT_FACT, USER_REPORT_FACT):
        pending = cs.pending_bot
        covered_pending = bool(
            pending
            and pending.step_id
            and pending.step_id in (cs.active_slot().covered_steps if cs.active_slot() else [])
        )
        if covered_pending:
            cs.pending_bot = None
            slot = cs.active_slot()
            if slot is not None:
                slot.pending_bot = None
            action = _action_next(cs, playbook_steps, ctx)
        else:
            action = BotAction(type=ACT_DEFER, domain_id=cs.active_domain_id)
        return TurnResult(interpretation=interpretation, state=cs, action=action)

    if act == USER_SIGNAL_DOMAIN:
        action = BotAction(
            type=ACT_DEFER,
            domain_id=cs.active_domain_id,
            referent=interpretation.domain_signal,
        )
        return TurnResult(interpretation=interpretation, state=cs, action=action)

    if act == USER_ASK_CLARIFY:
        pending = cs.pending_bot
        action = BotAction(
            type=ACT_RESTATE_PENDING,
            domain_id=(pending.domain_id if pending else cs.active_domain_id),
            step_id=pending.step_id if pending else ref.get("step_id"),
            referent=(pending.referent if pending else None) or ref.get("referent"),
        )
        return TurnResult(interpretation=interpretation, state=cs, action=action)

    if act in (USER_ASK_HOW_TO, USER_ASK_CAUSE, USER_ASK_FOLLOWUP):
        referent = ref.get("referent")
        if act != USER_ASK_FOLLOWUP:
            cs.pending_user = PendingUser(
                act=act,
                text=(interpretation.user_question or "")[:500],
                referent=referent,
                domain_id=cs.active_domain_id,
                turn=cs.turn,
                status="open",
            )
            slot = cs.active_slot()
            if slot is not None:
                slot.pending_user = cs.pending_user
        else:
            if cs.pending_user:
                cs.pending_user.status = "answered"
        cs.last_bot_act = LastBotAct(
            act=BOT_PROVIDE_INSTRUCTION,
            referent=referent,
            domain_id=cs.active_domain_id,
            step_id=ref.get("step_id"),
            turn=cs.turn,
        )
        action = BotAction(
            type=ACT_ANSWER_USER,
            domain_id=cs.active_domain_id,
            step_id=ref.get("step_id"),
            referent=referent,
        )
        return TurnResult(interpretation=interpretation, state=cs, action=action)

    if act in (USER_CONFIRM_ACTION, USER_REPORT_PERSISTENCE):
        step_id = ref.get("step_id") or (cs.pending_bot.step_id if cs.pending_bot else None)
        if not step_id:
            action = BotAction(
                type=ACT_RESTATE_PENDING if cs.pending_bot else ACT_DEFER,
                domain_id=cs.active_domain_id,
                step_id=cs.pending_bot.step_id if cs.pending_bot else None,
            )
            return TurnResult(interpretation=interpretation, state=cs, action=action)
        cover_step(cs, step_id)
        did = cs.active_domain_id or "tec-1"
        key = f"accion_{step_id}"
        value = "realizada_sin_mejora" if act == USER_REPORT_PERSISTENCE else "realizada"
        upsert_fact(
            cs,
            Fact(key=key, value=value, domain_id=did, source_turn=cs.turn, status="active"),
        )
        if act == USER_REPORT_PERSISTENCE:
            upsert_fact(
                cs,
                Fact(
                    key="resultado_accion",
                    value="sin_mejora",
                    domain_id=did,
                    source_turn=cs.turn,
                    status="active",
                ),
            )
        cs.pending_bot = None
        action = _action_next(cs, playbook_steps, ctx)
        action.cover_steps = [step_id]
        action.referent = step_id
        return TurnResult(interpretation=interpretation, state=cs, action=action)

    action = BotAction(type=ACT_DEFER, domain_id=cs.active_domain_id)
    return TurnResult(interpretation=interpretation, state=cs, action=action)


def stamp_bot_question(
    ctx: dict,
    *,
    step_id: str,
    pregunta: str,
    intencion: str = "",
) -> None:
    """Marca pending.bot + last_bot_act de una pregunta del playbook."""
    if _es_mensaje_no_conversacional(pregunta):
        return
    cs = hydrate_conversation_state(ctx)
    if intencion:
        slot = cs.active_slot()
        if slot and not slot.playbook:
            slot.playbook = intencion
    act = classify_step_act(step_id, pregunta)
    # Gate 11E: act viene de step_id; pregunta solo se usa arriba para
    # filtrar mensajes no conversacionales (no para semántica de pending).
    did = cs.active_domain_id
    cs.pending_bot = PendingBot(
        act=act,
        step_id=step_id or None,
        referent=step_id or None,
        domain_id=did,
        turn=cs.turn,
    )
    cs.last_bot_act = LastBotAct(
        act=act,
        referent=step_id or None,
        domain_id=did,
        step_id=step_id or None,
        turn=cs.turn,
    )
    slot = cs.active_slot()
    if slot is not None:
        slot.pending_bot = cs.pending_bot
        slot.last_bot_act = cs.last_bot_act
    ctx[CS_KEY] = cs.to_dict()


def stamp_pending_user(
    ctx: dict,
    *,
    act: str,
    text: str = "",
    referent: str | None = None,
    step_id: str | None = None,
) -> None:
    cs = hydrate_conversation_state(ctx)
    cs.pending_user = PendingUser(
        act=act,
        text=(text or "")[:500],
        referent=referent,
        domain_id=cs.active_domain_id,
        turn=cs.turn,
        status="open",
    )
    cs.last_bot_act = LastBotAct(
        act=BOT_PROVIDE_INSTRUCTION,
        referent=referent,
        domain_id=cs.active_domain_id,
        step_id=step_id,
        turn=cs.turn,
    )
    ctx[CS_KEY] = cs.to_dict()


def apply_cs_to_legacy(ctx: dict, cs: ConversationState) -> None:
    """cs es fuente semántica: proyecta a campos legacy de compatibilidad."""
    from app.domain.conversation_state import map_playbook_to_kind, project_legacy

    enforce_invariants(cs)
    slot = cs.active_slot()
    if slot is not None:
        pasos = PLAYBOOKS.get(slot.playbook) or []
        if pasos:
            extra = ids_paso_wifi_incompatibles(_hechos_para_omitir(cs, ctx))
            slot.cursor = primer_paso_pendiente(
                pasos, slot.covered_steps, extra_omitir=extra
            )
            if slot.cursor > len(pasos) - 1:
                slot.cursor = max(len(pasos) - 1, 0)
    prev_intent = str(ctx.get("intencion") or "")
    proj = project_legacy(cs)
    new_intent = str(proj.get("intencion") or "")
    kind_changed = bool(
        prev_intent
        and prev_intent not in ("general", "multi_tema")
        and new_intent
        and map_playbook_to_kind(prev_intent) != map_playbook_to_kind(new_intent)
    )
    proj_hechos = dict(proj.get("hechos") or {})
    if kind_changed:
        ctx["hechos"] = proj_hechos
        ctx["pasos_cubiertos"] = [
            str(x) for x in (proj.get("pasos_cubiertos") or []) if str(x).strip()
        ]
    else:
        hechos = dict(ctx.get("hechos") or {}) if isinstance(ctx.get("hechos"), dict) else {}
        hechos.update(proj_hechos)
        ctx["hechos"] = hechos
        # Gate 12: proyección exacta CS → legacy (no unión que resucite stale).
        ctx["pasos_cubiertos"] = [
            str(x) for x in (proj.get("pasos_cubiertos") or []) if str(x).strip()
        ]
    ctx["paso_idx"] = int(proj.get("paso_idx") or 0)
    ctx["intencion"] = proj["intencion"]
    pendiente = proj.get("intencion_tecnica_pendiente") or ""
    if pendiente:
        ctx["intencion_tecnica_pendiente"] = pendiente
    elif kind_changed:
        ctx.pop("intencion_tecnica_pendiente", None)
    ctx[CS_KEY] = cs.to_dict()
    ctx["_cs_source"] = "semantic"


def _es_mensaje_no_conversacional(texto: str) -> bool:
    t = (texto or "").lower()
    if not t:
        return True
    if "encuesta" in t or "calific" in t:
        return True
    if t.startswith("[sistema]") or t.startswith("[agente]"):
        return True
    return False
