"""Tests de voz Eco + contexto abonado + historial chat."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.diagnostico_n1 import MIN_TURNOS_ANTES_ESCALAR
from app.services.eco_voice import (
    TEMPERATURE_N1,
    build_contexto_abonado,
    enrich_contexto_desde_integraciones,
    historial_canal_a_mensajes_chat,
    system_prompt_eco_n1,
)


def test_parametros_n1_basicos():
    assert TEMPERATURE_N1 == 0.4
    assert MIN_TURNOS_ANTES_ESCALAR == 4


def test_contexto_abonado_invitado():
    txt = build_contexto_abonado(None)
    assert "invitado" in txt.lower()
    assert "integrar NMS" in txt
    assert "integrar Fiserv" in txt


def test_contexto_abonado_identificado():
    abo = SimpleNamespace(
        nombre="María Pérez",
        dni="30111222",
        servicio="internet",
        plan="100Mb",
        estado="activo",
        deuda_monto="0",
        linea_msisdn="2235551234",
    )
    txt = build_contexto_abonado(abo)
    assert "identificado" in txt
    assert "María Pérez" in txt
    assert "30***222" in txt or "***" in txt
    assert "100Mb" in txt
    # Placeholders listos para conectar APIs
    assert "ont_estado" in txt
    assert "pago_qr_reciente" in txt


def test_enrich_hook_vacio_hasta_integracion():
    empty = enrich_contexto_desde_integraciones(None)
    assert empty["ont_estado"] == ""
    assert empty["pago_qr_reciente"] == ""


def test_historial_a_chat_roles():
    hist = [
        {"autor": "cliente", "texto": "no anda internet"},
        {"autor": "bot", "texto": "¿Reiniciaste el router?"},
        {"autor": "cliente", "texto": "sí y sigue igual"},
    ]
    msgs = historial_canal_a_mensajes_chat(hist, max_msgs=14)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert "internet" in msgs[0]["content"]


def test_system_prompt_incluye_empatia_y_json():
    p = system_prompt_eco_n1(
        intencion="wifi",
        turnos=1,
        min_turnos_antes_escalar=4,
        contexto_abonado="CONTEXTO_ABONADO:\n- modo: invitado",
    )
    assert "frustrado" in p.lower() or "frustración" in p.lower() or "frustr" in p.lower()
    assert "JSON" in p
    assert "escalate" in p
    assert "CONTEXTO_ABONADO" in p
    assert "turno 2" in p
