"""H14 (I9): en móvil/Sensa/TV una escalada del LLM o heurística no se autoriza con pasos del playbook sin PREGUNTAR."""

from __future__ import annotations

import json

import pytest

import app.llm
from app.domain.action_proposal import ActionProposal, evaluate_escalate
from app.domain.flujos_abonado import PasoPlaybook
from app.services import diagnostico_n1 as dn

PB = [
    PasoPlaybook("tipo_problema_llamada", "¿No podés llamar, no te entran, o se cortan?"),
    PasoPlaybook("reinicio_llamadas", "Reiniciá y probá una llamada. ¿Anduvo?"),
    PasoPlaybook("derivar_llamadas", "Si persiste, te derivo con un agente. ¿Querés?"),
]
H = [{"rol": "user", "texto": "se me cortan"}]


def _turno(monkeypatch, *, motivo="falla_de_red_los", accion="escalate", cubiertos, preguntados, foco="movil", turnos=6):
    llm = {"accion": accion, "mensaje": "Es un tema de red.", "paso_cubierto": "", "motivo": motivo}
    monkeypatch.setattr(app.llm, "chat_completion", lambda *a, **k: json.dumps(llm))
    return dn.diagnosticar_turno(
        intencion="movil_llamadas",
        checklist=PB,
        historial_mensajes=H,
        mensaje_cliente="no, solo las llamadas",
        turnos_diagnostico=turnos,
        pasos_cubiertos=cubiertos,
        contexto_abonado="",
        servicio_foco_tipo=foco,
        pasos_preguntados=preguntados,
    )


def test_escalada_del_llm_con_paso_sin_preguntar_se_demota_al_paso(monkeypatch):
    # Un solo paso restante (reinicio): la guarda vieja de «sin agotamiento» (>1 restante) lo dejaba pasar.
    r = _turno(monkeypatch, cubiertos=["tipo_problema_llamada"], preguntados=[])
    assert r["accion"] == "ask" and r["motivo"] == "bloqueado_escalate_pasos_sin_preguntar", r
    assert r["mensaje"] == PB[1].pregunta and r["paso_cubierto"] == "reinicio_llamadas"


def test_bloque_optica_fuera_de_intencion_tampoco_salta_los_pasos(monkeypatch):
    r = _turno(monkeypatch, motivo="ia_falla_los", cubiertos=["tipo_problema_llamada"], preguntados=[])
    assert r["accion"] == "ask" and "acceso interno" not in r["mensaje"], r


def test_con_el_paso_ya_preguntado_la_escalada_se_autoriza(monkeypatch):
    r = _turno(monkeypatch, cubiertos=["tipo_problema_llamada"], preguntados=["reinicio_llamadas"])
    assert r["accion"] == "escalate", r


def test_un_paso_cubierto_por_un_hecho_del_abonado_no_bloquea(monkeypatch):
    r = _turno(monkeypatch, cubiertos=["tipo_problema_llamada", "reinicio_llamadas"], preguntados=[])
    assert r["accion"] == "escalate", r


def test_un_motivo_pack_acreditado_declarado_por_el_llm_no_es_autoridad(monkeypatch):
    # Gate 13C: el motivo del JSON del LLM es un claim (se sanea a «ia_…»); la exención es solo del guardrail determinista.
    r = _turno(monkeypatch, motivo="pack_acreditado_sin_datos", cubiertos=[], preguntados=[])
    assert r["motivo"] == "bloqueado_escalate_pasos_sin_preguntar", r


def test_internet_fijo_no_cambia(monkeypatch):
    r = _turno(monkeypatch, cubiertos=["tipo_problema_llamada"], preguntados=[], foco="internet")
    assert r["motivo"] != "bloqueado_escalate_pasos_sin_preguntar", r


def test_sin_registro_de_preguntados_la_guarda_no_actua(monkeypatch):
    r = _turno(monkeypatch, cubiertos=["tipo_problema_llamada"], preguntados=None)
    assert r["motivo"] != "bloqueado_escalate_pasos_sin_preguntar", r


@pytest.mark.parametrize(
    ("source", "reason", "permite"),
    [("llm", "ia", False), ("heuristic", "bloqueado_optica_fuera_de_intencion", False), ("plant", "los_confirmada", True), ("human", "pedido_humano", True), ("llm", "pack_acreditado_sin_datos", True)],
)
def test_politica_evaluate_escalate_con_pasos_sin_preguntar(source, reason, permite):
    d = evaluate_escalate(
        ActionProposal(action="escalate", source=source, reason=reason, message="x"),
        "no, solo las llamadas",
        turnos_diagnostico=9,
        intencion="movil_llamadas",
        pasos_sin_preguntar=["reinicio_llamadas"],
    )
    assert d.allow is permite, d
    if not permite:
        assert d.reason == "bloqueado_escalate_pasos_sin_preguntar"
