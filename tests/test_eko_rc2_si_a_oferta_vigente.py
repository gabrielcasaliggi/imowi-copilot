"""RC-2 (ADR contrato de turno): el «sí» confirma solo si el turno anterior del bot fue la oferta vigente."""

from __future__ import annotations

from types import SimpleNamespace

from app.services import eko_journeys as ej
from app.services.eko_action_bridge import resolve_user_confirmation


def test_si_sin_oferta_ni_estado_no_confirma():
    assert resolve_user_confirmation(ctx={}, action="create_ticket", texto="sí") == (False, False)


def test_si_con_oferta_vigente_confirma_y_no_rechaza():
    assert resolve_user_confirmation(ctx={}, action="create_ticket", texto="sí", offer_live=True) == (True, False)
    assert resolve_user_confirmation(ctx={}, action="create_ticket", texto="no", offer_live=True) == (False, True)


def test_texto_libre_con_oferta_vigente_no_confirma():
    assert resolve_user_confirmation(ctx={}, action="create_ticket", texto="sigue igual", offer_live=True) == (False, False)


def _ctx(offered):
    ctx: dict = {}
    ej.set_journey(ctx, pending_confirmation=True, confirmation_offer_inbound=offered)
    return ctx


def test_oferta_es_el_turno_anterior_solo_si_no_hubo_otro_mensaje(monkeypatch):
    conv = SimpleNamespace(id="c1")
    monkeypatch.setattr(ej, "_inbound_count", lambda db, c: 3)
    assert ej._offer_is_previous_turn(object(), conv, _ctx(2)) is True
    assert ej._offer_is_previous_turn(object(), conv, _ctx(1)) is False  # hubo otro turno del abonado entre medio


def test_sin_dato_no_se_puede_afirmar_lo_contrario(monkeypatch):
    conv = SimpleNamespace(id="c1")
    monkeypatch.setattr(ej, "_inbound_count", lambda db, c: 5)
    assert ej._offer_is_previous_turn(object(), conv, _ctx(None)) is True
    monkeypatch.setattr(ej, "_inbound_count", lambda db, c: None)
    assert ej._offer_is_previous_turn(object(), conv, _ctx(2)) is True
