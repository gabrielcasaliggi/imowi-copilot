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


def test_doble_tema_y_prioridad():
    from app.domain.flujos_abonado import (
        detectar_temas_duales,
        pide_humano,
        resolver_prioridad_tema,
    )

    msg = "hola internet anda cada vez peor y encima me vino aumento en la fatura"
    assert set(detectar_temas_duales(msg)) == {"tecnico", "facturacion"}
    assert resolver_prioridad_tema("por el internet") == "tecnico"
    assert resolver_prioridad_tema("el aumento") == "facturacion"
    assert pide_humano("que me atiendan ya") is True
    assert pide_humano("quiero un asesor") is True


def test_bloquea_handoff_y_pago_prematuro(monkeypatch):
    import json

    from app.services.diagnostico_n1 import diagnosticar_turno

    def _fake(*_a, **_k):
        return json.dumps(
            {
                "accion": "ask",
                "mensaje": (
                    "¿Te gustaría que un asesor te contacte por este medio "
                    "o preferís que te llamen?"
                ),
                "paso_cubierto": "x",
                "motivo": "ia",
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("app.llm.chat_completion", _fake)
    out = diagnosticar_turno(
        intencion="facturacion",
        checklist=[
            {"id": "identificar_cuenta", "pregunta": "¿Me pasás el DNI?"},
            {"id": "detalle_importe", "pregunta": "¿Qué monto ves?"},
        ],
        historial_mensajes=[],
        mensaje_cliente="la de este mes y son 5000 pesos mas",
        turnos_diagnostico=2,
        pasos_cubiertos=["triaje_motivo", "detalle_importe"],
    )
    assert out["accion"] == "ask"
    assert out["motivo"] == "bloqueado_handoff_prematuro"
    assert "asesor" not in (out.get("mensaje") or "").lower()
    assert "dni" in (out.get("mensaje") or "").lower() or "socio" in (out.get("mensaje") or "").lower()

    def _fake_pago(*_a, **_k):
        return json.dumps(
            {
                "accion": "ask",
                "mensaje": "¿Qué medio de pago utilizó y en qué fecha realizó el movimiento?",
                "paso_cubierto": "x",
                "motivo": "ia",
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("app.llm.chat_completion", _fake_pago)
    out2 = diagnosticar_turno(
        intencion="facturacion",
        checklist=[{"id": "identificar_cuenta", "pregunta": "¿DNI?"}],
        historial_mensajes=[],
        mensaje_cliente="que me atiendan ya",
        turnos_diagnostico=3,
        pasos_cubiertos=[],
        forzar_agente=True,
    )
    assert out2["accion"] == "escalate"
    assert out2["motivo"] == "pedido_humano"
