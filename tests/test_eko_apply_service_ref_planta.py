"""EKO 2.5-ext — apply_service_ref limpia la planta del servicio anterior al cambiar."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import canal_abonado as c
from app.services.eko_journeys import apply_service_ref
from app.services.eko_service_selection import ServiceRef, get_selected_ref
from tests.test_multi_cuenta_senal import _servicios_tupacireta

PLANTA = {
    "pppoe_login": "loginA",
    "pppoe_resumen": "A online",
    "pppoe_producto": "BAI 10",
    "pppoe_plan_mbps": "10",
    "pppoe_ip": "1.2.3.4",
    "uisp_resumen": "antena A",
    "uisp_signal_dbm": "-58",
    "bcm_resumen": "ONU A",
    "bcm_rx_dbm": "-20",
    "tecnologia_acceso": "ftth",
}
OTRAS = {"intencion": "internet_lento", "canal": "portal", "diag_turnos": 2, "dni": "30111222"}


def _ref(sid: str, login: str) -> ServiceRef:
    return ServiceRef(service_id=sid, login=login, service_type="internet", client_number="1")


def test_cambio_a_b_limpia_planta_anterior():
    ctx = {**PLANTA, **OTRAS}
    apply_service_ref(ctx, _ref("sA", "loginA"))  # primera selección
    ctx.update(PLANTA)
    apply_service_ref(ctx, _ref("sB", "loginB"))
    assert not any(k.startswith(("pppoe_", "uisp_", "bcm_")) for k in ctx)
    assert "tecnologia_acceso" not in ctx
    assert get_selected_ref(ctx).login == "loginB"


def test_primera_seleccion_no_limpia():
    ctx = {**PLANTA, **OTRAS}
    apply_service_ref(ctx, _ref("sA", "loginA"))
    for k, v in PLANTA.items():
        assert ctx[k] == v


def test_mismo_servicio_no_limpia():
    ctx = {**OTRAS}
    apply_service_ref(ctx, _ref("sA", "loginA"))
    ctx.update(PLANTA)
    apply_service_ref(ctx, _ref("sA", "loginA"))
    for k, v in PLANTA.items():
        assert ctx[k] == v


def test_claves_no_tecnicas_y_journey_no_se_tocan():
    ctx = {**OTRAS}
    apply_service_ref(ctx, _ref("sA", "loginA"))
    ctx.update(PLANTA)
    ctx["eko_journey"]["domain_stack"] = ["tec-1"]
    apply_service_ref(ctx, _ref("sB", "loginB"))
    for k, v in OTRAS.items():
        assert ctx[k] == v
    assert ctx["eko_journey"]["domain_stack"] == ["tec-1"]
    assert ctx["eko_journey"]["selected_service_ref"]["login"] == "loginB"


def test_canal_texto_a_luego_b_repone_planta_del_login_nuevo(monkeypatch):
    abo = SimpleNamespace(dni="30111222", client_number="2677")
    cat = [
        {"id": "s1", "login": "lemuramatiBAI", "type": "internet", "label": "Casa", "active": True},
        {"id": "s2", "login": "tupaciretacuidaBAI", "type": "internet", "label": "Local", "active": True},
    ]
    monkeypatch.setattr(c, "_servicios_conectividad_abonado", lambda _d, _a: _servicios_tupacireta())
    monkeypatch.setattr(
        "app.services.portal_services.catalog_for_selection",
        lambda _db, abonado: {"status": "ok", "services": cat},
    )

    def fake_sync(_db, _abo, ctx, login):
        ctx["login_seleccionado"] = login
        ctx["pppoe_login"] = login
        ctx["pppoe_resumen"] = f"resumen {login}"

    monkeypatch.setattr("app.services.conexion_uisp.sincronizar_servicio_login_en_ctx", fake_sync)
    ctx = {"uisp_resumen": "antena vieja", "bcm_resumen": "onu vieja"}
    c._sincronizar_login_desde_mensaje(MagicMock(), abo, ctx, "lemuramatiBAI")
    c._sincronizar_login_desde_mensaje(MagicMock(), abo, ctx, "tupaciretacuidaBAI")
    assert ctx["pppoe_resumen"] == "resumen tupaciretacuidaBAI"
    assert ctx["pppoe_login"] == "tupaciretacuidaBAI"
    assert "uisp_resumen" not in ctx and "bcm_resumen" not in ctx
