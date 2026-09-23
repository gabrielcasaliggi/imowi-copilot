"""Eko 2.5D-4 — Handoff + playbook continuity (transport ≠ authority).

Handoff may stamp a continuity **reference**. Restoration always re-validates
against TrustedContext / catalog. Transcript is never a restore source.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.eko_service_selection import (
    ServiceRef,
    get_selected_ref,
    is_fixed_internet_diagnosticable,
    ownership_matches_ref,
)

HANDOFF_KEY = "eko_handoff"
HANDOFF_CONTINUITY_VERSION = 1


@dataclass(frozen=True)
class HandoffReturnResult:
    status: str  # noop | restored | needs_input | rejected
    reason_code: str = ""
    service_kept: bool = False
    confirmation_cleared: bool = False


def playbook_selected_service(ctx: dict[str, Any] | None) -> ServiceRef | None:
    """Canonical READ for playbooks — never ``selected_service`` / ``login_seleccionado`` as SoT."""
    return get_selected_ref(ctx)


def should_ask_service_selection(
    ctx: dict[str, Any] | None,
    *,
    client_number: str = "",
    require_diagnosticable: bool = False,
) -> bool:
    """True when a playbook must ask for service (K01 gate).

    Valid ``selected_service_ref`` → do not re-ask.
    Foreign / missing ownership → ask (or fail upstream).
    """
    ref = get_selected_ref(ctx)
    if ref is None:
        # LEGACY_READ_REMAINS: incomplete dual-write may only have shadow login
        shadow = str((ctx or {}).get("login_seleccionado") or "").strip()
        return not bool(shadow)
    cn = str(client_number or "").strip()
    if cn and not ownership_matches_ref(ref, cn):
        return True
    if require_diagnosticable and not is_fixed_internet_diagnosticable(ref):
        return True
    return False


def _identity_from_ref(ref: ServiceRef | None) -> dict[str, str] | None:
    if ref is None:
        return None
    return {
        "service_id": str(ref.service_id or ""),
        "login": str(ref.login or ""),
        "service_type": str(ref.service_type or ""),
        "client_number": str(ref.client_number or ""),
    }


def get_handoff_meta(ctx: dict[str, Any] | None) -> dict[str, Any]:
    raw = (ctx or {}).get(HANDOFF_KEY)
    return dict(raw) if isinstance(raw, dict) else {}


def handoff_is_active(ctx: dict[str, Any] | None) -> bool:
    return bool(get_handoff_meta(ctx).get("active"))


def invalidate_stale_confirmation_if_handoff(ctx: dict[str, Any]) -> bool:
    """Early return hook: clear confirmation while handoff is still marked active."""
    if not handoff_is_active(ctx):
        return False
    return _clear_pending_confirmation(ctx)


def _clear_pending_confirmation(ctx: dict[str, Any]) -> bool:
    """Invalidate journey + action confirmation (stale across handoff)."""
    cleared = False
    try:
        from app.services.eko_journeys import _clear_stale_confirmation, get_journey

        before = bool(get_journey(ctx).get("pending_confirmation"))
        _clear_stale_confirmation(ctx)
        cleared = before or cleared
    except Exception:
        pass
    try:
        from app.services.eko_action_runtime import get_action_state, set_action_state

        st = get_action_state(ctx)
        if st.get("status") == "confirmation_pending" or st.get("confirmation_pending"):
            set_action_state(
                ctx,
                action=str(st.get("action") or ""),
                status="cleared_on_handoff",
                confirmation="CLEARED",
            )
            cleared = True
    except Exception:
        pass
    return cleared


def stamp_handoff_out(
    ctx: dict[str, Any],
    *,
    reason: str = "escalate_human",
) -> dict[str, Any]:
    """Handoff OUT: stamp continuity reference + invalidate pending confirmation.

    Does **not**:
    - write client_number / ownership
    - create domains
    - create ServiceRef
    - execute Runtime
    - store transcript
    """
    _clear_pending_confirmation(ctx)
    ref = get_selected_ref(ctx)
    stack: list[str] = []
    active_domain_id = ""
    try:
        from app.domain.conversation_state import hydrate_conversation_state

        cs = hydrate_conversation_state(ctx)
        stack = list(cs.domain_stack or [])
        active_domain_id = str(cs.active_domain_id or "")
    except Exception:
        pass

    meta = {
        "v": HANDOFF_CONTINUITY_VERSION,
        "active": True,
        "reason": str(reason or "escalate_human")[:80],
        "domain_stack": stack[:3],
        "active_domain_id": active_domain_id,
        "selected_service_identity": _identity_from_ref(ref),
        # Explicit non-authority markers
        "is_authority": False,
        "transcript": None,
    }
    ctx[HANDOFF_KEY] = meta
    return meta


def _clear_invalid_selection(ctx: dict[str, Any]) -> None:
    """Drop canonical selection when ownership/catalog validation fails."""
    try:
        from app.services.eko_journeys import set_journey

        set_journey(
            ctx,
            selected_service_ref=None,
            selected_service="",
            next_required_input="login",
            asked_selection=False,
            step="service_selection",
        )
    except Exception:
        j = ctx.get("eko_journey")
        if isinstance(j, dict):
            j.pop("selected_service_ref", None)
            j["selected_service"] = ""
    ctx.pop("login_seleccionado", None)


def validate_selected_ref_for_return(
    ctx: dict[str, Any],
    *,
    client_number: str,
    catalog: list[dict[str, Any]] | None = None,
) -> tuple[bool, str]:
    """Validate current selected_service_ref (and optional handoff identity).

    Returns (ok, reason_code).
    """
    cn = str(client_number or "").strip()
    ref = get_selected_ref(ctx)
    meta = get_handoff_meta(ctx)
    identity = meta.get("selected_service_identity")
    if isinstance(identity, dict):
        id_cn = str(identity.get("client_number") or "").strip()
        if id_cn and cn and id_cn != cn:
            return False, "handoff_identity_foreign_cn"
        id_sid = str(identity.get("service_id") or "").strip()
        if catalog is not None and id_sid:
            ids = {str(r.get("id") or "").strip() for r in catalog if isinstance(r, dict)}
            if id_sid not in ids:
                return False, "handoff_identity_not_in_catalog"

    if ref is None:
        return True, "no_selection"
    if cn and not ownership_matches_ref(ref, cn):
        return False, "selection_ownership_mismatch"
    if catalog is not None and ref.service_id:
        ids = {str(r.get("id") or "").strip() for r in catalog if isinstance(r, dict)}
        if ref.service_id not in ids:
            return False, "selection_not_in_catalog"
    return True, "ok"


def prepare_return_from_handoff(
    ctx: dict[str, Any],
    *,
    client_number: str = "",
    catalog: list[dict[str, Any]] | None = None,
) -> HandoffReturnResult:
    """First bot turn after handoff: validate continuity, never trust metadata as authority.

    REAL INTEGRATION: caller must invoke when ``conv.estado`` is already ``bot``
    and ``eko_handoff.active`` (set on OUT). Return signal = release/estado→bot
    (existing inbox/portal), not inferred from transcript.
    """
    if not handoff_is_active(ctx):
        return HandoffReturnResult(status="noop", reason_code="handoff_inactive")

    cleared = _clear_pending_confirmation(ctx)
    cn = str(client_number or "").strip()
    ok, reason = validate_selected_ref_for_return(
        ctx, client_number=cn, catalog=catalog
    )
    kept = False
    status = "restored"
    if not ok:
        _clear_invalid_selection(ctx)
        status = "needs_input" if reason.endswith("catalog") or "mismatch" in reason else "rejected"
        kept = False
    else:
        kept = get_selected_ref(ctx) is not None

    # Domain stack: ConversationState remains SoT — do not invent "handoff" domain
    # and do not overwrite cs from metadata (metadata is audit/reference only).
    meta = get_handoff_meta(ctx)
    meta["active"] = False
    meta["returned"] = True
    meta["return_reason"] = reason
    meta["is_authority"] = False
    ctx[HANDOFF_KEY] = meta

    return HandoffReturnResult(
        status=status,
        reason_code=reason,
        service_kept=kept,
        confirmation_cleared=cleared,
    )


def reject_llm_handoff_write(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Strip handoff / stack keys from untrusted payloads (defense in depth)."""
    out: dict[str, Any] = {}
    blocked = {
        HANDOFF_KEY,
        "domain_stack",
        "selected_service_ref",
        "client_number",
        "login_seleccionado",
    }
    for k, v in (raw or {}).items():
        if str(k) in blocked or str(k).lower() in blocked:
            continue
        out[k] = v
    return out
