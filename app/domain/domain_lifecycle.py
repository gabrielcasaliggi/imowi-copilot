"""Fase 8A — contrato de lifecycle de dominios (puro, sin canal productivo).

Operaciones: create / activate / pause / resume / close / refine.
El pending y last_bot_act viven en el DomainSlot; el pending global de
ConversationState es la proyección del dominio activo.

    operación   | precondición                         | transición              | postcondición
    ------------|--------------------------------------|-------------------------|----------------------------------------------
    create      | kind válido; no existe slot del kind | +slot paused→active     | id fijo (tec-1/adm-1/com-1); ≤3; no borra otros
    activate    | slot existe y no closed              | paused→active           | único active; pending reconciliado y proyectado
    pause       | slot existe y no closed              | active→paused           | facts/covered/cursor/pending/last/playbook intactos
    resume      | slot paused (no closed)              | paused→active           | mismos facts/covered; pending válido o siguiente real
    close       | slot existe                          | active|paused→closed    | no reabre por señal histórica
    refine      | slot activo/paused; mismo kind       | playbook'               | mismo id; facts compatibles; covered filtrados

Política por kind: un slot. Segunda señal del mismo kind = resume/reuse/refine,
nunca TEC-2. Closed no se reabre (eso es reopen explícito, Fase 8B).
"""

from __future__ import annotations

from typing import Any

from app.domain.conversation_state import (
    KIND_ADMIN,
    KIND_COMERCIAL,
    KIND_TECNICO,
    KINDS,
    MAX_DOMAINS,
    SLOT_ID,
    ConversationState,
    DomainSlot,
    Fact,
    LastBotAct,
    PendingBot,
    PendingUser,
    enforce_invariants,
    map_playbook_to_kind,
    push_domain_stack,
    upsert_fact,
)

# --- errores del contrato ------------------------------------------------

class DomainLifecycleError(ValueError):
    """Violación de precondición del lifecycle."""


class DomainKindError(DomainLifecycleError):
    pass


class DomainExistsError(DomainLifecycleError):
    pass


class DomainClosedError(DomainLifecycleError):
    pass


class DomainCapacityError(DomainLifecycleError):
    pass


class DomainNotFoundError(DomainLifecycleError):
    pass


_PLAYBOOK_DEFAULT = {
    KIND_TECNICO: "internet",
    KIND_ADMIN: "facturacion",
    KIND_COMERCIAL: "alta_plan",
}

# Señales explícitas (no NLP). Reutilizan el clasificador de playbooks.
_ADMIN_SIGNAL = (
    "cuanto debo",
    "cuánto debo",
    "la factura",
    "mi saldo",
    "el saldo",
    "me cobraron",
)
_TECH_SIGNAL = (
    "sigo sin internet",
    "no tengo internet",
    "sin internet",
    "no me anda el wifi",
    "no tengo wifi",
)
_OBSOLETE_ONT = (
    "cambio la ont",
    "cambió la ont",
    "cambio la ont",
    "reemplazaron la ont",
    "reemplazo la ont",
    "vino un tecnico",
    "vino un técnico",
    "ya vino un tecnico",
    "ya vino un técnico",
)


def new_conversation_state(*, turn: int = 0) -> ConversationState:
    """Estado vacío: sin slots. No hidratar desde legacy."""
    cs = ConversationState(v=1, turn=turn, domains=[], facts=[], domain_stack=[])
    enforce_invariants(cs)
    return cs


def facts_for(cs: ConversationState, domain_id: str) -> list[Fact]:
    return [f for f in cs.facts if f.domain_id == domain_id]


def active_facts_map(cs: ConversationState, domain_id: str) -> dict[str, Any]:
    return {
        f.key: f.value
        for f in cs.facts
        if f.domain_id == domain_id and f.status == "active"
    }


def _copy_pending_bot(pending: PendingBot | None) -> PendingBot | None:
    if pending is None:
        return None
    return PendingBot.from_dict(pending.to_dict())


def _copy_pending_user(pending: PendingUser | None) -> PendingUser | None:
    if pending is None:
        return None
    return PendingUser.from_dict(pending.to_dict())


def _copy_last(act: LastBotAct | None) -> LastBotAct | None:
    if act is None:
        return None
    return LastBotAct.from_dict(act.to_dict())


def _stash_discourse(cs: ConversationState, slot: DomainSlot) -> None:
    """Guarda el discurso global en el slot si pertenece a ese dominio."""
    pb = cs.pending_bot
    if pb and (not pb.domain_id or pb.domain_id == slot.id):
        slot.pending_bot = _copy_pending_bot(pb)
    pu = cs.pending_user
    if pu and (not pu.domain_id or pu.domain_id == slot.id):
        slot.pending_user = _copy_pending_user(pu)
    last = cs.last_bot_act
    if last and (not last.domain_id or last.domain_id == slot.id):
        slot.last_bot_act = _copy_last(last)


def _project_slot_discourse(cs: ConversationState, slot: DomainSlot) -> None:
    cs.pending_bot = _copy_pending_bot(slot.pending_bot)
    cs.pending_user = _copy_pending_user(slot.pending_user)
    cs.last_bot_act = _copy_last(slot.last_bot_act)


def _clear_global_discourse(cs: ConversationState) -> None:
    cs.pending_bot = None
    cs.pending_user = None
    cs.last_bot_act = None


def pending_is_valid(cs: ConversationState, slot: DomainSlot) -> bool:
    pb = slot.pending_bot
    if pb is None:
        return False
    if pb.status == "invalidated":
        return False
    if pb.step_id and pb.step_id in slot.covered_steps:
        return False
    facts = active_facts_map(cs, slot.id)
    if pb.step_id in ("reinicio_ont", "reinicio_router_wifi") and (
        facts.get("ont_reemplazada") or facts.get("ont_cambiada")
    ):
        return False
    return True


def _next_pending_for_slot(cs: ConversationState, slot: DomainSlot) -> PendingBot | None:
    """Pending del primer paso realmente descubierto. Nunca None si hay playbook."""
    from app.domain.conversation_motor import classify_step_act
    from app.domain.flujos_abonado import PLAYBOOKS, primer_paso_pendiente

    pasos = PLAYBOOKS.get(slot.playbook) or []
    if not pasos:
        return PendingBot(
            act="ASK_FACT",
            step_id=slot.playbook or None,
            referent=slot.playbook or None,
            domain_id=slot.id,
            turn=cs.turn,
            status="open",
        )
    idx = primer_paso_pendiente(pasos, slot.covered_steps)
    if idx >= len(pasos):
        idx = max(len(pasos) - 1, 0)
    paso = pasos[idx]
    sid = str(getattr(paso, "id", "") or "") or None
    pregunta = str(getattr(paso, "pregunta", "") or "")
    return PendingBot(
        act=classify_step_act(sid or "", pregunta),
        step_id=sid,
        referent=sid,
        domain_id=slot.id,
        turn=cs.turn,
        status="open",
    )


def _reconcile_pending(cs: ConversationState, slot: DomainSlot) -> None:
    if pending_is_valid(cs, slot):
        return
    slot.pending_bot = _next_pending_for_slot(cs, slot)


# --- operaciones ---------------------------------------------------------


def create_domain(
    cs: ConversationState,
    *,
    kind: str,
    playbook: str = "",
    activate: bool = True,
) -> DomainSlot:
    """Crea un slot de `kind`. Un slot por kind. No borra paused de otros kinds."""
    if kind not in KINDS:
        raise DomainKindError(f"kind no permitido: {kind}")
    existing = cs.slot_by_kind(kind)
    if existing is not None:
        if existing.status == "closed":
            raise DomainClosedError(
                f"{existing.id} está closed; no reabrir por create (usar reopen explícito)"
            )
        raise DomainExistsError(f"ya existe slot {existing.id} kind={kind}")
    if len(cs.domains) >= MAX_DOMAINS:
        raise DomainCapacityError(f"máximo {MAX_DOMAINS} dominios")
    slot = DomainSlot(
        id=SLOT_ID[kind],
        kind=kind,
        playbook=playbook or _PLAYBOOK_DEFAULT[kind],
        status="paused",
        covered_steps=[],
        cursor=0,
        opened_turn=cs.turn,
    )
    cs.domains.append(slot)
    if activate:
        current = cs.active_slot()
        if current is not None and current.id != slot.id:
            pause_domain(cs, current.id)
        slot.status = "active"
        cs.active_domain_id = slot.id
        push_domain_stack(cs, slot.id)
        _project_slot_discourse(cs, slot)
    else:
        push_domain_stack(cs, slot.id)
    enforce_invariants(cs)
    return slot


def pause_domain(cs: ConversationState, domain_id: str | None = None) -> DomainSlot:
    """active → paused. Conserva facts, covered, cursor, pending, last_bot_act, playbook."""
    slot = cs.slot(domain_id or cs.active_domain_id)
    if slot is None:
        raise DomainNotFoundError("no hay dominio para pausar")
    if slot.status == "closed":
        raise DomainClosedError(f"{slot.id} está closed")
    if slot.status == "active":
        _stash_discourse(cs, slot)
        if cs.active_domain_id == slot.id:
            _clear_global_discourse(cs)
            cs.active_domain_id = None
    slot.status = "paused"
    enforce_invariants(cs)
    return slot


def activate_domain(cs: ConversationState, domain_id: str) -> DomainSlot:
    """Pone un slot paused como unique active. Closed no se activa."""
    slot = cs.slot(domain_id)
    if slot is None:
        raise DomainNotFoundError(domain_id)
    if slot.status == "closed":
        raise DomainClosedError(f"{slot.id} closed no se activa")
    current = cs.active_slot()
    if current is not None and current.id != slot.id:
        pause_domain(cs, current.id)
    slot.status = "active"
    cs.active_domain_id = slot.id
    push_domain_stack(cs, slot.id)
    _reconcile_pending(cs, slot)
    _project_slot_discourse(cs, slot)
    enforce_invariants(cs)
    return slot


def resume_domain(cs: ConversationState, domain_id: str) -> DomainSlot:
    """paused → active. No reinicia facts ni covered_steps. Closed → error."""
    slot = cs.slot(domain_id)
    if slot is None:
        raise DomainNotFoundError(domain_id)
    if slot.status == "closed":
        raise DomainClosedError(f"{slot.id} closed: resume no reabre")
    if slot.status == "active":
        _reconcile_pending(cs, slot)
        _project_slot_discourse(cs, slot)
        return slot
    return activate_domain(cs, domain_id)


def close_domain(cs: ConversationState, domain_id: str | None = None) -> DomainSlot:
    """active|paused → closed. No se reanuda por referencia histórica."""
    slot = cs.slot(domain_id or cs.active_domain_id)
    if slot is None:
        raise DomainNotFoundError("no hay dominio para cerrar")
    if slot.status == "active":
        _stash_discourse(cs, slot)
        if cs.active_domain_id == slot.id:
            _clear_global_discourse(cs)
            cs.active_domain_id = None
    slot.status = "closed"
    if slot.pending_bot:
        slot.pending_bot.status = "invalidated"
    enforce_invariants(cs)
    return slot


def refine_playbook(cs: ConversationState, playbook: str, *, domain_id: str | None = None) -> DomainSlot:
    """Cambia el playbook del mismo slot (internet → internet_ftth). No crea slot nuevo."""
    slot = cs.slot(domain_id) if domain_id else cs.active_slot()
    if slot is None:
        raise DomainNotFoundError("no hay dominio para refinar")
    kind = map_playbook_to_kind(playbook)
    if kind != slot.kind:
        raise DomainKindError(
            f"refinar {slot.playbook} → {playbook} cambia de kind ({slot.kind} → {kind})"
        )
    slot.playbook = playbook
    try:
        from app.domain.flujos_abonado import PLAYBOOKS

        ids = {str(getattr(p, "id", "") or "") for p in (PLAYBOOKS.get(playbook) or [])}
        if ids:
            slot.covered_steps = [s for s in slot.covered_steps if s in ids]
    except Exception:
        pass
    if slot.status == "active":
        _reconcile_pending(cs, slot)
        _project_slot_discourse(cs, slot)
    enforce_invariants(cs)
    return slot


def set_slot_pending(
    cs: ConversationState,
    *,
    domain_id: str | None = None,
    pending_bot: PendingBot | None = None,
    pending_user: PendingUser | None = None,
    last_bot_act: LastBotAct | None = None,
) -> DomainSlot:
    slot = cs.slot(domain_id) if domain_id else cs.active_slot()
    if slot is None:
        raise DomainNotFoundError("no hay dominio para pending")
    if pending_bot is not None:
        pending_bot.domain_id = slot.id
        slot.pending_bot = pending_bot
    if pending_user is not None:
        pending_user.domain_id = slot.id
        slot.pending_user = pending_user
    if last_bot_act is not None:
        last_bot_act.domain_id = slot.id
        slot.last_bot_act = last_bot_act
    if slot.status == "active":
        _project_slot_discourse(cs, slot)
    return slot


def invalidate_pending(cs: ConversationState, domain_id: str | None = None) -> DomainSlot:
    slot = cs.slot(domain_id) if domain_id else cs.active_slot()
    if slot is None:
        raise DomainNotFoundError("no hay dominio")
    if slot.pending_bot:
        slot.pending_bot.status = "invalidated"
    if slot.status == "active":
        _reconcile_pending(cs, slot)
        _project_slot_discourse(cs, slot)
    return slot


def invalidate_pending_from_text(cs: ConversationState, texto: str) -> bool:
    """Señales explícitas: ONT cambiada / técnico en sitio. No es clasificador NLP."""
    t = (texto or "").lower()
    if not any(k in t for k in _OBSOLETE_ONT):
        return False
    slot = cs.active_slot() or cs.slot_by_kind(KIND_TECNICO)
    if slot is None:
        return False
    upsert_fact(
        cs,
        Fact(
            key="ont_reemplazada",
            value=True,
            domain_id=slot.id,
            source_turn=cs.turn,
            status="active",
        ),
    )
    invalidate_pending(cs, slot.id)
    return True


def domain_spans_in_order(texto: str) -> list[str]:
    """Kinds mencionados, en orden de aparición. No cambia kind_from_user_signal."""
    t = (texto or "").lower()
    hits: list[tuple[int, str]] = []
    admin_phrases = _ADMIN_SIGNAL + ("factura", "boleta", "deuda")
    tech_phrases = _TECH_SIGNAL + (
        "wifi",
        "wi-fi",
        "wi fi",
        "internet",
        "fibra",
        "router",
        "onu",
    )
    com_phrases = ("contratar", "alta nueva", "pasame con comercial", " comercial")
    for phrase, kind in (
        *[(p, KIND_ADMIN) for p in admin_phrases],
        *[(p, KIND_TECNICO) for p in tech_phrases],
        *[(p, KIND_COMERCIAL) for p in com_phrases],
    ):
        idx = t.find(phrase)
        if idx >= 0:
            hits.append((idx, kind))
    hits.sort(key=lambda row: row[0])
    ordered: list[str] = []
    seen: set[str] = set()
    for _pos, kind in hits:
        if kind not in seen:
            seen.add(kind)
            ordered.append(kind)
    return ordered


def kind_from_user_signal(texto: str) -> str | None:
    """Kind sugerido por el mensaje. Reusa clasificar_intencion; no NLP nuevo."""
    raw = texto or ""
    t = raw.lower()
    if any(k in t for k in _ADMIN_SIGNAL):
        return KIND_ADMIN
    if any(k in t for k in _TECH_SIGNAL):
        return KIND_TECNICO
    try:
        from app.domain.flujos_abonado import clasificar_intencion

        intent = clasificar_intencion(raw)
        if intent:
            kind = map_playbook_to_kind(intent)
            if intent in ("general", ""):
                return None
            return kind
    except Exception:
        return None
    return None


def apply_domain_signal(
    cs: ConversationState,
    texto: str,
    *,
    playbook: str = "",
) -> DomainSlot | None:
    """Pausa el activo y crea/reanuda el kind del mensaje. None si no hay cambio."""
    kind = kind_from_user_signal(texto)
    if kind is None:
        return None
    current = cs.active_slot()
    if current is not None and current.kind == kind:
        return current
    existing = cs.slot_by_kind(kind)
    if existing is not None:
        if existing.status == "closed":
            raise DomainClosedError(f"{existing.id} closed; señal histórica no reabre")
        return resume_domain(cs, existing.id)
    pb = playbook or _PLAYBOOK_DEFAULT[kind]
    if current is not None:
        pause_domain(cs, current.id)
    return create_domain(cs, kind=kind, playbook=pb, activate=True)


def cover_and_note(
    cs: ConversationState,
    *,
    steps: list[str],
    facts: dict[str, Any] | None = None,
) -> DomainSlot:
    """Helper de tests: cubre pasos y hechos en el dominio activo."""
    slot = cs.active_slot()
    if slot is None:
        raise DomainNotFoundError("no hay dominio activo")
    for sid in steps:
        if sid and sid not in slot.covered_steps:
            slot.covered_steps.append(sid)
    for key, value in (facts or {}).items():
        upsert_fact(
            cs,
            Fact(
                key=str(key),
                value=value,
                domain_id=slot.id,
                source_turn=cs.turn,
                status="active",
            ),
        )
    return slot
