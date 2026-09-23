"""Eko 2.5D-2 — Reference resolution (el fijo / la fija / el otro).

Does not change "ese" semantics. No probes / EFFECTS from resolve alone.
"""

from __future__ import annotations

from app.services.eko_journeys import apply_service_ref, get_journey
from app.services.eko_service_selection import (
    ServiceRef,
    get_selected_ref,
    looks_like_selection_utterance,
    resolve_fijo_reference,
    resolve_otro_reference,
    resolve_service_reference,
    resolve_service_selection,
)


def _row(
    *,
    sid: str,
    tip: str,
    product: str = "",
    label: str = "",
    login: str = "",
) -> dict:
    return {
        "id": sid,
        "type": tip,
        "product": product or tip,
        "label": label or product or tip,
        "login": login,
        "active": True,
        "line_msisdn": None,
    }


def test_2_5d2_el_fijo_unique_telefonia():
    cat = [_row(sid="t1", tip="telefonia", product="Línea fija", label="Teléfono fijo")]
    r = resolve_service_selection(texto="el fijo", catalog=cat, client_number="18099")
    assert r.status == "selected"
    assert r.ref and r.ref.service_id == "t1" and r.ref.service_type == "telefonia"


def test_2_5d2_la_fija_unique_telefonia():
    cat = [_row(sid="t1", tip="telefonia", product="Línea fija")]
    r = resolve_service_selection(texto="la fija", catalog=cat, client_number="18099")
    assert r.status == "selected"
    assert r.ref and r.ref.service_id == "t1"


def test_2_5d2_fijo_unique_internet_only():
    cat = [_row(sid="i1", tip="internet", login="INT1", product="Fibra 100")]
    r = resolve_service_selection(texto="el fijo", catalog=cat, client_number="18099")
    assert r.status == "selected"
    assert r.ref and r.ref.service_id == "i1" and r.ref.service_type == "internet"


def test_2_5d2_el_fijo_phone_and_internet_needs_input():
    cat = [
        _row(sid="i1", tip="internet", login="INT1", product="Internet fijo"),
        _row(sid="t1", tip="telefonia", product="Línea fija", label="Teléfono fijo"),
    ]
    r = resolve_service_selection(texto="el fijo", catalog=cat, client_number="18099")
    assert r.status == "needs_input"
    assert r.reason_code == "fijo_ambiguous"
    assert len(r.options or []) == 2


def test_2_5d2_fijo_no_compatible_needs_input():
    cat = [_row(sid="v1", tip="tv", product="Sensa")]
    r = resolve_service_selection(texto="el fijo", catalog=cat, client_number="18099")
    assert r.status == "needs_input"
    assert r.reason_code == "fijo_no_compatible"


def test_2_5d2_fijo_variants_normalized():
    cat = [_row(sid="t1", tip="telefonia", product="Fija")]
    for txt in ("Fijo", "FIJA", "  el fijo? ", "Ahora hablame del fijo"):
        r = resolve_service_selection(texto=txt, catalog=cat, client_number="18099")
        assert r.status == "selected", txt
        assert r.ref and r.ref.service_id == "t1"


def test_2_5d2_el_otro_unique_alternate():
    cat = [
        _row(sid="i1", tip="internet", login="INT1", product="Fibra"),
        _row(sid="t1", tip="telefonia", product="Fija"),
    ]
    cur = ServiceRef(
        service_id="i1",
        login="INT1",
        service_type="internet",
        client_number="18099",
    )
    r = resolve_service_selection(
        texto="el otro", catalog=cat, client_number="18099", current_ref=cur
    )
    assert r.status == "selected"
    assert r.ref and r.ref.service_id == "t1"


def test_2_5d2_el_otro_three_services_needs_input():
    cat = [
        _row(sid="i1", tip="internet", login="INT1", product="Fibra"),
        _row(sid="t1", tip="telefonia", product="Fija"),
        _row(sid="v1", tip="tv", product="Sensa"),
    ]
    cur = ServiceRef(
        service_id="i1", login="INT1", service_type="internet", client_number="18099"
    )
    r = resolve_service_selection(
        texto="el otro", catalog=cat, client_number="18099", current_ref=cur
    )
    assert r.status == "needs_input"
    assert r.reason_code == "otro_ambiguous"
    assert len(r.options or []) == 2


def test_2_5d2_el_otro_without_current_needs_input():
    cat = [
        _row(sid="i1", tip="internet", login="INT1", product="Fibra"),
        _row(sid="t1", tip="telefonia", product="Fija"),
    ]
    r = resolve_service_selection(texto="el otro", catalog=cat, client_number="18099")
    assert r.status == "needs_input"
    assert r.reason_code == "otro_missing_current"


def test_2_5d2_el_otro_single_service_needs_input():
    cat = [_row(sid="i1", tip="internet", login="INT1", product="Fibra")]
    cur = ServiceRef(
        service_id="i1", login="INT1", service_type="internet", client_number="18099"
    )
    r = resolve_service_selection(
        texto="el otro", catalog=cat, client_number="18099", current_ref=cur
    )
    assert r.status == "needs_input"
    assert r.reason_code == "otro_no_alternate"


def test_2_5d2_el_otro_current_not_in_catalog():
    cat = [
        _row(sid="i1", tip="internet", login="INT1", product="Fibra"),
        _row(sid="t1", tip="telefonia", product="Fija"),
    ]
    cur = ServiceRef(
        service_id="GONE", login="INTX", service_type="internet", client_number="18099"
    )
    r = resolve_service_selection(
        texto="el otro", catalog=cat, client_number="18099", current_ref=cur
    )
    assert r.status == "needs_input"
    assert r.reason_code == "otro_current_not_in_catalog"


def test_2_5d2_el_otro_never_picks_foreign_id():
    cat = [_row(sid="i1", tip="internet", login="INT1", product="Fibra")]
    cur = ServiceRef(
        service_id="i1", login="INT1", service_type="internet", client_number="18099"
    )
    r = resolve_service_selection(
        texto="el otro",
        catalog=cat,
        client_number="18099",
        current_ref=cur,
        proposed_service_id="FOREIGN",
    )
    assert r.status == "denied"


def test_2_5d2_missing_client_number():
    cat = [_row(sid="t1", tip="telefonia", product="Fija")]
    r = resolve_service_selection(texto="el fijo", catalog=cat, client_number="")
    assert r.status == "needs_input"
    assert r.reason_code == "missing_client_number"


def test_2_5d2_llm_foreign_service_id_denied():
    cat = [_row(sid="t1", tip="telefonia", product="Fija")]
    r = resolve_service_selection(
        texto="el fijo",
        catalog=cat,
        client_number="18099",
        proposed_service_id="EVIL",
    )
    assert r.status == "denied"


def test_2_5d2_ese_multi_unchanged():
    """Regression: ese with multi stays needs_input."""
    cat = [
        _row(sid="i1", tip="internet", login="INT1", product="Fibra"),
        _row(sid="t1", tip="telefonia", product="Fija"),
    ]
    r = resolve_service_selection(texto="ese", catalog=cat, client_number="18099")
    assert r.status == "needs_input"


def test_2_5d2_ese_single_unchanged():
    cat = [_row(sid="i1", tip="internet", login="INT1", product="Fibra")]
    r = resolve_service_selection(texto="ese", catalog=cat, client_number="18099")
    assert r.status == "selected"
    assert r.ref and r.ref.service_id == "i1"


def test_2_5d2_apply_service_ref_invalidates_diagnostic():
    ctx: dict = {"pppoe_informado": True}
    apply_service_ref(
        ctx,
        ServiceRef(
            service_id="i1",
            login="INT1",
            service_type="internet",
            client_number="18099",
        ),
    )
    from app.services.eko_journeys import set_journey

    set_journey(ctx, diagnostic_started=True, last_diagnostic_result="up")
    cat = [
        _row(sid="i1", tip="internet", login="INT1", product="Fibra"),
        _row(sid="t1", tip="telefonia", product="Fija"),
    ]
    r = resolve_service_selection(
        texto="el otro",
        catalog=cat,
        client_number="18099",
        current_ref=get_selected_ref(ctx),
    )
    assert r.status == "selected" and r.ref
    apply_service_ref(ctx, r.ref, previous_login="INT1")
    assert get_journey(ctx).get("diagnostic_started") is False
    assert not ctx.get("pppoe_informado")


def test_2_5d2_sensa_selection_no_login():
    cat = [
        _row(sid="i1", tip="internet", login="INT1", product="Fibra"),
        _row(sid="v1", tip="tv", product="Sensa", label="Sensa"),
    ]
    cur = ServiceRef(
        service_id="i1", login="INT1", service_type="internet", client_number="18099"
    )
    r = resolve_service_selection(
        texto="el otro", catalog=cat, client_number="18099", current_ref=cur
    )
    assert r.status == "selected"
    assert r.ref and r.ref.service_id == "v1" and r.ref.login == ""


def test_2_5d2_looks_like_includes_fijo_otro_not_otra_vez():
    assert looks_like_selection_utterance("el fijo")
    assert looks_like_selection_utterance("el otro")
    assert not looks_like_selection_utterance("otra vez lo mismo")


def test_2_5d2_resolve_service_reference_alias():
    cat = [_row(sid="t1", tip="telefonia", product="Fija")]
    r = resolve_service_reference(texto="fija", catalog=cat, client_number="18099")
    assert r.status == "selected"


def test_2_5d2_helpers_direct():
    cat = [
        _row(sid="i1", tip="internet", login="INT1", product="Fibra"),
        _row(sid="t1", tip="telefonia", product="Fija"),
    ]
    assert resolve_fijo_reference(
        texto="el fijo", catalog=cat, client_number="1"
    ).status == "needs_input"
    cur = ServiceRef(
        service_id="i1", login="INT1", service_type="internet", client_number="1"
    )
    assert (
        resolve_otro_reference(
            texto="el otro", catalog=cat, client_number="1", current_ref=cur
        ).ref
        and resolve_otro_reference(
            texto="el otro", catalog=cat, client_number="1", current_ref=cur
        ).ref.service_id
        == "t1"
    )


def test_2_5d2_no_fallback_login_shadow_for_otro():
    """current_ref must be canonical; login_seleccionado alone is not enough."""
    cat = [
        _row(sid="i1", tip="internet", login="INT1", product="Fibra"),
        _row(sid="t1", tip="telefonia", product="Fija"),
    ]
    r = resolve_service_selection(
        texto="el otro",
        catalog=cat,
        client_number="18099",
        current_ref=None,
    )
    assert r.reason_code == "otro_missing_current"
