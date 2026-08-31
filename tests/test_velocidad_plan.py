"""Velocidad contratada BillTrack vs test del abonado."""

from __future__ import annotations

from types import SimpleNamespace

from app.domain.flujos_abonado import PLAYBOOKS
from app.services.diagnostico_n1 import diagnosticar_turno
from app.services.eco_voice import build_contexto_abonado
from app.services.velocidad_plan import (
    clasificar_vs_plan,
    evaluar_speedtest_vs_plan,
    extraer_mbps_medido,
    extraer_mbps_plan,
    plan_mbps_desde_contexto,
)


def test_parse_plan_billtrack():
    assert extraer_mbps_plan("Internet 10Mb") == 10
    assert extraer_mbps_plan("10 Mb Radio") == 10
    assert extraer_mbps_plan("Fibra 100") == 100
    assert extraer_mbps_plan("100M") == 100
    assert extraer_mbps_plan("Móvil 5GB") is None
    assert extraer_mbps_plan("Fibra Optica") is None
    assert extraer_mbps_plan("10Mbps simétrico") == 10


def test_parse_medido_10m_10mb():
    assert extraer_mbps_medido("10M") == 10
    assert extraer_mbps_medido("10Mb") == 10
    assert extraer_mbps_medido("10 mbps") == 10
    assert extraer_mbps_medido("me dio 10Mb") == 10
    assert extraer_mbps_medido("tengo varios") is None
    assert extraer_mbps_medido("26269227") is None


def test_medido_numero_suelto_si_bot_pidio_test():
    hist = [
        {"autor": "bot", "texto": "Hacé un test por cable en fast.com y decime cuánto da."},
    ]
    assert extraer_mbps_medido("10", historial=hist) == 10
    assert extraer_mbps_medido("10", historial=[]) is None


def test_10mb_vs_plan_10_es_ok():
    assert clasificar_vs_plan(10, 10) == "ok"
    assert clasificar_vs_plan(8, 10) == "ok"
    assert clasificar_vs_plan(6, 10) == "aceptable"
    assert clasificar_vs_plan(3, 10) == "bajo"


def test_contexto_plan_mbps_no_toma_el_70_del_prompt():
    ctx = (
        "CONTEXTO_ABONADO:\n"
        "- plan: Internet 10Mb\n"
        "- plan_contratado: 10 Mbps\n"
        "- plan_mbps: 10\n"
        "- Un test ≥70% de ese valor es NORMAL\n"
    )
    assert plan_mbps_desde_contexto(ctx) == 10


def test_evaluar_10mb_no_deriva():
    ctx = "- plan_mbps: 10\n- plan_contratado: 10 Mbps"
    out = evaluar_speedtest_vs_plan("10Mb", [], ctx, intencion="internet_radio")
    assert out is not None
    assert out["accion"] == "ask"
    assert out["motivo"] == "velocidad_dentro_del_plan"
    assert "10 Mb" in out["mensaje"]
    assert "técnico" not in out["mensaje"].lower()
    assert "dentro de lo esperado" in out["mensaje"]


def test_evaluar_muy_bajo_no_intercepta():
    ctx = "- plan_mbps: 100"
    assert evaluar_speedtest_vs_plan("10Mb", [], ctx, intencion="internet_lento") is None


def test_build_contexto_incluye_plan_mbps():
    abo = SimpleNamespace(
        nombre="Vanesa",
        dni="26269227",
        servicio="internet",
        plan="Internet 10Mb",
        estado="activo",
        deuda_monto="0",
        linea_msisdn="",
    )
    txt = build_contexto_abonado(
        abo,
        extras={"pppoe_producto": "Internet 10Mb", "pppoe_plan_mbps": "10"},
    )
    assert "plan_mbps: 10" in txt
    assert "plan_contratado: 10 Mbps" in txt


def test_diagnosticar_10mb_no_escala(monkeypatch):
    def _fake(*_a, **_k):
        raise AssertionError("no debería llamar al LLM: el test ya cubre el plan")

    monkeypatch.setattr("app.llm.chat_completion", _fake)
    out = diagnosticar_turno(
        intencion="internet_lento",
        checklist=PLAYBOOKS["internet_lento"],
        historial_mensajes=[
            {
                "autor": "bot",
                "texto": "¿Podrías hacer un test de velocidad desde una PC conectada por cable? "
                "Podés usar fast.com y decirme cuánto te da de bajada.",
            }
        ],
        mensaje_cliente="10Mb",
        turnos_diagnostico=5,
        pasos_cubiertos=["cuantos_dispositivos", "test_velocidad"],
        contexto_abonado="- plan_mbps: 10\n- plan_contratado: 10 Mbps",
    )
    assert out["accion"] == "ask"
    assert out["motivo"] == "velocidad_dentro_del_plan"
    assert "dentro de lo esperado" in (out.get("mensaje") or "")
