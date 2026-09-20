"""Fase 8B — adapter productivo de lifecycle (no cambia el contrato 8A).

Convierte la señal del turno en create/pause/resume/refine y proyecta legacy
desde el dominio activo. No decide el texto de la respuesta.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.domain.conversation_state import (
    KIND_ADMIN,
    KIND_COMERCIAL,
    KIND_TECNICO,
    ConversationState,
    DomainSlot,
    hydrate_conversation_state,
    map_playbook_to_kind,
)
from app.domain.domain_lifecycle import (
    DomainClosedError,
    DomainExistsError,
    DomainKindError,
    apply_domain_signal,
    create_domain,
    domain_spans_in_order,
    kind_from_user_signal,
    pause_domain,
    refine_playbook,
    resume_domain,
)

logger = logging.getLogger("operations_hub")

_SKIP_PLAYBOOKS = frozenset({"", "general", "multi_tema"})

_SPECIALIZE = {
    "internet": frozenset(
        {
            "internet_ftth",
            "internet_radio",
            "internet_adsl",
            "internet_lento",
            "internet_intermitente",
            "wifi",
            "cambio_clave_wifi",
        }
    ),
    "movil": frozenset({"movil_datos", "movil_llamadas"}),
    "facturacion": frozenset(
        {
            "facturacion_pago",
            "facturacion_descarga",
            "facturacion_informar_pago",
            "facturacion_factura",
            "facturacion_estado_cuenta",
            "facturacion_reclamo",
        }
    ),
}


def _is_refine(current: str, nxt: str) -> bool:
    """Solo especializar. Nunca generalizar wifi→internet ni ftth→internet."""
    if not current or not nxt or current == nxt:
        return False
    if current == "general":
        return nxt not in _SKIP_PLAYBOOKS
    if nxt in _SPECIALIZE.get(current, frozenset()):
        return True
    if current == "facturacion" and nxt.startswith("facturacion"):
        return True
    return False


@dataclass
class DomainTransitionResult:
    cs: ConversationState
    previous_active_id: str | None
    active_domain_id: str | None
    created: bool = False
    paused: bool = False
    resumed: bool = False
    refined: bool = False
    blocked_closed: bool = False
    reason: str = ""
    playbook: str = ""
    secondary_kind: str | None = None

    @property
    def changed(self) -> bool:
        return bool(
            self.created or self.paused or self.resumed or self.refined
        )


def _playbook_from_text(texto: str) -> str:
    try:
        from app.domain.flujos_abonado import clasificar_intencion

        intent = clasificar_intencion(texto) or ""
        if intent in _SKIP_PLAYBOOKS:
            return ""
        return intent
    except Exception:
        return ""


def _playbook_for_kind(texto: str, kind: str, hint: str = "") -> str:
    if hint and map_playbook_to_kind(hint) == kind and hint not in _SKIP_PLAYBOOKS:
        return hint
    pb = _playbook_from_text(texto)
    if pb and map_playbook_to_kind(pb) == kind:
        return pb
    t = (texto or "").lower()
    if kind == KIND_TECNICO:
        if "wifi" in t or "wi-fi" in t:
            return "wifi"
        return "internet"
    if kind == KIND_ADMIN:
        return "facturacion"
    if kind == KIND_COMERCIAL:
        return "alta_plan"
    return pb


def _ensure_kind_paused(cs: ConversationState, kind: str, texto: str) -> bool:
    """Crea el slot del kind en paused si no existe. Closed no se reabre."""
    existing = cs.slot_by_kind(kind)
    if existing is not None:
        return False
    create_domain(
        cs,
        kind=kind,
        playbook=_playbook_for_kind(texto, kind),
        activate=False,
    )
    return True


def _kind_from_cambio_tema(cs: ConversationState, texto: str) -> tuple[str | None, str]:
    current = cs.active_slot()
    actual = (current.playbook if current else "") or ""
    try:
        from app.domain.flujos_abonado import es_cambio_tema_claro

        nueva = es_cambio_tema_claro(texto, actual)
    except Exception:
        nueva = None
    if not nueva or nueva in _SKIP_PLAYBOOKS:
        return None, ""
    return map_playbook_to_kind(nueva), nueva


def _log_transition(
    trans: DomainTransitionResult,
    *,
    from_status: str,
    to_status: str,
    kind: str,
    turn: int,
) -> None:
    if trans.created:
        event = "domain_created"
    elif trans.resumed:
        event = "domain_resumed"
    elif trans.refined:
        event = "domain_refined"
    elif trans.paused:
        event = "domain_paused"
    elif trans.blocked_closed:
        event = "domain_closed"
    else:
        event = "domain_transition"
    logger.info(
        "%s domain_id=%s kind=%s playbook=%s from_status=%s to_status=%s turn=%s reason=%s "
        "created=%s paused=%s resumed=%s refined=%s",
        event,
        trans.active_domain_id or "-",
        kind or "-",
        trans.playbook or "-",
        from_status or "-",
        to_status or "-",
        turn,
        trans.reason or "-",
        int(trans.created),
        int(trans.paused),
        int(trans.resumed),
        int(trans.refined),
    )


def _tramite_comercial_desde_texto(texto: str) -> str | None:
    """Baja/titularidad/domicilio mandan sobre spans técnicos («internet» en la frase)."""
    try:
        from app.domain.flujos_abonado import (
            solicita_baja_servicio,
            solicita_cambio_domicilio,
            solicita_cambio_titularidad,
        )
    except Exception:
        return None
    if solicita_baja_servicio(texto):
        return "baja_servicio"
    if solicita_cambio_titularidad(texto):
        return "cambio_titularidad"
    if solicita_cambio_domicilio(texto):
        return "cambio_domicilio"
    return None


def _respuesta_en_tramite_comercial(previous: DomainSlot | None, texto: str) -> bool:
    """Producto/modalidad cortos dentro de baja/titularidad: no saltar a técnico."""
    if previous is None or previous.kind != KIND_COMERCIAL:
        return False
    pb = (previous.playbook or "").strip()
    if pb not in ("baja_servicio", "cambio_titularidad", "cambio_domicilio"):
        return False
    try:
        from app.domain.flujos_abonado import (
            parse_alcance_baja,
            parse_modalidad_titularidad,
        )
    except Exception:
        return False
    if pb == "baja_servicio" and parse_alcance_baja(texto):
        return True
    if pb == "cambio_titularidad" and parse_modalidad_titularidad(texto):
        return True
    t = (texto or "").strip().lower()
    if pb == "baja_servicio" and t in {
        "sensa",
        "tv",
        "tele",
        "internet",
        "fibra",
        "móvil",
        "movil",
        "total",
        "todo",
        "todos",
    }:
        return True
    return False


def apply_turn_domain(
    cs: ConversationState,
    texto: str,
    *,
    playbook_hint: str = "",
) -> DomainTransitionResult:
    """Aplica la señal de dominio del turno. No devuelve texto."""
    previous = cs.active_slot()
    prev_id = previous.id if previous else None
    prev_status = previous.status if previous else ""
    hint = (playbook_hint or "").strip()
    if hint in _SKIP_PLAYBOOKS:
        hint = ""

    spans = domain_spans_in_order(texto)
    secondary_kind = spans[1] if len(spans) > 1 else None
    tramite_pb = _tramite_comercial_desde_texto(texto)
    if tramite_pb:
        kind = KIND_COMERCIAL
        playbook = hint if hint and map_playbook_to_kind(hint) == KIND_COMERCIAL else tramite_pb
        # «internet»/«sensa» en la baja no abren técnico secundario.
        secondary_kind = None
    elif _respuesta_en_tramite_comercial(previous, texto):
        return DomainTransitionResult(
            cs=cs,
            previous_active_id=prev_id,
            active_domain_id=cs.active_domain_id,
            playbook=(previous.playbook if previous else "") or "",
            reason="noop",
            secondary_kind=None,
        )
    else:
        kind = spans[0] if spans else kind_from_user_signal(texto)
        playbook = hint or (
            _playbook_for_kind(texto, kind, hint) if kind else _playbook_from_text(texto)
        )
    if kind is None:
        kind_tema, pb_tema = _kind_from_cambio_tema(cs, texto)
        if kind_tema:
            kind = kind_tema
            playbook = playbook or pb_tema
    if kind is None and playbook:
        kind = map_playbook_to_kind(playbook)
    if kind and (not playbook or map_playbook_to_kind(playbook) != kind):
        playbook = _playbook_for_kind(texto, kind, hint)

    noop = DomainTransitionResult(
        cs=cs,
        previous_active_id=prev_id,
        active_domain_id=cs.active_domain_id,
        playbook=(previous.playbook if previous else "") or playbook,
        reason="noop",
        secondary_kind=secondary_kind,
    )
    if kind is None:
        return noop

    def _attach_secondary(trans: DomainTransitionResult) -> DomainTransitionResult:
        if not secondary_kind or secondary_kind == kind:
            return trans
        created_sec = _ensure_kind_paused(cs, secondary_kind, texto)
        trans.cs = cs
        trans.secondary_kind = secondary_kind
        if created_sec and trans.reason in ("noop", "signal", ""):
            trans.reason = "dual_ensure_secondary"
        return trans

    if previous is not None and previous.kind == kind:
        if (
            playbook
            and playbook != previous.playbook
            and map_playbook_to_kind(playbook) == previous.kind
            and _is_refine(previous.playbook, playbook)
        ):
            try:
                slot = refine_playbook(cs, playbook)
            except DomainKindError:
                return _attach_secondary(noop)
            trans = DomainTransitionResult(
                cs=cs,
                previous_active_id=prev_id,
                active_domain_id=slot.id,
                refined=True,
                reason="refine",
                playbook=slot.playbook,
                secondary_kind=secondary_kind,
            )
            _log_transition(
                trans,
                from_status=prev_status,
                to_status=slot.status,
                kind=slot.kind,
                turn=cs.turn,
            )
            return _attach_secondary(trans)
        return _attach_secondary(noop)

    existing = cs.slot_by_kind(kind)
    paused_prev = False
    created = False
    resumed = False
    refined = False
    reason = "signal"
    try:
        if existing is not None:
            if existing.status == "closed":
                trans = DomainTransitionResult(
                    cs=cs,
                    previous_active_id=prev_id,
                    active_domain_id=cs.active_domain_id,
                    blocked_closed=True,
                    reason="closed",
                    playbook=existing.playbook,
                )
                _log_transition(
                    trans,
                    from_status="closed",
                    to_status="closed",
                    kind=existing.kind,
                    turn=cs.turn,
                )
                return trans
            if previous is not None and previous.id != existing.id:
                pause_domain(cs, previous.id)
                paused_prev = True
            resume_domain(cs, existing.id)
            resumed = True
            reason = "resume"
            if playbook and _is_refine(existing.playbook, playbook):
                refine_playbook(cs, playbook)
                refined = True
                reason = "resume_refine"
        else:
            slot_via_signal = None
            if kind_from_user_signal(texto) == kind:
                slot_via_signal = apply_domain_signal(cs, texto, playbook=playbook)
            if slot_via_signal is None:
                if previous is not None:
                    pause_domain(cs, previous.id)
                    paused_prev = True
                create_domain(cs, kind=kind, playbook=playbook, activate=True)
            else:
                paused_prev = previous is not None and previous.id != slot_via_signal.id
            created = True
            paused_prev = paused_prev or (previous is not None)
            reason = "create"
    except DomainClosedError:
        trans = DomainTransitionResult(
            cs=cs,
            previous_active_id=prev_id,
            active_domain_id=cs.active_domain_id,
            blocked_closed=True,
            reason="closed",
            playbook=playbook,
        )
        _log_transition(
            trans,
            from_status="closed",
            to_status="closed",
            kind=kind,
            turn=cs.turn,
        )
        return trans
    except DomainExistsError:
        existing = cs.slot_by_kind(kind)
        if existing is None or existing.status == "closed":
            return DomainTransitionResult(
                cs=cs,
                previous_active_id=prev_id,
                active_domain_id=cs.active_domain_id,
                blocked_closed=existing is not None,
                reason="exists",
                playbook=playbook,
            )
        if previous is not None and previous.id != existing.id:
            pause_domain(cs, previous.id)
            paused_prev = True
        resume_domain(cs, existing.id)
        resumed = True
        reason = "reuse"

    slot = cs.active_slot()
    trans = DomainTransitionResult(
        cs=cs,
        previous_active_id=prev_id,
        active_domain_id=cs.active_domain_id,
        created=created,
        paused=paused_prev,
        resumed=resumed,
        refined=refined,
        reason=reason,
        playbook=(slot.playbook if slot else playbook),
        secondary_kind=secondary_kind,
    )
    _log_transition(
        trans,
        from_status=prev_status,
        to_status=(slot.status if slot else ""),
        kind=(slot.kind if slot else kind),
        turn=cs.turn,
    )
    return _attach_secondary(trans)


def project_domain_into_ctx(ctx: dict, cs: ConversationState) -> None:
    """cs → ctx. intencion/hechos/cubiertos son proyección del activo."""
    from app.domain.conversation_motor import apply_cs_to_legacy

    apply_cs_to_legacy(ctx, cs)


def apply_lifecycle_to_ctx(
    ctx: dict,
    texto: str,
    *,
    playbook_hint: str = "",
) -> DomainTransitionResult:
    """Punto único para canal: hidrata, transiciona y proyecta."""
    cs = hydrate_conversation_state(ctx)
    trans = apply_turn_domain(cs, texto, playbook_hint=playbook_hint)
    if trans.changed:
        project_domain_into_ctx(ctx, trans.cs)
    else:
        ctx["cs"] = trans.cs.to_dict()
    return trans
