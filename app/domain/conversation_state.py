"""ConversationState v1 — contrato shadow (Fase 6+12).

Estructuras, hidratación, serialización, proyección y operaciones puras.
Gate 12: ``ConversationState.covered_steps`` es canónico; ``ctx.pasos_cubiertos``
es proyección legacy. ``sync_from_legacy`` no reintroduce covers desde ctx.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("operations_hub")

CS_VERSION = 1
CS_KEY = "cs"
MAX_DOMAINS = 3
MAX_STACK = 3
MAX_FACT_HISTORY = 3

KIND_TECNICO = "tecnico"
KIND_ADMIN = "administrativo"
KIND_COMERCIAL = "comercial"
KINDS = (KIND_TECNICO, KIND_ADMIN, KIND_COMERCIAL)

SLOT_ID = {
    KIND_TECNICO: "tec-1",
    KIND_ADMIN: "adm-1",
    KIND_COMERCIAL: "com-1",
}

_ADMIN_PLAYBOOKS = frozenset(
    {
        "facturacion",
        "facturacion_pago",
        "facturacion_descarga",
        "facturacion_informar_pago",
        "facturacion_factura",
        "facturacion_estado_cuenta",
        "facturacion_reclamo",
        "corte_deuda",
        "aviso_deuda",
        "estado_reclamo",
        "reactivacion_pago",
        "portal_tramites",
    }
)
_COMERCIAL_PLAYBOOKS = frozenset(
    {
        "alta_plan",
        "baja_servicio",
        "cambio_titularidad",
        "cambio_domicilio",
    }
)

_FACT_KIND_OWNER = {
    "alcance_wifi": KIND_TECNICO,
    "zona_wifi": KIND_TECNICO,
    "dispositivo_afectado": KIND_TECNICO,
    "dispositivo_sin_ethernet": KIND_TECNICO,
    "luces_ont": KIND_TECNICO,
    "accion_reinicio_ont": KIND_TECNICO,
    "tecnologia_acceso": KIND_TECNICO,
    "saldo": KIND_ADMIN,
    "mes_facturacion": KIND_ADMIN,
    "pago_informado": KIND_ADMIN,
}
_FACT_STATUSES = frozenset({"active", "superseded", "uncertain"})
_SLOT_STATUSES = frozenset({"active", "paused", "closed"})


def map_playbook_to_kind(playbook: str | None) -> str:
    p = (playbook or "").strip()
    if p in _COMERCIAL_PLAYBOOKS:
        return KIND_COMERCIAL
    if p in _ADMIN_PLAYBOOKS or p.startswith("facturacion"):
        return KIND_ADMIN
    return KIND_TECNICO


@dataclass
class DomainSlot:
    id: str
    kind: str
    playbook: str = ""
    status: str = "active"
    covered_steps: list[str] = field(default_factory=list)
    cursor: int = 0
    opened_turn: int = 0
    pending_bot: PendingBot | None = None
    pending_user: PendingUser | None = None
    last_bot_act: LastBotAct | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "playbook": self.playbook,
            "status": self.status,
            "covered_steps": list(self.covered_steps),
            "cursor": int(self.cursor),
            "opened_turn": int(self.opened_turn),
        }
        if self.pending_bot or self.pending_user:
            out["pending"] = {
                "bot": self.pending_bot.to_dict() if self.pending_bot else None,
                "user": self.pending_user.to_dict() if self.pending_user else None,
            }
        if self.last_bot_act:
            out["last_bot_act"] = self.last_bot_act.to_dict()
        return out

    @classmethod
    def from_dict(cls, raw: Any) -> DomainSlot | None:
        if not isinstance(raw, dict):
            return None
        ident = str(raw.get("id") or "").strip()
        kind = str(raw.get("kind") or "").strip()
        if not ident or kind not in KINDS:
            return None
        status = str(raw.get("status") or "active")
        if status not in _SLOT_STATUSES:
            status = "paused"
        steps = [str(x) for x in (raw.get("covered_steps") or []) if str(x).strip()]
        try:
            cursor = int(raw.get("cursor") or 0)
        except (TypeError, ValueError):
            cursor = 0
        try:
            opened = int(raw.get("opened_turn") or 0)
        except (TypeError, ValueError):
            opened = 0
        pending_raw = raw.get("pending") if isinstance(raw.get("pending"), dict) else {}
        return cls(
            id=ident,
            kind=kind,
            playbook=str(raw.get("playbook") or ""),
            status=status,
            covered_steps=steps,
            cursor=max(0, cursor),
            opened_turn=max(0, opened),
            pending_bot=PendingBot.from_dict(pending_raw.get("bot")),
            pending_user=PendingUser.from_dict(pending_raw.get("user")),
            last_bot_act=LastBotAct.from_dict(raw.get("last_bot_act")),
        )


@dataclass
class Fact:
    key: str
    value: Any
    domain_id: str
    source_turn: int = 0
    status: str = "active"
    supersedes_turn: int | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "key": self.key,
            "value": self.value,
            "domain_id": self.domain_id,
            "source_turn": int(self.source_turn),
            "status": self.status,
        }
        if self.supersedes_turn is not None:
            out["supersedes_turn"] = int(self.supersedes_turn)
        return out

    @classmethod
    def from_dict(cls, raw: Any) -> Fact | None:
        if not isinstance(raw, dict):
            return None
        key = str(raw.get("key") or "").strip()
        domain_id = str(raw.get("domain_id") or "").strip()
        if not key or not domain_id:
            return None
        status = str(raw.get("status") or "active")
        if status not in _FACT_STATUSES:
            status = "active"
        try:
            source_turn = int(raw.get("source_turn") or 0)
        except (TypeError, ValueError):
            source_turn = 0
        sup = raw.get("supersedes_turn")
        try:
            supersedes_turn = int(sup) if sup is not None else None
        except (TypeError, ValueError):
            supersedes_turn = None
        return cls(
            key=key,
            value=raw.get("value"),
            domain_id=domain_id,
            source_turn=max(0, source_turn),
            status=status,
            supersedes_turn=supersedes_turn,
        )


_PENDING_STATUSES = frozenset({"open", "answered", "invalidated"})


@dataclass
class PendingBot:
    act: str
    step_id: str | None = None
    referent: str | None = None
    domain_id: str | None = None
    turn: int = 0
    status: str = "open"

    def to_dict(self) -> dict[str, Any]:
        return {
            "act": self.act,
            "step_id": self.step_id,
            "referent": self.referent,
            "domain_id": self.domain_id,
            "turn": int(self.turn),
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> PendingBot | None:
        if not isinstance(raw, dict):
            return None
        act = str(raw.get("act") or "").strip()
        if not act:
            return None
        try:
            turn = int(raw.get("turn") or 0)
        except (TypeError, ValueError):
            turn = 0
        st = str(raw.get("status") or "open")
        if st not in _PENDING_STATUSES:
            st = "open"
        return cls(
            act=act,
            step_id=_opt_str(raw.get("step_id")),
            referent=_opt_str(raw.get("referent")),
            domain_id=_opt_str(raw.get("domain_id")),
            turn=max(0, turn),
            status=st,
        )


@dataclass
class PendingUser:
    act: str
    text: str = ""
    referent: str | None = None
    domain_id: str | None = None
    turn: int = 0
    status: str = "open"

    def to_dict(self) -> dict[str, Any]:
        return {
            "act": self.act,
            "text": self.text,
            "referent": self.referent,
            "domain_id": self.domain_id,
            "turn": int(self.turn),
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> PendingUser | None:
        if not isinstance(raw, dict):
            return None
        act = str(raw.get("act") or "").strip()
        if not act:
            return None
        try:
            turn = int(raw.get("turn") or 0)
        except (TypeError, ValueError):
            turn = 0
        st = str(raw.get("status") or "open")
        if st not in _PENDING_STATUSES:
            st = "open"
        return cls(
            act=act,
            text=str(raw.get("text") or "")[:500],
            referent=_opt_str(raw.get("referent")),
            domain_id=_opt_str(raw.get("domain_id")),
            turn=max(0, turn),
            status=st,
        )


@dataclass
class LastBotAct:
    act: str
    referent: str | None = None
    domain_id: str | None = None
    step_id: str | None = None
    turn: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "act": self.act,
            "referent": self.referent,
            "domain_id": self.domain_id,
            "step_id": self.step_id,
            "turn": int(self.turn),
        }

    @classmethod
    def from_dict(cls, raw: Any) -> LastBotAct | None:
        if not isinstance(raw, dict):
            return None
        act = str(raw.get("act") or "").strip()
        if not act:
            return None
        try:
            turn = int(raw.get("turn") or 0)
        except (TypeError, ValueError):
            turn = 0
        return cls(
            act=act,
            referent=_opt_str(raw.get("referent")),
            domain_id=_opt_str(raw.get("domain_id")),
            step_id=_opt_str(raw.get("step_id")),
            turn=max(0, turn),
        )


@dataclass
class ConversationState:
    v: int = CS_VERSION
    turn: int = 0
    active_domain_id: str | None = None
    domain_stack: list[str] = field(default_factory=list)
    domains: list[DomainSlot] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    pending_bot: PendingBot | None = None
    pending_user: PendingUser | None = None
    last_bot_act: LastBotAct | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "v": int(self.v),
            "turn": int(self.turn),
            "active_domain_id": self.active_domain_id,
            "domain_stack": list(self.domain_stack),
            "domains": [d.to_dict() for d in self.domains],
            "facts": [f.to_dict() for f in self.facts],
            "pending": {
                "bot": self.pending_bot.to_dict() if self.pending_bot else None,
                "user": self.pending_user.to_dict() if self.pending_user else None,
            },
            "last_bot_act": self.last_bot_act.to_dict() if self.last_bot_act else None,
        }

    def slot(self, domain_id: str | None) -> DomainSlot | None:
        if not domain_id:
            return None
        for d in self.domains:
            if d.id == domain_id:
                return d
        return None

    def active_slot(self) -> DomainSlot | None:
        return self.slot(self.active_domain_id)

    def slot_by_kind(self, kind: str) -> DomainSlot | None:
        for d in self.domains:
            if d.kind == kind:
                return d
        return None


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _hechos_planos(ctx: dict) -> dict[str, Any]:
    raw = ctx.get("hechos")
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items() if str(k).strip()}


def _cubiertos(ctx: dict) -> list[str]:
    return [str(x) for x in (ctx.get("pasos_cubiertos") or []) if str(x).strip()]


def _filter_covers_for_kind(
    steps: list[str], kind: str, playbook: str = ""
) -> list[str]:
    """Defense-in-depth: no copiar al slot activo covers de otro kind.

    Pasos desconocidos (no catalogados en PLAYBOOKS) se conservan.
    Pasos que solo existen en playbooks de otro kind se descartan.
    """
    if not steps:
        return []
    try:
        from app.domain.flujos_abonado import PLAYBOOKS
    except Exception:
        return list(steps)
    step_kinds: dict[str, set[str]] = {}
    for pb, pasos in (PLAYBOOKS or {}).items():
        pb_kind = map_playbook_to_kind(pb)
        for p in pasos or []:
            sid = str(getattr(p, "id", "") or "").strip()
            if sid:
                step_kinds.setdefault(sid, set()).add(pb_kind)
    own_ids: set[str] = set()
    if playbook:
        for p in PLAYBOOKS.get(playbook) or []:
            sid = str(getattr(p, "id", "") or "").strip()
            if sid:
                own_ids.add(sid)
    out: list[str] = []
    for s in steps:
        owners = step_kinds.get(s)
        if not owners:
            out.append(s)
        elif kind in owners or s in own_ids:
            out.append(s)
    return out


def _paso_idx(ctx: dict) -> int:
    try:
        return max(0, int(ctx.get("paso_idx") or 0))
    except (TypeError, ValueError):
        return 0


def hydrate_from_legacy(ctx: dict) -> ConversationState:
    """Migración conservadora: un slot (o admin+técnico paused) sin historial."""
    playbook = str(ctx.get("intencion") or "").strip() or "general"
    kind = map_playbook_to_kind(playbook)
    turn = 0
    active = DomainSlot(
        id=SLOT_ID[kind],
        kind=kind,
        playbook=playbook,
        status="active",
        covered_steps=_filter_covers_for_kind(_cubiertos(ctx), kind, playbook),
        cursor=_paso_idx(ctx),
        opened_turn=turn,
    )
    domains = [active]
    pendiente = str(ctx.get("intencion_tecnica_pendiente") or "").strip()
    if pendiente and map_playbook_to_kind(pendiente) == KIND_TECNICO and kind != KIND_TECNICO:
        paused = DomainSlot(
            id=SLOT_ID[KIND_TECNICO],
            kind=KIND_TECNICO,
            playbook=pendiente,
            status="paused",
            covered_steps=[],
            cursor=0,
            opened_turn=turn,
        )
        domains.append(paused)
    facts = [
        Fact(
            key=k,
            value=v,
            domain_id=active.id,
            source_turn=turn,
            status="active",
        )
        for k, v in _hechos_planos(ctx).items()
    ]
    stack = [active.id]
    if len(domains) > 1:
        stack.append(domains[1].id)
    cs = ConversationState(
        v=CS_VERSION,
        turn=turn,
        active_domain_id=active.id,
        domain_stack=stack[:MAX_STACK],
        domains=domains,
        facts=facts,
        pending_bot=None,
        pending_user=None,
        last_bot_act=None,
    )
    enforce_invariants(cs)
    return cs


def conversation_state_from_dict(raw: Any) -> ConversationState | None:
    if not isinstance(raw, dict):
        return None
    try:
        version = int(raw.get("v"))
    except (TypeError, ValueError):
        return None
    if version != CS_VERSION:
        return None
    if "domains" in raw and not isinstance(raw.get("domains"), list):
        return None
    try:
        turn = int(raw.get("turn") or 0)
    except (TypeError, ValueError):
        turn = 0
    domains: list[DomainSlot] = []
    for item in raw.get("domains") or []:
        slot = DomainSlot.from_dict(item)
        if slot:
            domains.append(slot)
    if not domains:
        return None
    facts: list[Fact] = []
    for item in raw.get("facts") or []:
        fact = Fact.from_dict(item)
        if fact:
            facts.append(fact)
    pending_raw = raw.get("pending") if isinstance(raw.get("pending"), dict) else {}
    cs = ConversationState(
        v=CS_VERSION,
        turn=max(0, turn),
        active_domain_id=_opt_str(raw.get("active_domain_id")),
        domain_stack=[str(x) for x in (raw.get("domain_stack") or []) if str(x).strip()],
        domains=domains,
        facts=facts,
        pending_bot=PendingBot.from_dict(pending_raw.get("bot")),
        pending_user=PendingUser.from_dict(pending_raw.get("user")),
        last_bot_act=LastBotAct.from_dict(raw.get("last_bot_act")),
    )
    enforce_invariants(cs)
    if cs.active_domain_id and not cs.active_slot():
        return None
    return cs


def hydrate_conversation_state(ctx: dict | None) -> ConversationState:
    """Si `ctx["cs"]` es v1 válido, usarlo. Si no, hidratar desde legacy."""
    ctx = ctx if isinstance(ctx, dict) else {}
    raw = ctx.get(CS_KEY)
    if raw is not None:
        try:
            version = int(raw.get("v")) if isinstance(raw, dict) else None
        except (TypeError, ValueError, AttributeError):
            version = None
        if version is not None and version != CS_VERSION:
            logger.warning(
                "cs_shadow_unknown_version v=%s; degradando a legacy",
                version,
            )
            return hydrate_from_legacy(ctx)
        parsed = conversation_state_from_dict(raw)
        if parsed is not None:
            return parsed
        logger.warning("cs_shadow_invalid; degradando a legacy")
    return hydrate_from_legacy(ctx)


def upsert_fact(cs: ConversationState, fact: Fact, *, as_correction: bool = False) -> None:
    """Mantiene un solo active por (domain_id, key) y recorta historial a 3."""
    if fact.status not in _FACT_STATUSES:
        fact.status = "active"
    current_active: Fact | None = None
    for existing in cs.facts:
        if (
            existing.domain_id == fact.domain_id
            and existing.key == fact.key
            and existing.status == "active"
        ):
            current_active = existing
            break
    if fact.status == "active":
        if current_active is not None:
            if current_active.value == fact.value and not as_correction:
                current_active.source_turn = max(current_active.source_turn, fact.source_turn)
                _trim_fact_history(cs, fact.domain_id, fact.key)
                return
            current_active.status = "superseded"
            if as_correction:
                fact.supersedes_turn = current_active.source_turn
        cs.facts.append(fact)
    else:
        cs.facts.append(fact)
    _trim_fact_history(cs, fact.domain_id, fact.key)


def _trim_fact_history(cs: ConversationState, domain_id: str, key: str) -> None:
    rows = [
        (i, f)
        for i, f in enumerate(cs.facts)
        if f.domain_id == domain_id and f.key == key
    ]
    if len(rows) <= MAX_FACT_HISTORY:
        return
    actives = [(i, f) for i, f in rows if f.status == "active"]
    keep_idx = {i for i, _ in actives[:1]}
    rest = sorted(
        ((i, f) for i, f in rows if i not in keep_idx),
        key=lambda it: it[1].source_turn,
        reverse=True,
    )
    capacity = MAX_FACT_HISTORY - len(keep_idx)
    for i, _f in rest[:capacity]:
        keep_idx.add(i)
    drop = {i for i, _f in rows if i not in keep_idx}
    cs.facts = [f for i, f in enumerate(cs.facts) if i not in drop]


def push_domain_stack(cs: ConversationState, domain_id: str | None) -> None:
    if not domain_id or not cs.slot(domain_id):
        return
    stack = [x for x in cs.domain_stack if x != domain_id]
    stack.insert(0, domain_id)
    cs.domain_stack = stack[:MAX_STACK]


def enforce_invariants(cs: ConversationState) -> None:
    cs.v = CS_VERSION
    cs.turn = max(0, int(cs.turn or 0))
    by_kind: dict[str, DomainSlot] = {}
    for slot in cs.domains:
        if slot.kind not in KINDS:
            continue
        prev = by_kind.get(slot.kind)
        if prev is None or (slot.status == "active" and prev.status != "active"):
            by_kind[slot.kind] = slot
    cs.domains = list(by_kind.values())[:MAX_DOMAINS]
    actives = [d for d in cs.domains if d.status == "active"]
    if len(actives) > 1:
        keep = None
        if cs.active_domain_id:
            keep = cs.slot(cs.active_domain_id)
        if keep is None or keep.status != "active":
            keep = actives[0]
        for d in cs.domains:
            if d.id != keep.id and d.status == "active":
                d.status = "paused"
        cs.active_domain_id = keep.id
    elif len(actives) == 1:
        cs.active_domain_id = actives[0].id
    else:
        # 0 activos: paused/closed es estado válido (Fase 8A pause sin reemplazo).
        cs.active_domain_id = None
    if cs.active_domain_id and not cs.slot(cs.active_domain_id):
        cs.active_domain_id = cs.domains[0].id if cs.domains else None
    ids = {d.id for d in cs.domains}
    stack: list[str] = []
    for item in cs.domain_stack:
        if item in ids and item not in stack:
            stack.append(item)
    if cs.active_domain_id and cs.active_domain_id not in stack:
        stack.insert(0, cs.active_domain_id)
    cs.domain_stack = stack[:MAX_STACK]
    seen_active: set[tuple[str, str]] = set()
    for fact in cs.facts:
        if fact.status != "active":
            continue
        pair = (fact.domain_id, fact.key)
        if pair in seen_active:
            fact.status = "superseded"
        else:
            seen_active.add(pair)
    keys = {(f.domain_id, f.key) for f in cs.facts}
    for domain_id, key in keys:
        _trim_fact_history(cs, domain_id, key)


def _ensure_slot(cs: ConversationState, kind: str, playbook: str, *, opened_turn: int) -> DomainSlot:
    slot = cs.slot_by_kind(kind)
    if slot is None:
        slot = DomainSlot(
            id=SLOT_ID[kind],
            kind=kind,
            playbook=playbook,
            status="paused",
            covered_steps=[],
            cursor=0,
            opened_turn=opened_turn,
        )
        if len(cs.domains) < MAX_DOMAINS:
            cs.domains.append(slot)
        else:
            for i, existing in enumerate(cs.domains):
                if existing.status == "closed":
                    cs.domains[i] = slot
                    break
    return slot


def sync_from_legacy(cs: ConversationState, ctx: dict) -> ConversationState:
    """Sincroniza playbook/facts/kind desde ctx. Gate 12: NO importa covers.

    ``covered_steps`` del slot activo es canónico. Solo ``hydrate_from_legacy``
    (conversación sin ``ctx["cs"]``) puede sembrar covers desde
    ``pasos_cubiertos``. Una sync posterior nunca resucita ni reemplaza covers.
    """
    playbook = str(ctx.get("intencion") or "").strip() or "general"
    kind = map_playbook_to_kind(playbook)
    turn = max(0, int(cs.turn or 0))
    current = cs.active_slot()
    kind_changed = current is None or current.kind != kind
    if current is None or current.kind != kind:
        if current is not None:
            current.status = "paused"
            push_domain_stack(cs, current.id)
        nxt = _ensure_slot(cs, kind, playbook, opened_turn=turn)
        if nxt.status == "closed":
            # Contrato 8A: closed no se reabre por proyección legacy.
            enforce_invariants(cs)
            return cs
        nxt.status = "active"
        nxt.playbook = playbook
        cs.active_domain_id = nxt.id
        push_domain_stack(cs, nxt.id)
        current = nxt
    else:
        current.playbook = playbook
        current.status = "active"
    # Gate 12: cursor legacy es tip; covers NO se tocan desde ctx.
    current.cursor = _paso_idx(ctx)

    pendiente = str(ctx.get("intencion_tecnica_pendiente") or "").strip()
    if pendiente and map_playbook_to_kind(pendiente) == KIND_TECNICO:
        if kind != KIND_TECNICO:
            paused = _ensure_slot(cs, KIND_TECNICO, pendiente, opened_turn=turn)
            if paused.id != cs.active_domain_id:
                paused.status = "paused"
                paused.playbook = pendiente
                push_domain_stack(cs, paused.id)

    active_id = current.id
    hechos = _hechos_planos(ctx)
    existing_active = {
        f.key: f
        for f in cs.facts
        if f.domain_id == active_id and f.status == "active"
    }
    owned_elsewhere = {
        f.key: f.domain_id
        for f in cs.facts
        if f.status == "active" and f.domain_id != active_id
    }
    if hechos:
        for key, value in hechos.items():
            catalog_kind = _FACT_KIND_OWNER.get(key)
            if catalog_kind and catalog_kind != kind:
                continue
            if key in owned_elsewhere:
                continue
            old = existing_active.get(key)
            if old is not None and old.value == value:
                continue
            upsert_fact(
                cs,
                Fact(
                    key=key,
                    value=value,
                    domain_id=active_id,
                    source_turn=turn,
                    status="active",
                ),
                as_correction=old is not None,
            )
        if not kind_changed:
            for key, old in existing_active.items():
                if key not in hechos:
                    old.status = "superseded"
                    _trim_fact_history(cs, active_id, key)

    enforce_invariants(cs)
    return cs


def mark_covers(ctx: dict, *step_ids: str) -> None:
    """Autoridad B: escribe covers en CS canónico y proyecta a ``pasos_cubiertos``.

    Usar en writers determinísticos (plant, wifi_bcm, guardrails, etc.).
    No usar para sugerencias LLM.
    """
    if not isinstance(ctx, dict):
        return
    cs = hydrate_conversation_state(ctx)
    slot = cs.active_slot()
    added: list[str] = []
    for raw in step_ids:
        sid = str(raw or "").strip()
        if not sid:
            continue
        if slot is None:
            added.append(sid)
            continue
        filtered = _filter_covers_for_kind([sid], slot.kind, slot.playbook or "")
        if sid not in filtered:
            continue
        if sid not in slot.covered_steps:
            slot.covered_steps.append(sid)
        added.append(sid)
    if slot is not None:
        ctx["pasos_cubiertos"] = list(slot.covered_steps)
    else:
        cub = _cubiertos(ctx)
        for sid in added:
            if sid not in cub:
                cub.append(sid)
        ctx["pasos_cubiertos"] = cub
    ctx[CS_KEY] = cs.to_dict()


def replace_covers(ctx: dict, step_ids: list[str] | tuple[str, ...] | None) -> None:
    """Reemplaza covers canónicos (p.ej. reset de playbook) y proyecta a legacy."""
    if not isinstance(ctx, dict):
        return
    cs = hydrate_conversation_state(ctx)
    slot = cs.active_slot()
    steps = [str(x).strip() for x in (step_ids or []) if str(x).strip()]
    if slot is not None:
        slot.covered_steps = _filter_covers_for_kind(
            steps, slot.kind, slot.playbook or ""
        )
        ctx["pasos_cubiertos"] = list(slot.covered_steps)
    else:
        ctx["pasos_cubiertos"] = steps
    ctx[CS_KEY] = cs.to_dict()


def project_legacy(cs: ConversationState) -> dict[str, Any]:
    """Proyección determinística hacia campos legacy. Observabilidad / migración."""
    active = cs.active_slot()
    playbook = (active.playbook if active else "") or "general"
    covered = list(active.covered_steps) if active else []
    cursor = int(active.cursor) if active else 0
    hechos = {
        f.key: f.value
        for f in cs.facts
        if f.status == "active" and active and f.domain_id == active.id
    }
    tech_paused = None
    for slot in cs.domains:
        if slot.kind == KIND_TECNICO and slot.status == "paused":
            tech_paused = slot.playbook
            break
    derived = cursor
    try:
        from app.domain.flujos_abonado import PLAYBOOKS, primer_paso_pendiente

        pasos = PLAYBOOKS.get(playbook) or []
        if pasos:
            derived = primer_paso_pendiente(pasos, covered)
    except Exception:
        derived = cursor
    return {
        "intencion": playbook,
        "hechos": hechos,
        "pasos_cubiertos": covered,
        "paso_idx": cursor,
        "paso_idx_derived": derived,
        "intencion_tecnica_pendiente": tech_paused or "",
    }


def increment_user_turn(ctx: dict) -> None:
    """Una llamada = un turno de usuario. No usar en CSAT / duplicados / sistema."""
    cs = hydrate_conversation_state(ctx)
    cs.turn = max(0, cs.turn) + 1
    ctx[CS_KEY] = cs.to_dict()


def write_shadow_into_ctx(
    ctx: dict,
    *,
    conversacion_id: str = "",
) -> None:
    """Dual-write: serializa cs. Gate 12: proyecta covers canónicos → legacy."""
    if not isinstance(ctx, dict):
        return
    snapshot = {
        "intencion": ctx.get("intencion"),
        "hechos": dict(ctx["hechos"]) if isinstance(ctx.get("hechos"), dict) else ctx.get("hechos"),
        "pasos_cubiertos": list(ctx["pasos_cubiertos"])
        if isinstance(ctx.get("pasos_cubiertos"), list)
        else ctx.get("pasos_cubiertos"),
        "paso_idx": ctx.get("paso_idx"),
        "intencion_tecnica_pendiente": ctx.get("intencion_tecnica_pendiente"),
        "identificado": ctx.get("identificado"),
        "dni": ctx.get("dni"),
    }
    projected_back: set[str] = set()
    try:
        prev_active = None
        raw_cs = ctx.get(CS_KEY)
        if isinstance(raw_cs, dict):
            prev_active = raw_cs.get("active_domain_id")
        cs = hydrate_conversation_state(ctx)
        sync_from_legacy(cs, ctx)
        slot = cs.active_slot()
        # Gate 12: CS.covered_steps → ctx.pasos_cubiertos (también si vacío).
        if slot is not None:
            ctx["pasos_cubiertos"] = list(slot.covered_steps)
            projected_back.add("pasos_cubiertos")
            resumed = bool(
                prev_active
                and slot.id != prev_active
                and slot.covered_steps
                and not snapshot.get("pasos_cubiertos")
            )
            if resumed:
                ctx["paso_idx"] = int(slot.cursor or 0)
                projected_back.add("paso_idx")
        ctx[CS_KEY] = cs.to_dict()
        _log_mismatch_if_any(cs, ctx, conversacion_id=conversacion_id)
    except Exception:
        logger.exception("cs_shadow_write_failed conv=%s", (conversacion_id or "")[:12])
    for key, value in snapshot.items():
        if key in projected_back:
            continue
        if ctx.get(key) != value:
            ctx[key] = value


def _log_mismatch_if_any(
    cs: ConversationState,
    ctx: dict,
    *,
    conversacion_id: str,
) -> None:
    proj = project_legacy(cs)
    checks = (
        ("intencion", str(ctx.get("intencion") or "general"), str(proj.get("intencion") or "")),
        (
            "pasos_cubiertos",
            list(ctx.get("pasos_cubiertos") or []),
            list(proj.get("pasos_cubiertos") or []),
        ),
        ("paso_idx", int(ctx.get("paso_idx") or 0), int(proj.get("paso_idx") or 0)),
        (
            "hechos",
            _hechos_planos(ctx),
            dict(proj.get("hechos") or {}),
        ),
    )
    conv = (conversacion_id or "")[:12] or "-"
    for field_name, legacy, projected in checks:
        if legacy != projected:
            logger.warning(
                "cs_shadow_mismatch conv=%s turn=%s field=%s legacy=%s cs=%s",
                conv,
                cs.turn,
                field_name,
                _safe_preview(legacy),
                _safe_preview(projected),
            )


def _safe_preview(value: Any) -> str:
    text = str(value)
    if len(text) > 160:
        text = text[:157] + "..."
    return text
