"""Tests de rama Wi‑Fi post PPPoE (sin preguntar ONT)."""

from __future__ import annotations

from app.services.canal_abonado import _cliente_cable_ok, _cliente_indica_solo_wifi
from app.services.diagnostico_n1 import diagnosticar_turno
from app.services.eco_voice import system_prompt_eco_n1


def test_cliente_indica_solo_wifi():
    assert _cliente_indica_solo_wifi("solo falla el wifi")
    assert _cliente_indica_solo_wifi("Solo el Wi-Fi")
    assert _cliente_indica_solo_wifi("falla solo wifi")
    assert not _cliente_indica_solo_wifi("no me anda internet")
    assert not _cliente_indica_solo_wifi("")


def test_cliente_cable_ok():
    assert _cliente_cable_ok("tengo un tv conectado por cable y funciona bien")
    assert _cliente_cable_ok("por cable funciona")
    assert not _cliente_cable_ok("por cable no funciona")


def test_system_prompt_linea_ok_no_ont():
    p = system_prompt_eco_n1(
        intencion="internet_ftth",
        turnos=2,
        min_turnos_antes_escalar=4,
        contexto_abonado=(
            "CONTEXTO_ABONADO:\n"
            "- pppoe: estado=conectado\n"
            "- pppoe_triage: triage=linea_ok_indagar_wifi_vs_cable; "
            "NO pedir reinicio de ONT como primer paso\n"
        ),
    )
    assert "NUNCA preguntes por luces ONT" in p
    assert "cajita blanca" in p.lower() or "ONT" in p


def test_diagnosticar_no_fuerza_pon_si_linea_ok():
    """Con triage linea_ok, confirmar 'verde' no debe disparar plantilla PON."""
    hist = [
        {"autor": "bot", "texto": "¿No te anda en ningún dispositivo o solo por Wi‑Fi?"},
        {"autor": "cliente", "texto": "solo falla el wifi"},
    ]
    # Sin linea_ok sí podría; con linea_ok en contexto no debe devolver pon_verde
    r = diagnosticar_turno(
        intencion="internet_ftth",
        checklist=[{"id": "luces_los", "pregunta": "¿Luces?"}],
        historial_mensajes=hist,
        mensaje_cliente="esta todo verde fijo",
        turnos_diagnostico=3,
        pasos_cubiertos=["wifi_vs_cable_ftth"],
        forzar_agente=False,
        contexto_abonado=(
            "pppoe_triage: triage=linea_ok_indagar_wifi_vs_cable; "
            "NO pedir reinicio de ONT como primer paso"
        ),
    )
    assert r.get("motivo") != "pon_verde_enlace_ok"
