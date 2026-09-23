"""Eko 2.5D-1 — Canonical service context READ path.

No production semantics beyond: get_selected_ref reads ONLY selected_service_ref.
"""

from __future__ import annotations

from app.services.eko_journeys import apply_service_ref, get_journey
from app.services.eko_service_selection import (
    ServiceRef,
    get_selected_ref,
    get_selected_service_ref,
)


def _ref(**kw) -> ServiceRef:
    base = dict(
        service_id="inet-1",
        login="INT1",
        service_type="internet",
        client_number="18099",
        label="Internet",
        product="Fibra",
        active=True,
    )
    base.update(kw)
    return ServiceRef(**base)


def test_2_5d1_accessor_returns_canonical_ref():
    ctx: dict = {}
    apply_service_ref(ctx, _ref())
    got = get_selected_ref(ctx)
    assert got is not None
    assert got.service_id == "inet-1"
    assert got.login == "INT1"
    assert get_selected_service_ref(ctx) is got or (
        get_selected_service_ref(ctx)
        and get_selected_service_ref(ctx).service_id == "inet-1"
    )


def test_2_5d1_accessor_none_when_missing():
    assert get_selected_ref({}) is None
    assert get_selected_ref({"eko_journey": {}}) is None


def test_2_5d1_no_fallback_from_selected_service_string():
    """selected_service alone must NOT invent a ServiceRef."""
    ctx = {"eko_journey": {"selected_service": "INT_LEGACY"}}
    assert get_selected_ref(ctx) is None


def test_2_5d1_no_fallback_from_login_seleccionado():
    """login_seleccionado alone must NOT invent a ServiceRef."""
    ctx = {"login_seleccionado": "INT_SHADOW", "eko_journey": {}}
    assert get_selected_ref(ctx) is None


def test_2_5d1_ref_with_login_projection_coherent():
    ctx: dict = {}
    apply_service_ref(ctx, _ref(login="INT777", service_id="s777"))
    ref = get_selected_ref(ctx)
    assert ref and ref.login == "INT777"
    assert ctx.get("login_seleccionado") == "INT777"
    assert get_journey(ctx).get("selected_service") == "INT777"


def test_2_5d1_sensa_no_fabricated_login():
    ctx: dict = {}
    apply_service_ref(
        ctx,
        _ref(
            service_id="tv-1",
            login="",
            service_type="tv",
            label="Sensa",
            product="Sensa",
        ),
    )
    ref = get_selected_ref(ctx)
    assert ref and ref.service_id == "tv-1" and ref.login == ""
    assert not ctx.get("login_seleccionado")
    # Shadow alone must not resurrect selection after canonical cleared
    st = dict(ctx["eko_journey"])
    st.pop("selected_service_ref", None)
    ctx["eko_journey"] = st
    ctx["login_seleccionado"] = "SHOULD_NOT_MATTER"
    assert get_selected_ref(ctx) is None


def test_2_5d1_change_selection_reads_new_canonical():
    ctx: dict = {}
    apply_service_ref(ctx, _ref(service_id="a", login="INTA"))
    apply_service_ref(
        ctx,
        _ref(service_id="b", login="INTB"),
        previous_login="INTA",
    )
    ref = get_selected_ref(ctx)
    assert ref and ref.service_id == "b" and ref.login == "INTB"
