"""Contador E1 y lectura forzada OLT/WIS."""

from __future__ import annotations

from app.services.turno_e1 import (
    MAX_TURNOS_E1_SIN_RESOLUCION,
    debe_forzar_lectura_e1,
    es_intencion_e1_acceso,
    tecnologia_e1,
    turnos_e1,
    veredicto_desde_ctx,
)


def test_umbral_e1_son_tres_turnos():
    assert MAX_TURNOS_E1_SIN_RESOLUCION == 3
    assert es_intencion_e1_acceso("internet_ftth")
    assert es_intencion_e1_acceso("internet_radio")
    assert not es_intencion_e1_acceso("wifi")
    assert not es_intencion_e1_acceso("movil_datos")
    assert not es_intencion_e1_acceso("facturacion_pago")


def test_no_fuerza_antes_de_tres_turnos():
    ctx = {"diag_turnos": 2, "intencion": "internet_ftth"}
    assert not debe_forzar_lectura_e1(ctx, "internet_ftth", "sigue sin internet")


def test_fuerza_al_tercer_turno_sin_resolucion():
    ctx = {"diag_turnos": 3}
    assert debe_forzar_lectura_e1(ctx, "internet_ftth", "sigue sin internet")
    assert debe_forzar_lectura_e1(ctx, "internet", "no me anda nada")


def test_no_fuerza_si_ya_leyo_o_acceso_ok():
    assert not debe_forzar_lectura_e1(
        {"diag_turnos": 5, "lectura_forzada_e1": True},
        "internet_ftth",
        "sigue igual",
    )
    assert not debe_forzar_lectura_e1(
        {"diag_turnos": 5, "bcm_triage": "triage=onu_ftth_enlace_ok; indagar Wi‑Fi"},
        "internet_ftth",
        "sigue igual",
    )
    assert not debe_forzar_lectura_e1(
        {"diag_turnos": 5, "wifi_rama_activada": True},
        "internet",
        "sigue igual",
    )


def test_no_fuerza_si_el_cliente_cerro():
    ctx = {"diag_turnos": 4}
    assert not debe_forzar_lectura_e1(ctx, "internet_ftth", "listo, ya anda")


def test_veredicto_y_tecnologia_desde_ctx():
    assert veredicto_desde_ctx({"bcm_rama": "potencia_mala"}) == "acceso_malo"
    assert veredicto_desde_ctx({"bcm_rama": "enlace_ok"}) == "acceso_ok"
    assert veredicto_desde_ctx({"uisp_rama": "cpe_offline"}) == "acceso_malo"
    assert veredicto_desde_ctx({}) == "sin_dato"
    assert tecnologia_e1({"tecnologia_acceso": "internet_radio"}, "internet") == (
        "internet_radio"
    )
    assert turnos_e1({"diag_turnos": 3}) == 3
