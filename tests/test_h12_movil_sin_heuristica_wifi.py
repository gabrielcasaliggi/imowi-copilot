"""H12: una conversación de servicio móvil no se clasifica como diagnóstico Wi-Fi (evidencia de prod)."""

from __future__ import annotations

import json

import pytest

import app.llm
from app.domain.flujos_abonado import PLAYBOOKS, contexto_diagnostico_wifi
from app.services import diagnostico_n1 as dn

HISTORIAL_MOVIL = [
    {"rol": "bot", "texto": "Dale, vamos con el servicio de telefonía móvil. ¿Qué te pasa: sin señal, sin datos o no podés llamar?"},
    {"rol": "user", "texto": "tecnico, no puedo hacer llamadas"},
    {"rol": "bot", "texto": "¿Te pasa lo mismo con los mensajes de texto (SMS)?"},
]
FIJO = ("wi-fi", "wifi", "router", "equipos", "fibra", "acceso a la red")

@pytest.mark.parametrize("intencion", ["movil", "movil_llamadas", "movil_datos"])
def test_h12_conversacion_movil_no_es_contexto_wifi(intencion):
    assert contexto_diagnostico_wifi(HISTORIAL_MOVIL, intencion=intencion) is False


def test_h12_pregunta_de_acceso_fijo_del_llm_en_movil_no_se_reescribe_como_wifi(monkeypatch):
    llm = {"accion": "ask", "mensaje": "¿Es fibra, antena o línea telefónica? ¿Ves una cajita blanca?", "paso_cubierto": "", "motivo": "ia"}
    monkeypatch.setattr(app.llm, "chat_completion", lambda *a, **k: json.dumps(llm))
    r = dn.diagnosticar_turno(
        intencion="movil_llamadas",
        checklist=PLAYBOOKS["movil_llamadas"],
        historial_mensajes=HISTORIAL_MOVIL,
        mensaje_cliente="no",
        turnos_diagnostico=3,
        pasos_cubiertos=[],
        contexto_abonado="",
    )
    assert not any(k in r["mensaje"].lower() for k in FIJO), r


def test_h12e_forzar_confirmacion_derivacion():
    from app.domain.flujos_abonado import forzar_confirmacion_derivacion
    from app.services.eko_action_bridge import MSG_CONFIRMAR_DERIVACION

    out = forzar_confirmacion_derivacion(
        "¿El problema es en una sola zona o en varias ubicaciones? Si pasa en todos lados, hay que revisar la línea. Te paso con un agente."
    )
    assert out and out.endswith(MSG_CONFIRMAR_DERIVACION) and "Te paso con un agente" not in out and out.endswith("?")
    assert forzar_confirmacion_derivacion("Si persiste, te derivo con un agente. ¿Querés?") is None  # ya pregunta
    assert forzar_confirmacion_derivacion("Reiniciá y probá una llamada. ¿Anduvo?") is None  # no ofrece derivar
    assert forzar_confirmacion_derivacion("Modo avión 15 segundos y volvé a probar.") is None


def test_h14_log_de_la_plantilla_acceso_interno(monkeypatch, caplog):
    """Un escalate del LLM con motivo «óptico» en un servicio móvil emite la plantilla y deja un log INFO sin PII."""
    import logging

    llm = {"accion": "escalate", "mensaje": "Es un tema de red.", "paso_cubierto": "", "motivo": "falla_de_red_los"}
    monkeypatch.setattr(app.llm, "chat_completion", lambda *a, **k: json.dumps(llm))
    with caplog.at_level(logging.INFO, logger="operations_hub"):
        r = dn.diagnosticar_turno(
            intencion="movil_llamadas",
            checklist=PLAYBOOKS["movil_llamadas"][:1],
            historial_mensajes=HISTORIAL_MOVIL,
            mensaje_cliente="no, solo las llamadas",
            turnos_diagnostico=6,
            pasos_cubiertos=[],
            contexto_abonado="",
            servicio_foco_tipo="movil",
        )
    assert "acceso interno" in r["mensaje"]
    logs = [m for m in caplog.messages if m.startswith("diag_plantilla_fuera_de_intencion")]
    assert logs and "plantilla=acceso_interno" in logs[0] and "servicio_foco=movil" in logs[0] and "fuente=" in logs[0], caplog.messages
