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
