"""EKO-CTX-1 — servicio en foco en CONTEXTO_ABONADO (criterios brief §4)."""

from __future__ import annotations

import copy
from unittest.mock import patch

from app.services.canal_diagnostico_ia import _extras_servicio_y_planta
from app.services.eko_context import format_n1_contexto
from app.services.eko_service_selection import ServiceRef

TECH_CTX = {
    "pppoe_login": "loginA",
    "pppoe_resumen": "PPPoE A online",
    "pppoe_triage": "ok",
    "uisp_resumen": "UISP A",
    "uisp_signal_dbm": "-58",
    "bcm_resumen": "ONU A",
    "tecnologia_acceso": "ftth",
}


def _ref(login: str, label: str = "Casa") -> dict:
    return {
        "eko_journey": {
            "selected_service_ref": ServiceRef(
                service_id="s1", login=login, service_type="internet",
                client_number="1", label=label,
            ).to_dict()
        }
    }


def _facts(items, tickets=None):
    return {
        "customer": {"display_name": "Ana", "line_msisdn": ""},
        "account": {"client_number": "1", "status": "activo", "plan": "x"},
        "billing": {"status": "stale", "balance": {"amount": "0"}},
        "services": {"status": "ok", "items": items},
        "tickets": tickets or {"status": "ok", "items": []},
    }


NET = lambda label: {"type": "internet", "label": label, "active": True}  # noqa: E731
TWO = [NET("Casa"), NET("Local")]


def test_1_con_ref_muestra_servicio_en_foco():
    ctx = _ref("loginA")
    extras = _extras_servicio_y_planta(ctx, None, None)
    txt = format_n1_contexto(_facts(TWO), extras=extras)
    assert "## SERVICE IN FOCUS" in txt
    assert "servicio_en_foco: Casa (loginA)" in txt


def test_2_sin_ref_y_multi_no_copia_planta_y_pide_elegir():
    ctx = dict(TECH_CTX)
    with patch("app.services.eko_context.internet_logins_count", return_value=2):
        extras = _extras_servicio_y_planta(ctx, object(), object())
    assert not any(k.startswith(("pppoe_", "uisp_", "bcm_")) for k in extras)
    txt = format_n1_contexto(_facts(TWO), extras=extras)
    assert "servicio_en_foco: (sin seleccionar — preguntar cuál antes de diagnosticar)" in txt


def test_3_login_distinto_al_ref_no_copia_pppoe():
    # Ajustado (regla relajada): con mismatch solo se descarta el grupo en mismatch.
    ctx = {**TECH_CTX, **_ref("loginB")}
    extras = _extras_servicio_y_planta(ctx, None, None)
    assert not any(k.startswith("pppoe_") for k in extras)
    assert extras["servicio_foco_login"] == "loginB"
    # coincidente: sí se copia
    ctx_ok = {**TECH_CTX, **_ref("LOGINA")}
    assert _extras_servicio_y_planta(ctx_ok, None, None)["pppoe_resumen"] == "PPPoE A online"


def _planta(extras):
    return sorted(k for k in extras if k.startswith(("pppoe_", "uisp_", "bcm_")))


def test_A_ref_con_canal_pppoe_sin_login_copia():
    ctx = {**_ref("loginA"), "pppoe_resumen": "online", "pppoe_triage": "ok",
           "pppoe_producto": "BAI 10", "pppoe_plan_mbps": "10"}
    assert _planta(_extras_servicio_y_planta(ctx, None, None)) == [
        "pppoe_plan_mbps", "pppoe_producto", "pppoe_resumen", "pppoe_triage"]


def test_B_ref_con_bcm_sin_login_copia():
    ctx = {**_ref("loginA"), "bcm_resumen": "ONU ok", "bcm_triage": "x",
           "tecnologia_acceso": "ftth"}
    extras = _extras_servicio_y_planta(ctx, None, None)
    assert _planta(extras) == ["bcm_resumen", "bcm_triage"]
    assert extras["tecnologia_acceso"] == "ftth"


def test_C_ref_con_pppoe_login_igual_copia():
    ctx = {**_ref("loginA"), "pppoe_login": "LoginA", "pppoe_resumen": "online",
           "bcm_resumen": "ONU"}
    assert _planta(_extras_servicio_y_planta(ctx, None, None)) == ["bcm_resumen", "pppoe_resumen"]


def test_D_ref_con_uisp_login_igual_sin_pppoe_login_copia():
    ctx = {**_ref("loginA"), "uisp_login": "loginA", "uisp_resumen": "antena ok",
           "uisp_signal_dbm": "-58"}
    assert _planta(_extras_servicio_y_planta(ctx, None, None)) == [
        "uisp_resumen", "uisp_signal_dbm"]


def test_E_ref_con_pppoe_login_distinto_descarta_pppoe_y_conserva_resto():
    ctx = {**_ref("loginA"), "pppoe_login": "loginB", "pppoe_resumen": "B",
           "uisp_resumen": "u", "bcm_resumen": "b"}
    assert _planta(_extras_servicio_y_planta(ctx, None, None)) == ["bcm_resumen", "uisp_resumen"]


def test_F_ref_con_uisp_login_distinto_descarta_uisp_y_conserva_resto():
    ctx = {**_ref("loginA"), "uisp_login": "loginB", "uisp_resumen": "B",
           "pppoe_resumen": "p", "bcm_resumen": "b"}
    assert _planta(_extras_servicio_y_planta(ctx, None, None)) == ["bcm_resumen", "pppoe_resumen"]


def test_ambos_logins_distintos_descarta_tambien_bcm_y_tecnologia():
    ctx = {**_ref("loginA"), "pppoe_login": "B", "uisp_login": "B", "pppoe_resumen": "p",
           "uisp_resumen": "u", "bcm_resumen": "b", "tecnologia_acceso": "ftth"}
    assert _extras_servicio_y_planta(ctx, None, None).keys() == {
        "servicio_foco_login", "servicio_foco_tipo", "servicio_foco_label", "servicio_foco_id"}


def test_4_un_solo_servicio_unico_servicio_sin_inventar_login():
    with patch("app.services.eko_context.internet_logins_count", return_value=1):
        extras = _extras_servicio_y_planta(dict(TECH_CTX), object(), object())
    assert extras["pppoe_resumen"] == "PPPoE A online"
    txt = format_n1_contexto(_facts([NET("Casa")]), extras=extras)
    assert "servicio_en_foco: único servicio" in txt
    assert "loginA" not in txt


def test_5_tickets_con_fecha_y_sin_tickets_igual():
    t = {"status": "ok", "items": [
        {"id": "IBOT-1234567890", "state": "open", "category": "internet",
         "updated_at": "2026-09-30T10:00:00+00:00"},
        {"id": "IBOT-2", "state": "open", "category": "x"},
    ]}
    txt = format_n1_contexto(_facts(TWO, t), extras={})
    assert "IBOT-1234567:open/internet (actualizado: 2026-09-30)" in txt
    assert "IBOT-2:open/x;" not in txt and "IBOT-2:open/x" in txt
    assert "IBOT-2:open/x (actualizado" not in txt
    vacio = format_n1_contexto(_facts(TWO), extras={})
    assert "- tickets: (ninguno visible)" in vacio


def test_6_invitado_render_identico():
    base = format_n1_contexto({"customer": None}, extras={})
    con = format_n1_contexto(
        {"customer": None},
        extras={"servicio_foco_login": "loginA", "servicio_foco_label": "Casa"},
    )
    assert base == con
    assert "SERVICE IN FOCUS" not in base


def test_7_solo_lectura_ctx_no_cambia():
    for ctx in ({**TECH_CTX, **_ref("loginA")}, {**TECH_CTX, **_ref("loginB")}):
        before = copy.deepcopy(ctx)
        extras = _extras_servicio_y_planta(ctx, None, None)
        format_n1_contexto(_facts(TWO), extras=extras)
        assert ctx == before
    ctx = dict(TECH_CTX)
    before = copy.deepcopy(ctx)
    with patch("app.services.eko_context.internet_logins_count", return_value=2):
        _extras_servicio_y_planta(ctx, object(), object())
    assert ctx == before
    assert "login_seleccionado" not in ctx


def test_sin_ref_ni_regla_no_hay_seccion():
    txt = format_n1_contexto(_facts([]), extras={})
    assert "SERVICE IN FOCUS" not in txt
