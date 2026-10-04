"""RC-1 / ADR §b: ``journey_release`` es el único que suelta el estado pendiente al hacer PASS."""

from __future__ import annotations

from app.services.eko_action_runtime import get_action_state, set_action_state
from app.services.eko_journeys import get_journey, journey_release, set_journey


def _ctx(**extra):
    ctx = {
        "multi_cuenta_pendiente": True,
        "menu_paso": "servicio",
        "menu_servicio": "internet",
        "aviso_deuda_ofrecido": True,
        "eko_no_fixed_internet": True,
        "pppoe_informado": True,
        **extra,
    }
    set_journey(
        ctx,
        name="internet_sin_conectividad",
        step="confirm_action",
        pending_confirmation=True,
        confirmation_correlation="c-1",
        next_required_input="confirmation",
        asked_selection=True,
        selection_options=["a", "b"],
        reprompts=1,
        selected_service_ref={"service_id": "int1", "login": "lemuramatiBAI"},
    )
    return ctx


def test_release_limpia_pendientes_y_deja_el_journey_terminado():
    ctx = _ctx()
    journey_release(ctx, "confirmation_expired")
    st = get_journey(ctx)
    assert st["step"] == "done" and st["released_reason"] == "confirmation_expired"
    assert not st["pending_confirmation"] and not st["confirmation_correlation"]
    assert not st["next_required_input"] and not st["asked_selection"] and st["selection_options"] == []
    assert st["reprompts"] == 0
    assert "multi_cuenta_pendiente" not in ctx


def test_release_no_toca_seleccion_planta_ni_aviso_de_deuda():
    ctx = _ctx()
    journey_release(ctx, "confirmation_expired")
    assert get_journey(ctx)["selected_service_ref"] == {"service_id": "int1", "login": "lemuramatiBAI"}
    assert ctx["aviso_deuda_ofrecido"] and ctx["eko_no_fixed_internet"] and ctx["pppoe_informado"]


def test_release_menu_solo_si_el_journey_lo_consumio():
    ctx = _ctx()
    journey_release(ctx, "x")
    assert ctx["menu_paso"] == "servicio" and ctx["menu_servicio"] == "internet"
    journey_release(ctx, "x", consumed_menu=True)
    assert "menu_paso" not in ctx and "menu_servicio" not in ctx


def test_release_intencion_solo_si_es_de_journey():
    ctx = _ctx(intencion="consulta_servicios")
    journey_release(ctx, "x")
    assert "intencion" not in ctx
    ctx = _ctx(intencion="internet")
    journey_release(ctx, "x")
    assert ctx["intencion"] == "internet"


def test_release_libera_la_confirmacion_del_runtime():
    ctx = _ctx()
    set_action_state(ctx, action="create_ticket", status="confirmation_pending")
    journey_release(ctx, "x")
    assert get_action_state(ctx).get("status") == "released"
