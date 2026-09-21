"""Allowlist de acciones Agentic Ops (Fase 4B).

Reexporta el registry del Action Runtime. La ejecución vive en
``eko_action_runtime.execute_action`` — nunca ``getattr`` sobre nombres LLM.
"""

from __future__ import annotations

from app.services.eko_action_runtime import (
    ActionRequest,
    ActionResult,
    ActionSpec,
    TrustedContext,
    bootstrap_registry,
    evaluate_policy,
    execute_action,
    get_action,
    is_registered,
    list_registered_actions,
    parse_llm_action_proposal,
    register_action,
    sanitize_parameters,
)

__all__ = [
    "ActionRequest",
    "ActionResult",
    "ActionSpec",
    "TrustedContext",
    "bootstrap_registry",
    "evaluate_policy",
    "execute_action",
    "get_action",
    "is_registered",
    "list_registered_actions",
    "parse_llm_action_proposal",
    "register_action",
    "sanitize_parameters",
]
