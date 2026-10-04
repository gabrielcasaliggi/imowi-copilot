"""RC-12 — el mensaje «sin Internet fijo» es terminal: el journey queda «done» y suelta el turno siguiente."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.eko_journeys import _journey_is_resolved, get_journey, maybe_handle_journey_turn
from tests.test_eko_service_management_2_2c import _abo, _conv, _enable, _login_count


def _turno(texto, ctx):
    with _login_count(0):
        return maybe_handle_journey_turn(MagicMock(), "org", _conv(), _abo(), texto, canal="wa", ctx=ctx)


def test_mensaje_sin_fijo_deja_el_journey_en_done(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    t = _turno("no tengo internet", ctx)
    assert t and t.reason_code == "no_fixed_internet" and t.step == "done"
    st = get_journey(ctx)
    assert st["step"] == "done" and _journey_is_resolved(st)
    assert ctx["eko_no_fixed_internet"] is True


def test_hola_posterior_no_repite_el_mensaje(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    primero = _turno("no tengo internet", ctx)
    t = _turno("hola", ctx)
    # el journey suelta el turno: sin texto (lo toma el legacy por FIX-1), nunca el mismo párrafo
    assert t is None or not (t.user_message or "").strip() or t.user_message != primero.user_message
    assert t is None or "no veo un servicio de Internet fijo" not in (t.user_message or "")


def test_repetir_el_pedido_de_internet_responde_igual_sin_reabrir(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    primero = _turno("no tengo internet", ctx)
    otra = _turno("no tengo internet", ctx)
    assert otra and otra.user_message == primero.user_message
    assert get_journey(ctx)["step"] == "done"


def test_otro_dominio_sigue_funcionando(monkeypatch):
    _enable(monkeypatch)
    ctx: dict = {}
    _turno("no tengo internet", ctx)
    t = _turno("quiero ver mis servicios", ctx)
    assert t is not None and t.handled and t.journey == "service_catalog"
