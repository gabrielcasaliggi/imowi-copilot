"""Eko 2.6Q — Effective ACTION_RUNTIME_* observability (startup snapshot)."""

from __future__ import annotations

import logging

import app.services.eko_action_bridge as bridge


def test_26q_case_a_enabled_isolated_create(monkeypatch, caplog):
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ACTIONS", frozenset({"create_ticket"}))
    snap = bridge.effective_action_runtime_config()
    assert snap["enabled"] is True
    assert snap["actions"] == ["create_ticket"]
    # Same source Runtime uses
    assert bridge.action_runtime_covers("create_ticket") is True
    assert bridge.action_runtime_covers("show_ticket") is False
    with caplog.at_level(logging.INFO, logger="operations_hub"):
        logged = bridge.log_effective_action_runtime_config()
    assert logged == snap
    assert any(
        "action_runtime.enabled=true" in r.message
        and "action_runtime.actions=create_ticket" in r.message
        for r in caplog.records
    )


def test_26q_case_b_enabled_false(monkeypatch, caplog):
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", False)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ACTIONS", frozenset({"create_ticket"}))
    snap = bridge.effective_action_runtime_config()
    assert snap["enabled"] is False
    assert bridge.action_runtime_master_enabled() is False
    assert bridge.action_runtime_covers("create_ticket") is False
    with caplog.at_level(logging.INFO, logger="operations_hub"):
        bridge.log_effective_action_runtime_config()
    assert any("action_runtime.enabled=false" in r.message for r in caplog.records)


def test_26q_case_c_multi_actions(monkeypatch):
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(
        bridge,
        "ACTION_RUNTIME_ACTIONS",
        frozenset({"create_ticket", "show_ticket"}),
    )
    snap = bridge.effective_action_runtime_config()
    assert snap["enabled"] is True
    assert snap["actions"] == ["create_ticket", "show_ticket"]
    assert bridge.action_runtime_covers("create_ticket") is True
    assert bridge.action_runtime_covers("show_ticket") is True
    assert bridge.action_runtime_covers("ticket_customer_note") is False


def test_26q_snapshot_matches_covers_source(monkeypatch):
    """El snapshot no es una segunda fuente: lee los mismos globals que covers()."""
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(
        bridge, "ACTION_RUNTIME_ACTIONS", frozenset({"show_balance", "create_ticket"})
    )
    snap = bridge.effective_action_runtime_config()
    for name in snap["actions"]:
        assert bridge.action_runtime_covers(name) is True
    assert set(snap["actions"]) == set(bridge.ACTION_RUNTIME_ACTIONS)
    assert snap["enabled"] is bridge.action_runtime_master_enabled()
