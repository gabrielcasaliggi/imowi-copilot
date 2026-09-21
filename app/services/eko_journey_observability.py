"""Observabilidad de Journeys (Fase 7) — reutiliza logging + contadores in-process.

Sin telemetría paralela, sin PII, sin secrets. Patrón alineado a ov_handoff / llm_metrics.
Eventos: journey.started|step|waiting_input|waiting_confirmation|action|switched|
         completed|abandoned|failed (+ señales de seguridad).
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("operations_hub")

# Contadores globales (proceso)
_LOCK = threading.Lock()
_COUNTERS: dict[str, int] = {
    "journey_started_total": 0,
    "journey_completed_total": 0,
    "journey_abandoned_total": 0,
    "journey_failed_total": 0,
    "journey_switched_total": 0,
    "journey_needs_input_total": 0,
    "journey_needs_confirmation_total": 0,
    "journey_action_success_total": 0,
    "journey_action_failed_total": 0,
    "journey_action_denied_total": 0,
    "journey_action_unavailable_total": 0,
    "journey_runtime_total": 0,
    "journey_legacy_total": 0,
    "journey_diagnostic_total": 0,
    "journey_unexpected_probe_total": 0,
    "unauthorized_action_total": 0,
    "ownership_denied_total": 0,
    "stale_confirmation_rejected_total": 0,
    "double_execution_detected_total": 0,
    "unexpected_probe_total": 0,
}

_BY_JOURNEY: dict[str, dict[str, int]] = {}

_JOURNEY_KEYS = (
    "started",
    "completed",
    "abandoned",
    "failed",
    "switched",
)

# Eventos recientes (sin PII) para reconstrucción en tests / ops
_RECENT: list[dict[str, Any]] = []
_RECENT_MAX = 200

_PII_FORBIDDEN = (
    "dni",
    "password",
    "jwt",
    "token",
    "secret",
    "authorization",
    "abonado_id",
    "confirmation_token",
)


def reset_journey_metrics() -> None:
    with _LOCK:
        for k in _COUNTERS:
            _COUNTERS[k] = 0
        _BY_JOURNEY.clear()
        _RECENT.clear()


def snapshot_journey_metrics() -> dict[str, Any]:
    with _LOCK:
        return {
            "counters": dict(_COUNTERS),
            "by_journey": {j: dict(v) for j, v in _BY_JOURNEY.items()},
            "recent_n": len(_RECENT),
            "recent": list(_RECENT[-50:]),
        }


def _inc(name: str, n: int = 1) -> None:
    with _LOCK:
        _COUNTERS[name] = int(_COUNTERS.get(name) or 0) + n


def _inc_journey(journey: str, key: str, n: int = 1) -> None:
    j = (journey or "").strip() or "unknown"
    with _LOCK:
        bucket = _BY_JOURNEY.setdefault(j, {k: 0 for k in _JOURNEY_KEYS})
        if key not in bucket:
            bucket[key] = 0
        bucket[key] = int(bucket[key]) + n


def _sanitize_fields(fields: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in fields.items():
        key = str(k)
        if key.lower() in _PII_FORBIDDEN:
            continue
        if key.lower().endswith("_id") and key not in (
            "correlation_id",
            "conversation_id",
        ):
            # Evitar abonado_id / ticket_id / etc. salvo correlation
            if key not in ("correlation_id",):
                continue
        if isinstance(v, str) and len(v) > 120:
            v = v[:120]
        out[key] = v
    return out


def emit_journey_event(
    event: str,
    *,
    journey: str = "",
    domain: str = "",
    step: str = "",
    action: str = "",
    status: str = "",
    execution_path: str = "",
    correlation_id: str = "",
    channel: str = "",
    previous_journey: str = "",
    next_journey: str = "",
    failure_reason: str = "",
    **extra: Any,
) -> None:
    """Emite evento operacional + actualiza contadores. Sin PII."""
    payload = _sanitize_fields(
        {
            "event": event,
            "journey": journey,
            "domain": domain,
            "step": step,
            "action": action,
            "status": status,
            "execution_path": execution_path,
            "correlation_id": correlation_id,
            "channel": (channel or "")[:24],
            "previous_journey": previous_journey,
            "next_journey": next_journey,
            "failure_reason": (failure_reason or "")[:80],
            "timestamp": datetime.now(UTC).isoformat(),
            **extra,
        }
    )
    with _LOCK:
        _RECENT.append(payload)
        if len(_RECENT) > _RECENT_MAX:
            del _RECENT[: len(_RECENT) - _RECENT_MAX]

    logger.info("eko_journey %s", payload)

    # Contadores
    if event == "journey.started":
        _inc("journey_started_total")
        _inc_journey(journey, "started")
    elif event == "journey.completed":
        _inc("journey_completed_total")
        _inc_journey(journey, "completed")
    elif event == "journey.abandoned":
        _inc("journey_abandoned_total")
        _inc_journey(journey, "abandoned")
    elif event == "journey.failed":
        _inc("journey_failed_total")
        _inc_journey(journey, "failed")
    elif event == "journey.switched":
        _inc("journey_switched_total")
        _inc_journey(journey or next_journey, "switched")
    elif event == "journey.waiting_input":
        _inc("journey_needs_input_total")
    elif event == "journey.waiting_confirmation":
        _inc("journey_needs_confirmation_total")
    elif event == "journey.action":
        st = (status or "").strip()
        if st == "success" or st == "already_done":
            _inc("journey_action_success_total")
        elif st == "failed":
            _inc("journey_action_failed_total")
        elif st == "denied":
            _inc("journey_action_denied_total")
        elif st == "unavailable":
            _inc("journey_action_unavailable_total")
        path = (execution_path or "").strip().lower()
        if path == "runtime":
            _inc("journey_runtime_total")
        elif path == "legacy" or path.startswith("legacy"):
            _inc("journey_legacy_total")
        if (action or "") == "run_diagnostic_pppoe":
            _inc("journey_diagnostic_total")


def record_security_signal(kind: str, **fields: Any) -> None:
    """Señales de seguridad / stop-conditions (sin PII)."""
    key_map = {
        "unauthorized": "unauthorized_action_total",
        "ownership_denied": "ownership_denied_total",
        "stale_confirmation": "stale_confirmation_rejected_total",
        "double_execution": "double_execution_detected_total",
        "unexpected_probe": "unexpected_probe_total",
    }
    counter = key_map.get(kind)
    if counter:
        _inc(counter)
        if kind == "unexpected_probe":
            _inc("journey_unexpected_probe_total")
    emit_journey_event(
        f"journey.security.{kind}",
        failure_reason=kind,
        **fields,
    )


def observe_journey_turn(
    turn: Any,
    *,
    canal: str = "",
    started: bool = False,
    switched: bool = False,
    previous_journey: str = "",
    completed: bool = False,
    abandoned: bool = False,
) -> None:
    """Deriva eventos mínimos desde un JourneyTurn (sin contenido de mensaje)."""
    if turn is None or not getattr(turn, "handled", False):
        return
    journey = str(getattr(turn, "journey", "") or "")
    domain = str(getattr(turn, "domain", "") or "")
    step = str(getattr(turn, "step", "") or "")
    action = str(getattr(turn, "action", "") or "")
    status = str(getattr(turn, "action_status", "") or "")
    corr = str(getattr(turn, "correlation_id", "") or "")
    data = getattr(turn, "data", None) or {}
    path = str(data.get("execution_path") or "")

    if switched or data.get("reentry"):
        emit_journey_event(
            "journey.switched",
            journey=journey,
            domain=domain,
            step=step,
            correlation_id=corr,
            channel=canal,
            previous_journey=previous_journey,
            next_journey=journey,
        )
    if started:
        emit_journey_event(
            "journey.started",
            journey=journey,
            domain=domain,
            step=step,
            correlation_id=corr,
            channel=canal,
        )

    emit_journey_event(
        "journey.step",
        journey=journey,
        domain=domain,
        step=step,
        action=action,
        status=status,
        execution_path=path,
        correlation_id=corr,
        channel=canal,
    )

    if step in ("service_selection", "identity") or status == "needs_input":
        emit_journey_event(
            "journey.waiting_input",
            journey=journey,
            domain=domain,
            step=step,
            correlation_id=corr,
            channel=canal,
        )
    if step == "confirm_action" or status == "needs_confirmation":
        emit_journey_event(
            "journey.waiting_confirmation",
            journey=journey,
            domain=domain,
            step=step,
            correlation_id=corr,
            channel=canal,
        )
    elif data.get("decision") == "offer_escalate" or data.get("observation") == "pppoe_session_down":
        emit_journey_event(
            "journey.waiting_confirmation",
            journey=journey,
            domain=domain,
            step=step,
            correlation_id=corr,
            channel=canal,
        )
    if action:
        emit_journey_event(
            "journey.action",
            journey=journey,
            domain=domain,
            step=step,
            action=action,
            status=status,
            execution_path=path,
            correlation_id=corr,
            channel=canal,
        )
    if status in ("failed", "denied") and action:
        emit_journey_event(
            "journey.failed",
            journey=journey,
            domain=domain,
            step=step,
            action=action,
            status=status,
            execution_path=path,
            correlation_id=corr,
            channel=canal,
            failure_reason=str(getattr(turn, "reason_code", "") or status),
        )
    if completed or step == "done":
        emit_journey_event(
            "journey.completed",
            journey=journey,
            domain=domain,
            step=step,
            correlation_id=corr,
            channel=canal,
        )
    if abandoned:
        emit_journey_event(
            "journey.abandoned",
            journey=journey,
            domain=domain,
            step=step,
            correlation_id=corr,
            channel=canal,
        )
    if data.get("idempotent_skip"):
        record_security_signal(
            "double_execution",
            journey=journey,
            step=step,
            action=action or "run_diagnostic_pppoe",
            correlation_id=corr,
            channel=canal,
            status="already_done",
        )
