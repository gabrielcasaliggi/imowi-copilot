"""Eko 2.2B — service selection (service_id ↔ login)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.config as app_config
import app.services.eko_action_bridge as bridge
from app.services.eko_action_runtime import (
    ActionRequest,
    ActionResult,
    TrustedContext,
    bootstrap_registry,
    execute_action,
    parse_llm_action_proposal,
    sanitize_parameters,
)
from app.services.eko_journeys import (
    apply_service_ref,
    detect_journey_name,
    get_journey,
    maybe_handle_journey_turn,
    set_journey,
)
from app.services.eko_service_selection import (
    ServiceRef,
    get_selected_ref,
    option_from_row,
    resolve_service_selection,
)


def _abo(**kwargs):
    d = {
        "id": "abo-1",
        "organizacion_id": "org-1",
        "nombre": "Ana",
        "dni": "30111222",
        "client_number": "18099",
        "deuda_monto": "0",
    }
    d.update(kwargs)
    return SimpleNamespace(**d)


def _conv(**kwargs):
    d = {
        "id": "conv-1",
        "ticket_id": "",
        "estado": "bot",
        "telefono": "2235551234",
        "canal": "whatsapp",
        "abonado_id": "abo-1",
    }
    d.update(kwargs)
    return SimpleNamespace(**d)


def _enable(monkeypatch, *actions: str):
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ENABLED", True)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(
        bridge,
        "ACTION_RUNTIME_ACTIONS",
        frozenset(actions or ("service_list", "show_balance", "show_invoice", "open_OV")),
    )
    bootstrap_registry()


def _row(
    *,
    sid: str,
    tip: str = "internet",
    product: str = "Internet 600M",
    login: str = "",
    active: bool = True,
) -> dict:
    return {
        "id": sid,
        "type": tip,
        "label": product,
        "product": product,
        "active": active,
        "login": login,
        "line_msisdn": login if tip == "movil" and len("".join(c for c in login if c.isdigit())) == 10 else None,
    }


def _cat(*rows: dict) -> dict:
    return {
        "status": "ok",
        "checked_at": "2026-09-22T12:00:00+00:00",
        "services": list(rows),
        "reason_code": None,
    }


def test_t01_single_service(monkeypatch):
    _enable(monkeypatch)
    row = _row(sid="s1", login="INT600", product="Internet 600M")
    with patch(
        "app.services.portal_services.catalog_for_selection",
        return_value=_cat(row),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "ese servicio",
            canal="wa",
            ctx={},
        )
    assert t and t.action == "service_selection"
    assert t.action_status == "success"
    ref = t.data.get("selected_service_ref") or {}
    assert ref.get("service_id") == "s1"
    assert ref.get("login") == "INT600"


def test_t02_multiple_needs_input(monkeypatch):
    _enable(monkeypatch)
    rows = [
        _row(sid="a", login="INTA", product="Internet 600M"),
        _row(sid="b", login="INTB", product="Internet 300M"),
    ]
    with patch(
        "app.services.portal_services.catalog_for_selection",
        return_value=_cat(*rows),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "quiero el internet",
            canal="wa",
            ctx={},
        )
    assert t and t.action_status == "needs_input"
    assert t.action == "service_selection"
    assert len(t.data.get("selection_options") or []) >= 2


def test_t03_explicit_service_id():
    rows = [
        _row(sid="own-1", login="INT1"),
        _row(sid="own-2", login="INT2"),
    ]
    r = resolve_service_selection(
        texto="service_id: own-1",
        catalog=rows,
        client_number="18099",
    )
    assert r.status == "selected"
    assert r.ref and r.ref.service_id == "own-1"
    assert r.ref.login == "INT1"


def test_t04_foreign_service_id():
    rows = [_row(sid="own-1", login="INT1")]
    r = resolve_service_selection(
        texto="service_id: foreign-99",
        catalog=rows,
        client_number="18099",
    )
    assert r.status == "denied"
    assert r.reason_code == "foreign_or_unknown_service_id"


def test_t05_explicit_login():
    rows = [
        _row(sid="s1", login="INTAAA"),
        _row(sid="s2", login="INTBBB"),
    ]
    r = resolve_service_selection(
        texto="INTBBB",
        catalog=rows,
        client_number="18099",
    )
    assert r.status == "selected"
    assert r.ref and r.ref.service_id == "s2"
    assert r.ref.login == "INTBBB"


def test_t06_foreign_login():
    rows = [_row(sid="s1", login="INTAAA")]
    r = resolve_service_selection(
        texto="INTZZZ",
        catalog=rows,
        client_number="18099",
    )
    assert r.status == "denied"


def test_t07_numeric_option():
    rows = [
        _row(sid="a", login="INTA", product="Internet 600M"),
        _row(sid="b", login="INTB", product="Internet 300M"),
        _row(sid="c", tip="tv", product="Sensa", login=""),
    ]
    opts = [
        {"service_id": "a", "login": "INTA", "label": "Internet 600M"},
        {"service_id": "b", "login": "INTB", "label": "Internet 300M"},
        {"service_id": "c", "login": "", "label": "Sensa"},
    ]
    r = resolve_service_selection(
        texto="2",
        catalog=rows,
        client_number="18099",
        pending_options=opts,
    )
    assert r.status == "selected"
    assert r.ref and r.ref.service_id == "b"


def test_t08_ambiguous_natural():
    rows = [
        _row(sid="a", login="INTA", product="Internet 600M"),
        _row(sid="b", login="INTB", product="Internet 300M"),
    ]
    r = resolve_service_selection(
        texto="el internet",
        catalog=rows,
        client_number="18099",
    )
    assert r.status == "needs_input"
    assert r.reason_code == "ambiguous_reference"


def test_t09_unique_natural():
    rows = [
        _row(sid="a", login="INTA", product="Internet 600M"),
        _row(sid="b", tip="tv", product="Sensa", login=""),
    ]
    r = resolve_service_selection(
        texto="el Sensa",
        catalog=rows,
        client_number="18099",
    )
    assert r.status == "selected"
    assert r.ref and r.ref.service_id == "b"


def test_t10_empty_client_number(monkeypatch):
    _enable(monkeypatch)
    with (
        patch("app.services.portal_services.catalog_for_selection") as cat,
        patch("app.services.eko_journeys.dispatch_runtime") as disp,
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(client_number=""),
            "el primero",
            canal="wa",
            ctx={},
        )
    assert t and t.action_status == "needs_input"
    assert t.reason_code == "missing_client_number"
    cat.assert_not_called()
    disp.assert_not_called()


def test_t11_client_number_immutable():
    cleaned = sanitize_parameters({"client_number": "EVIL", "service_id": "x"})
    assert "client_number" not in cleaned


def test_t12_selection_change_invalidates(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {
        "pppoe_informado": True,
        "eko_journey": {
            "name": "service_catalog",
            "selected_service": "INTA",
            "selected_service_ref": {
                "service_id": "a",
                "login": "INTA",
                "service_type": "internet",
                "client_number": "18099",
            },
            "last_diagnostic_result": "operational",
            "diagnostic_started": True,
        },
        "login_seleccionado": "INTA",
    }
    rows = [
        _row(sid="a", login="INTA", product="Internet 600M"),
        _row(sid="b", login="INTB", product="Internet 300M"),
    ]
    with patch(
        "app.services.portal_services.catalog_for_selection",
        return_value=_cat(*rows),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "INTB",
            canal="wa",
            ctx=ctx,
        )
    assert t and t.action_status == "success"
    ref = get_selected_ref(ctx)
    assert ref and ref.login == "INTB" and ref.service_id == "b"
    assert not ctx.get("pppoe_informado")
    assert get_journey(ctx).get("last_diagnostic_result") in ("", None)
    assert get_journey(ctx).get("diagnostic_started") is False


def test_t13_selected_service_login_consistency():
    ctx: dict = {}
    ref = ServiceRef(
        service_id="s9",
        login="INT9",
        service_type="internet",
        client_number="18099",
        product="Internet",
    )
    apply_service_ref(ctx, ref)
    got = get_selected_ref(ctx)
    assert got is not None
    assert got.service_id == "s9"
    assert got.login == "INT9"
    assert ctx.get("login_seleccionado") == "INT9"
    assert get_journey(ctx).get("selected_service") == "INT9"
    assert get_journey(ctx).get("selected_service_ref", {}).get("service_id") == "s9"


def test_t14_no_automatic_diagnostic(monkeypatch):
    _enable(monkeypatch)
    row = _row(sid="s1", login="INT1")
    with (
        patch(
            "app.services.portal_services.catalog_for_selection",
            return_value=_cat(row),
        ),
        patch("app.services.eko_journeys._advance_connectivity") as diag,
        patch("app.services.eko_journeys.dispatch_runtime") as disp,
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "INT1",
            canal="wa",
            ctx={},
        )
    assert t and t.action == "service_selection"
    diag.assert_not_called()
    # no diagnostic actions
    assert all(
        (c.args[0] if c.args else "") not in (
            "run_diagnostic_pppoe",
            "run_diagnostic_bcm",
            "run_diagnostic_uisp",
        )
        for c in disp.call_args_list
    )


def test_t15_no_commercial_effect(monkeypatch):
    _enable(monkeypatch)
    row = _row(sid="s1", login="INT1")
    with (
        patch(
            "app.services.portal_services.catalog_for_selection",
            return_value=_cat(row),
        ),
        patch("app.services.eko_journeys.dispatch_runtime") as disp,
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "ese",
            canal="wa",
            ctx={},
        )
    assert t and t.action_status == "success"
    assert all(
        (c.args[0] if c.args else "")
        not in ("create_ticket", "open_OV", "show_invoice", "show_balance")
        for c in disp.call_args_list
    )


def test_t16_commercial_vs_technical():
    ref = ServiceRef(
        service_id="s1",
        login="INT1",
        service_type="internet",
        client_number="18099",
        active=True,
    )
    d = ref.to_dict()
    assert d.get("active") is True
    assert "operational" not in d
    assert "technical_status" not in d


def test_t17_llm_invented_service_id():
    rows = [_row(sid="real", login="INT1")]
    r = resolve_service_selection(
        texto="",
        catalog=rows,
        client_number="18099",
        proposed_service_id="hallucinated-id",
    )
    assert r.status == "denied"


def test_t18_llm_ownership():
    cleaned = sanitize_parameters({"client_number": "OTHER", "abonado_id": "x"})
    assert "client_number" not in cleaned
    assert "abonado_id" not in cleaned
    trusted = TrustedContext(abonado=_abo(client_number="18099"), organization_id="org")
    assert str(getattr(trusted.abonado, "client_number", "")) == "18099"


def test_t19_routing_service_list(monkeypatch):
    _enable(monkeypatch)

    def _disp(action, **kwargs):
        assert action == "service_list"
        return ActionResult(
            action="service_list",
            status="success",
            user_message="Estos son tus servicios contratados:\n• Internet 600M — Activo",
            data={"services": [{"id": "1", "type": "internet", "product": "Internet 600M", "active": True, "label": "Internet 600M"}], "count": 1},
        )

    with (
        patch("app.services.eko_journeys.dispatch_runtime", side_effect=_disp),
        patch(
            "app.services.portal_services.catalog_for_selection",
            return_value=_cat(_row(sid="1", login="INT1")),
        ),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "¿Qué servicios tengo?",
            canal="wa",
            ctx={},
        )
    assert t and t.action == "service_list"
    assert t.action_status == "success"
    # list no fuerza selección
    assert not get_journey({}).get("selected_service_ref")


def test_t19b_list_does_not_auto_select(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}

    def _disp(action, **kwargs):
        return ActionResult(
            action="service_list",
            status="success",
            user_message="ok",
            data={"services": [], "count": 2},
        )

    with (
        patch("app.services.eko_journeys.dispatch_runtime", side_effect=_disp),
        patch(
            "app.services.portal_services.catalog_for_selection",
            return_value=_cat(
                _row(sid="a", login="INTA"),
                _row(sid="b", login="INTB"),
            ),
        ),
    ):
        maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "Mostrame mis servicios",
            canal="wa",
            ctx=ctx,
        )
    assert get_selected_ref(ctx) is None
    assert len(get_journey(ctx).get("selection_options") or []) == 2


def test_t20_billing_regression():
    """Selección 2.2B no roba routing de billing 2.1."""
    assert detect_journey_name("¿Cuánto debo?") == "billing_self_service"
    assert detect_journey_name("quiero pagar") == "billing_self_service"
    assert detect_journey_name("ver mi factura") == "billing_self_service"
    assert detect_journey_name("talon de pago") == "billing_self_service"
    assert detect_journey_name("¿Cuándo vence?") == "billing_self_service"
    assert detect_journey_name("historial de pago") == "billing_self_service"
    assert detect_journey_name("¿Qué servicios tengo?") == "service_catalog"


def test_t21_connectivity_regression_no_probes_without_selection(monkeypatch):
    """Sin selección inequívoca no se dispara diagnóstico/probes."""
    _enable(monkeypatch)
    assert detect_journey_name("No tengo internet") == "internet_sin_conectividad"
    assert detect_journey_name("Bueno, ¿y el Internet?") == "internet_sin_conectividad"

    probe = MagicMock()
    ctx: dict = {}
    set_journey(
        ctx,
        name="service_catalog",
        selection_options=[
            option_from_row(_row(sid="a", login="INTA", product="Internet 300M")),
            option_from_row(_row(sid="b", login="INTB", product="Internet 600M")),
        ],
        next_required_input="service",
    )
    with (
        patch(
            "app.services.portal_services.catalog_for_selection",
            return_value=_cat(
                _row(sid="a", login="INTA", product="Internet 300M"),
                _row(sid="b", login="INTB", product="Internet 600M"),
            ),
        ),
        patch("app.services.portal_connectivity.evaluar_conectividad_portal", probe),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "quiero el internet",
            canal="wa",
            ctx=ctx,
        )
    assert t is not None
    assert t.journey == "service_catalog"
    assert t.action_status in ("needs_input", "unavailable")
    assert get_selected_ref(ctx) is None
    probe.assert_not_called()


def test_t22_casi_llm_cannot_mutate_selection_state():
    """CASI: propuesta LLM no persiste selected_service sin validación catálogo."""
    bootstrap_registry()
    ctx: dict = {}
    r = resolve_service_selection(
        texto="elegí el inventado",
        catalog=[_row(sid="real", login="INT1")],
        client_number="18099",
        proposed_service_id="llm-fake-id",
        proposed_login="FAKELOGIN",
    )
    assert r.status == "denied"
    assert r.ref is None
    assert get_selected_ref(ctx) is None

    cleaned = sanitize_parameters(
        {
            "service_id": "llm-fake-id",
            "login": "FAKELOGIN",
            "client_number": "99999",
            "abonado_id": "evil",
        }
    )
    assert "client_number" not in cleaned
    assert "abonado_id" not in cleaned
    assert "service_id" not in cleaned
    assert "login" not in cleaned

    req = parse_llm_action_proposal(
        {
            "action": "service_list",
            "parameters": {"client_number": "EVIL", "service_id": "x"},
        }
    )
    assert req is not None
    assert "client_number" not in req.parameters

    # Aplicar ref inventada solo ocurre tras resolve selected; aquí negó.
    assert get_selected_ref(ctx) is None

    trusted = TrustedContext(
        abonado=_abo(client_number="18099"),
        organization_id="org",
        confirmation_received=False,
    )
    assert str(getattr(trusted.abonado, "client_number", "")) == "18099"
    ar = execute_action(
        ActionRequest(
            action="create_ticket",
            parameters={"motivo": "alta servicio"},
            source="llm_proposal",
        ),
        trusted,
    )
    assert ar.status in ("needs_confirmation", "denied", "unavailable")
