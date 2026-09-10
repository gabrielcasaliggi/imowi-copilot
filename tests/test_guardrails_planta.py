"""La rama de planta manda: no preguntar Wi‑Fi con ONU caída ni luces con enlace OK."""

from __future__ import annotations

from app.services.conexion_bcm import evaluar_turno_onu_bcm
from app.services.conexion_uisp import evaluar_turno_visita_antena_uisp
from app.services.diagnostico_n1 import diagnosticar_turno
from app.services.guardrails_planta import (
    aplicar_guardrails_planta,
    evaluar_turno_sensa_planta,
)

CTX_BCM_OK = (
    "CONTEXTO_ABONADO:\n"
    "- bcm: nro_cliente=1; estado=en_linea; rx=-18.2dBm; calidad=buena\n"
    "- bcm_triage: triage=onu_ftth_enlace_ok; indagar Wi‑Fi\n"
)

CTX_BCM_OFF = (
    "CONTEXTO_ABONADO:\n"
    "- bcm: nro_cliente=1; estado=fuera_de_linea\n"
    "- bcm_triage: triage=onu_ftth_offline; chequear luces PON/LOS\n"
)

CTX_UISP_OK = (
    "CONTEXTO_ABONADO:\n"
    "- uisp: login=x; estado=en_linea; senal=-55dBm; calidad=buena\n"
    "- uisp_triage: triage=cpe_radio_enlace_ok; indagar Wi‑Fi\n"
)

CTX_UISP_OFF = (
    "CONTEXTO_ABONADO:\n"
    "- uisp: login=x; estado=fuera_de_linea\n"
    "- uisp_triage: triage=cpe_radio_offline\n"
)

_CHECKLIST_FTTH = [
    {"id": "energia_ont", "pregunta": "¿La cajita blanca tiene luces encendidas?"},
    {"id": "wifi_vs_cable_ftth", "pregunta": "¿Falla también por cable al router, o solo el WiFi?"},
]


def test_guardrail_enlace_ok_no_pregunta_luces():
    out = aplicar_guardrails_planta(
        mensaje="Dale, arrancamos por fibra. ¿La cajita blanca tiene luces encendidas?",
        contexto_abonado=CTX_BCM_OK,
        accion="ask",
    )
    assert out["motivo"] == "bloqueado_luces_con_enlace_ok"
    low = out["mensaje"].lower()
    assert "wifi" in low.replace("‑", "").replace("-", "") or "wi-fi" in low
    assert "cajita" not in low


def test_guardrail_onu_offline_no_pregunta_wifi():
    out = aplicar_guardrails_planta(
        mensaje="Sigamos en tu casa: ¿no te anda en ningún dispositivo o solo por Wi‑Fi?",
        contexto_abonado=CTX_BCM_OFF,
        accion="ask",
    )
    assert out["motivo"] == "bloqueado_wifi_con_onu_offline"
    low = out["mensaje"].lower()
    assert "pon" in low or "los" in low
    assert "wifi" not in low.replace("‑", "-")


def test_evaluar_bcm_enlace_ok_va_a_wifi():
    out = evaluar_turno_onu_bcm(
        contexto_abonado=CTX_BCM_OK,
        mensaje_cliente="sigue sin andar internet",
        historial_mensajes=[],
        pasos_cubiertos=[],
        turnos_diagnostico=1,
        intencion="internet_ftth",
    )
    assert out is not None
    assert out["motivo"] == "bcm_enlace_ok_wifi"
    low = (out["mensaje"] or "").lower()
    assert "luces" not in low
    assert "cajita" not in low


def test_evaluar_bcm_enlace_ok_no_repite_si_ya_esta_en_wifi():
    out = evaluar_turno_onu_bcm(
        contexto_abonado=CTX_BCM_OK,
        mensaje_cliente="me pasa en todos los celulares",
        historial_mensajes=[],
        pasos_cubiertos=["wifi_vs_cable_ftth", "otros_dispositivos_wifi"],
        turnos_diagnostico=2,
        intencion="wifi",
    )
    assert out is None


def test_evaluar_uisp_enlace_ok_va_a_wifi():
    out = evaluar_turno_visita_antena_uisp(
        contexto_abonado=CTX_UISP_OK,
        mensaje_cliente="sigue sin andar",
        historial_mensajes=[],
        pasos_cubiertos=[],
        turnos_diagnostico=1,
        intencion="internet_radio",
    )
    assert out is not None
    assert out["motivo"] == "uisp_enlace_ok_wifi"
    assert "wifi" in (out["mensaje"] or "").lower().replace("‑", "-").replace("-", "")


def test_evaluar_uisp_offline_pregunta_poe_no_wifi():
    out = evaluar_turno_visita_antena_uisp(
        contexto_abonado=CTX_UISP_OFF,
        mensaje_cliente="no tengo internet",
        historial_mensajes=[],
        pasos_cubiertos=[],
        turnos_diagnostico=0,
        intencion="internet_radio",
    )
    assert out is not None
    assert out["motivo"] == "uisp_cpe_offline"
    low = (out["mensaje"] or "").lower()
    assert "poe" in low or "inyecto" in low
    assert "wifi" not in low.replace("‑", "-")


def test_diagnosticar_pon_verde_en_wifi_no_repregunta_luces(monkeypatch):
    monkeypatch.setattr(
        "app.llm.chat_completion",
        lambda *_a, **_k: (
            '{"accion":"ask","mensaje":"¿La cajita blanca tiene luces encendidas?",'
            '"paso_cubierto":"energia_ont","motivo":"ia"}'
        ),
    )
    out = diagnosticar_turno(
        intencion="wifi",
        checklist=_CHECKLIST_FTTH,
        historial_mensajes=[],
        mensaje_cliente="La PON está verde y la LOS apagada",
        turnos_diagnostico=2,
        pasos_cubiertos=["wifi_vs_cable_ftth"],
        contexto_abonado="",
    )
    assert out["motivo"] == "pon_verde_enlace_ok"
    low = (out["mensaje"] or "").lower()
    assert "cajita" not in low
    assert "luces encendidas" not in low


def test_diagnosticar_llm_no_pisa_bcm_enlace_ok(monkeypatch):
    monkeypatch.setattr(
        "app.llm.chat_completion",
        lambda *_a, **_k: (
            '{"accion":"ask","mensaje":"¿La cajita blanca tiene luces encendidas?",'
            '"paso_cubierto":"energia_ont","motivo":"ia"}'
        ),
    )
    out = diagnosticar_turno(
        intencion="internet_ftth",
        checklist=_CHECKLIST_FTTH,
        historial_mensajes=[],
        mensaje_cliente="sigue igual",
        turnos_diagnostico=2,
        pasos_cubiertos=["wifi_vs_cable_ftth", "zona_wifi"],
        contexto_abonado=CTX_BCM_OK,
    )
    low = (out["mensaje"] or "").lower()
    assert "cajita" not in low
    assert "luces encendidas" not in low
    assert out["motivo"] in (
        "bloqueado_luces_con_enlace_ok",
        "bcm_enlace_ok_wifi",
        "bloqueado_ont_post_linea_ok",
    )


def test_sensa_con_onu_offline_no_empieza_por_la_app():
    out = evaluar_turno_sensa_planta(
        contexto_abonado=CTX_BCM_OFF,
        mensaje_cliente="no me anda Sensa",
        pasos_cubiertos=[],
        intencion="tv_sensa",
    )
    assert out is not None
    assert out["motivo"] == "sensa_depende_acceso_malo"
    low = (out["mensaje"] or "").lower()
    assert "sensa" in low
    assert "pon" in low or "los" in low


def test_sensa_con_internet_en_equipo_sigue_playbook():
    out = evaluar_turno_sensa_planta(
        contexto_abonado=CTX_BCM_OFF,
        mensaje_cliente="usuario incorrecto",
        pasos_cubiertos=["internet_en_disp", "navega_en_disp"],
        intencion="tv_sensa",
    )
    assert out is None


def test_sensa_enlace_ok_no_pregunta_luces_de_casa():
    out = aplicar_guardrails_planta(
        mensaje="¿La cajita blanca tiene luces encendidas?",
        contexto_abonado=CTX_BCM_OK,
        accion="ask",
        intencion="tv_sensa",
    )
    assert out["motivo"] == "bloqueado_luces_sensa_con_enlace_ok"
    low = out["mensaje"].lower()
    assert "sensa" in low
    assert "cajita" not in low
    assert "wifi" not in low.replace("‑", "-")


def test_bcm_no_roba_sensa_ni_imowi_ni_adsl():
    for intent in ("tv_sensa", "movil_datos", "internet_adsl"):
        out = evaluar_turno_onu_bcm(
            contexto_abonado=CTX_BCM_OK,
            mensaje_cliente="sigue sin andar",
            historial_mensajes=[],
            pasos_cubiertos=[],
            turnos_diagnostico=1,
            intencion=intent,
        )
        assert out is None, intent


def test_adsl_no_pregunta_fibra():
    out = aplicar_guardrails_planta(
        mensaje="¿La cajita blanca tiene luces PON o LOS?",
        contexto_abonado=CTX_BCM_OK,
        accion="ask",
        intencion="internet_adsl",
    )
    assert out["motivo"] == "bloqueado_fibra_en_adsl"
    assert "adsl" in out["mensaje"].lower() or "tono" in out["mensaje"].lower()


def test_imowi_no_pisa_apn_con_planta():
    out = aplicar_guardrails_planta(
        mensaje="En Android creá el APN imowi. ¿Navega?",
        contexto_abonado=CTX_BCM_OK,
        accion="ask",
        intencion="movil_datos",
    )
    assert out["motivo"] == ""
    assert "apn" in out["mensaje"].lower()


def test_diagnosticar_sensa_con_planta_mala(monkeypatch):
    monkeypatch.setattr(
        "app.llm.chat_completion",
        lambda *_a, **_k: (
            '{"accion":"ask","mensaje":"¿Confirmás usuario y contraseña de Sensa?",'
            '"paso_cubierto":"app_sensa","motivo":"ia"}'
        ),
    )
    out = diagnosticar_turno(
        intencion="tv_sensa",
        checklist=[
            {"id": "triaje_tv_sensa", "pregunta": "¿App Sensa o decodificador?"},
            {"id": "internet_en_disp", "pregunta": "¿Tenés internet en el equipo?"},
        ],
        historial_mensajes=[],
        mensaje_cliente="no me anda la tele Sensa",
        turnos_diagnostico=0,
        pasos_cubiertos=[],
        contexto_abonado=CTX_BCM_OFF,
    )
    assert out["motivo"] == "sensa_depende_acceso_malo"
    assert "contraseña" not in (out["mensaje"] or "").lower()

