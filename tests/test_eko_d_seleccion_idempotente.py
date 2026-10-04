"""EKO D — seleccionar dos veces el mismo servicio no repite la confirmación."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.eko_journeys import get_journey, maybe_handle_journey_turn, set_journey
from tests.test_eko_a_intencion_menu import _CAT, chat  # noqa: F401  (fixture e2e)
from tests.test_eko_service_management_2_2c import _abo, _conv, _enable, _ref, _seed_selection


def _arrancar(say):
    say("hola")
    say("tengo problemas con mi linea de imowi")  # menú de selección


def test_dos_unos_seguidos_dan_listo_y_un_acuse_distinto(chat):  # noqa: F811
    say = chat
    _arrancar(say)
    sent1, ctx1, _t = say("1")
    assert len(sent1) == 1 and sent1[0].startswith("Listo: seleccioné «Imowi 5 GB». (cuenta 2235550001)")  # RC-9: + siguiente paso
    sent2, ctx2, ticket = say("1")
    assert sent2 == ["Ya tengo seleccionado «Imowi 5 GB». Contame qué te pasa."]
    assert not sent2[0].startswith("Listo")
    assert ticket == ""
    # nada se reabrió: mismo ref, journey cerrado, sin selección pendiente
    assert ctx2["eko_journey"]["selected_service_ref"] == ctx1["eko_journey"]["selected_service_ref"]
    assert ctx2["eko_journey"]["step"] == "done"
    assert not ctx2["eko_journey"].get("next_required_input")


def test_tercera_repeticion_sigue_siendo_acuse(chat):  # noqa: F811
    say = chat
    _arrancar(say)
    say("1")
    for _ in range(2):
        sent, _ctx, _t = say("1")
        assert sent[0].startswith("Ya tengo seleccionado")


def test_cambio_real_de_servicio_confirma_con_listo(chat):  # noqa: F811
    say = chat
    _arrancar(say)
    say("1")
    sent, ctx, _t = say("2")
    assert len(sent) == 1 and sent[0].startswith("Listo: seleccioné «Imowi 3 GB». (cuenta 2235550002)")  # RC-9: + siguiente paso
    assert ctx["eko_journey"]["selected_service_ref"]["service_id"] == "m2"
    # y volver a repetir el nuevo servicio sí es acuse
    sent2, _ctx2, _t = say("2")
    assert sent2[0] == "Ya tengo seleccionado «Imowi 3 GB». Contame qué te pasa."


def test_misma_etiqueta_en_otra_linea_no_es_el_mismo_servicio(chat):  # noqa: F811
    say = chat
    _arrancar(say)
    say("2")  # Imowi 3 GB (m2)
    sent, ctx, _t = say("3")  # Imowi 3 GB (m3): otro servicio, misma etiqueta
    assert sent[0].startswith("Listo: seleccioné «Imowi 3 GB»")
    assert ctx["eko_journey"]["selected_service_ref"]["service_id"] == "m3"


def test_si_habia_una_seleccion_pendiente_confirma_aunque_sea_el_mismo(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    _seed_selection(ctx, _ref(sid="m1", login="2235550001", tip="movil", product="Imowi 5 GB"))
    # el abonado volvió a pedir elegir y quedó esperando el número
    set_journey(ctx, step="service_selection", next_required_input="service_selection")
    cat = {"status": "ok", "services": _CAT}
    with patch("app.services.portal_services.catalog_for_selection", lambda _db, abonado: cat):
        turn = maybe_handle_journey_turn(MagicMock(), "org", _conv(), _abo(), "1", canal="wa", ctx=ctx)
    assert turn is not None and turn.user_message.startswith("Listo: seleccioné")
    assert get_journey(ctx)["step"] == "done"


@pytest.mark.parametrize("texto", ["1", "el 1"])
def test_acuse_no_invoca_runtime_ni_tickets(chat, texto):  # noqa: F811
    say = chat
    _arrancar(say)
    say("1")
    with patch("app.services.eko_action_runtime.execute_action") as ex, \
         patch("app.services.canal_abonado._crear_ticket_n2") as tk:
        sent, _ctx, ticket = say(texto)
    assert sent and sent[0].startswith("Ya tengo seleccionado")
    ex.assert_not_called()
    tk.assert_not_called()
    assert ticket == ""
