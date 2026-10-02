"""EKO-2.8A — login nombrado por texto → selected_service_ref (única autoridad)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import canal_abonado as c
from app.services.eko_action_runtime import (
    ActionRequest,
    TrustedContext,
    _exec_run_diagnostic_pppoe,
)
from app.services.eko_service_selection import get_selected_ref
from tests.test_multi_cuenta_senal import _servicios_tupacireta

ABO = SimpleNamespace(dni="30111222", client_number="2677")
CATALOG = [
    {"id": "s1", "login": "lemuramatiBAI", "type": "internet", "label": "Casa", "active": True},
    {"id": "s2", "login": "tupaciretacuidaBAI", "type": "internet", "label": "Local", "active": True},
]


@pytest.fixture
def env(monkeypatch):
    calls = {"sync": []}

    def fake_sync(_db, _abo, ctx, login):
        calls["sync"].append(login)
        ctx["login_seleccionado"] = login
        ctx["pppoe_login"] = login

    monkeypatch.setattr(c, "_servicios_conectividad_abonado", lambda _d, _a: _servicios_tupacireta())
    monkeypatch.setattr("app.services.conexion_uisp.sincronizar_servicio_login_en_ctx", fake_sync)
    monkeypatch.setattr(
        "app.services.portal_services.catalog_for_selection",
        lambda _db, abonado: {"status": "ok", "services": CATALOG},
    )
    return calls


def _run(ctx):
    return c._sincronizar_login_desde_mensaje(MagicMock(), ABO, ctx, "la de tupaciretacuidaBAI")


def test_login_nombrado_fija_ref_y_limpia_pendiente(env):
    ctx = {"multi_cuenta_pendiente": True}
    assert _run(ctx) == "tupaciretacuidaBAI"
    ref = get_selected_ref(ctx)
    assert ref is not None and ref.login == "tupaciretacuidaBAI" and ref.service_id == "s2"
    assert ref.client_number == "2677"
    assert "multi_cuenta_pendiente" not in ctx


def test_turno_posterior_no_repregunta_cuenta(env, monkeypatch):
    ctx = {"multi_cuenta_pendiente": True}
    _run(ctx)
    monkeypatch.setattr("app.services.eko_action_runtime._internet_login_count", lambda _t: 3)
    res = _exec_run_diagnostic_pppoe(
        ActionRequest("run_diagnostic_pppoe"),
        TrustedContext(abonado=ABO, ctx=ctx, db=None),
    )
    assert res.reason_code != "service_selection_required"


def test_login_igual_a_prev_pero_sin_ref_igual_enriquece(env):
    ctx = {"login_seleccionado": "tupaciretacuidaBAI"}
    _run(ctx)
    assert get_selected_ref(ctx).login == "tupaciretacuidaBAI"
    assert env["sync"] == []  # no re-sincroniza planta


def test_login_con_ref_vigente_no_hace_nada(env):
    ctx: dict = {}
    _run(ctx)
    env["sync"].clear()
    _run(ctx)
    assert env["sync"] == []


def test_login_fuera_del_catalogo_no_setea_ref_ni_fallback(env, monkeypatch):
    monkeypatch.setattr(
        "app.services.portal_services.catalog_for_selection",
        lambda _db, abonado: {"status": "ok", "services": [CATALOG[0]]},
    )
    ctx: dict = {}
    _run(ctx)
    assert get_selected_ref(ctx) is None


def test_catalogo_no_disponible_no_setea_ref(env, monkeypatch):
    monkeypatch.setattr(
        "app.services.portal_services.catalog_for_selection",
        lambda _db, abonado: {"status": "unavailable", "services": []},
    )
    ctx: dict = {}
    _run(ctx)
    assert get_selected_ref(ctx) is None


def test_cambio_de_login_resetea_diagnostico(env):
    ctx: dict = {}
    c._sincronizar_login_desde_mensaje(MagicMock(), ABO, ctx, "lemuramatiBAI")
    ctx["eko_journey"]["diagnostic_started"] = True
    _run(ctx)
    assert get_selected_ref(ctx).login == "tupaciretacuidaBAI"
    assert ctx["eko_journey"]["diagnostic_started"] is False
