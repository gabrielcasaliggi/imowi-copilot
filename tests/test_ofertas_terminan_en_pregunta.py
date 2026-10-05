"""Tanda 6 F2: toda oferta que deja una confirmación pendiente (derivar, ticket) termina con una pregunta explícita."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.domain.flujos_abonado import PLAYBOOKS, es_paso_derivacion, texto_ofrece_derivacion
from app.services.eko_action_bridge import MSG_CONFIRMAR_DERIVACION, confirmation_prompt_for


def test_todos_los_pasos_de_derivacion_de_los_playbooks_terminan_en_pregunta():
    pasos = [(n, p) for n, ps in PLAYBOOKS.items() for p in ps if es_paso_derivacion(p)]
    assert len(pasos) >= 20
    malos = [(n, p.id, p.pregunta[-60:]) for n, p in pasos if not p.pregunta.strip().endswith("?")]
    assert not malos, malos


@pytest.mark.parametrize("accion", ["create_ticket", "escalate_human", "close_conversation", "otra"])
def test_los_prompts_de_confirmacion_del_runtime_terminan_en_pregunta(accion):
    assert confirmation_prompt_for(accion).strip().endswith("?")


def test_la_confirmacion_de_derivacion_es_una_pregunta_y_se_reconoce_como_oferta():
    assert MSG_CONFIRMAR_DERIVACION.endswith("?")
    assert texto_ofrece_derivacion(MSG_CONFIRMAR_DERIVACION)


def _escalada_fuera_de_intencion(intencion: str, mensaje_cliente: str) -> dict:
    from app.domain.flujos_abonado import PLAYBOOKS as PB
    from app.services.diagnostico_n1 import diagnosticar_turno

    falsa = json.dumps(
        {"accion": "escalate", "mensaje": "Revisá la luz LOS de la ONT.", "paso_cubierto": "", "motivo": "fibra_danada"}
    )
    with patch("app.llm.chat_completion", lambda *a, **k: falsa):
        return diagnosticar_turno(
            intencion=intencion,
            checklist=PB.get(intencion) or PB["general"],
            historial_mensajes=[],
            mensaje_cliente=mensaje_cliente,
            turnos_diagnostico=6,
            pasos_cubiertos=[p.id for p in (PB.get(intencion) or PB["general"]) if not es_paso_derivacion(p)],
            kb_fragmento="",
            forzar_agente=False,
            contexto_abonado="",
        )


@pytest.mark.parametrize(
    "intencion,mensaje_cliente",
    [("movil", "no tengo señal"), ("tv_sensa", "la tele de sensa me dice error de usuario y cuenta")],
)
def test_la_escalada_fuera_de_intencion_se_redacta_como_oferta(intencion, mensaje_cliente):
    r = _escalada_fuera_de_intencion(intencion, mensaje_cliente)
    assert r["accion"] == "escalate" and r["motivo"] == "bloqueado_optica_fuera_de_intencion", r
    assert r["mensaje"].strip().endswith("?"), r["mensaje"]
    assert "te derivo y le paso" not in r["mensaje"].lower()
