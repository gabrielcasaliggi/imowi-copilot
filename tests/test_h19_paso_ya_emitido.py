"""H19 (I10): sin pending_bot y tras una respuesta lateral (potencia…), el diagnóstico no re-emite un paso de los últimos 6 turnos."""

from __future__ import annotations

from app.domain.flujos_abonado import PasoPlaybook
from app.services.canal_diagnostico_ia import _avanzar_fallback_por_respuesta

P1 = PasoPlaybook("p1", "Primer paso del playbook. ¿Lo hiciste?")
P2 = PasoPlaybook("p2", "Segundo paso del playbook. ¿Mejoró?")
P3 = PasoPlaybook("p3", "Tercer paso del playbook. ¿Probaste?")
DERIV = PasoPlaybook("derivar_x", "Si persiste te derivo con un agente. ¿Querés?")
LATERAL = "No puedo ver la potencia de tu fibra desde el chat. ¿Querés que te derive con un agente?"


def _bot(txt):
    return {"rol": "bot", "texto": txt}


def _cli(txt):
    return {"rol": "in", "texto": txt}


def _res(p, motivo="fallback_playbook", paso=None):
    return {"accion": "ask", "mensaje": p.pregunta, "paso_cubierto": p.id if paso is None else paso, "motivo": motivo}


def _avanzar(checklist, result, historial, cubiertos=(), ultimo_bot=LATERAL):
    return _avanzar_fallback_por_respuesta(
        {}, checklist, "ok me anda lento en un dispositivo", result, list(cubiertos), ultimo_bot=ultimo_bot, historial=historial
    )


def test_paso_ya_emitido_tras_respuesta_lateral_avanza_al_siguiente():
    h = [_bot(P1.pregunta), _cli("me anda lento"), _bot(LATERAL), _cli("ok")]
    r = _avanzar([P1, P2, P3], _res(P1), h)
    assert r["paso_cubierto"] == "p2" and r["mensaje"] == P2.pregunta


def test_camino_llm_vivo_con_paso_cubierto_vacio_tambien_avanza():
    h = [_bot(P1.pregunta), _bot(LATERAL)]
    r = _avanzar([P1, P2], _res(P1, motivo="ia", paso=""), h)
    assert r["mensaje"] == P2.pregunta


def test_paso_emitido_hace_mas_de_6_turnos_puede_re_emitirse():
    h = [_bot(P1.pregunta)] + [_bot(f"relleno {i}") for i in range(6)]
    r = _avanzar([P1, P2], _res(P1), h)
    assert r["mensaje"] == P1.pregunta


def test_si_el_ultimo_mensaje_del_bot_era_el_paso_es_una_repregunta_y_no_se_toca():
    h = [_bot(P1.pregunta)]
    r = _avanzar([P1, P2], _res(P1), h, ultimo_bot=P1.pregunta)
    assert r["mensaje"] == P1.pregunta


def test_paso_de_derivacion_no_se_salta():
    h = [_bot(DERIV.pregunta), _bot(LATERAL)]
    r = _avanzar([P1, DERIV], _res(DERIV), h)
    assert r["mensaje"] == DERIV.pregunta


def test_paso_que_no_salio_no_se_toca():
    r = _avanzar([P1, P2], _res(P1), [_bot(LATERAL)])
    assert r["mensaje"] == P1.pregunta


def test_borde_el_paso_saltado_es_el_ultimo_de_la_lista():
    h = [_bot(P2.pregunta), _bot(LATERAL)]
    r = _avanzar([P1, P2], _res(P2), h, cubiertos=["p1"])
    assert r["accion"] == "escalate"


def test_checklist_agotado_escala_con_pregunta_y_sin_derivar_sin_confirmacion():
    h = [_bot(P1.pregunta), _bot(P2.pregunta), _bot(LATERAL)]
    r = _avanzar([P1, P2], _res(P1), h)
    assert r["accion"] == "escalate" and r["motivo"] == "fallback_checklist_agotado"
    assert r["mensaje"].rstrip().endswith("?")  # I7
    assert "¿Querés que te derive" in r["mensaje"]  # R1: ofrece, no deriva solo


def test_la_funcion_no_muta_el_ctx():
    ctx: dict = {}
    _avanzar_fallback_por_respuesta(ctx, [P1, P2], "ok", _res(P1), [], ultimo_bot=LATERAL, historial=[_bot(P1.pregunta), _bot(LATERAL)])
    assert ctx == {}
