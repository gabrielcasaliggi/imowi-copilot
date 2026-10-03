"""EKO-FIX-1 — post_resolution_hold sin texto cae al Legacy N1 (no silencio).

Sin .env reales ni servicios externos: LLM, BillTrack y catálogo mockeados.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import app.config as app_config
import app.services.eko_action_bridge as bridge
from app.estate import canal_repo as crepo
from app.estate.database import get_session_factory
from app.estate.models import Abonado, ConversacionCanal, Organization
from app.services import canal_abonado as c
from app.services.canal_abonado import _journey_hold_sin_texto

_TEL = "5492235557001"
_CAT = [
    {"id": "int1", "login": "lemuramatiBAI", "type": "internet", "label": "Casa", "active": True, "product": "BAI"},
    {"id": "m1", "login": "2235551234", "type": "movil", "label": "Móvil 5GB", "active": True, "product": "IMOWI"},
]


def _turn(**kw):
    base = dict(handled=True, user_message="", reason_code=None, data={})
    base.update(kw)
    return SimpleNamespace(**base)


def test_predicado_solo_hold_sin_texto_ni_cortesia():
    assert _journey_hold_sin_texto(_turn(reason_code="post_resolution_hold"))
    assert not _journey_hold_sin_texto(
        _turn(reason_code="post_resolution_courtesy", data={"courtesy_silence": True})
    )
    assert not _journey_hold_sin_texto(
        _turn(reason_code="post_resolution_hold", data={"courtesy_silence": True})
    )
    assert not _journey_hold_sin_texto(_turn(reason_code="explicit_conversation_close"))
    assert not _journey_hold_sin_texto(_turn(reason_code="post_resolution_hold", user_message="hola"))
    assert not _journey_hold_sin_texto(_turn(reason_code=None))
    assert not _journey_hold_sin_texto(None)


@pytest.fixture
def chat(monkeypatch):
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ENABLED", True)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(
        bridge,
        "ACTION_RUNTIME_ACTIONS",
        frozenset({"run_diagnostic_pppoe", "service_list", "request_account_selection", "show_balance"}),
    )
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        abo = db.scalar(select(Abonado).where(Abonado.dni == "30111222"))
        for cv in db.scalars(select(ConversacionCanal).where(ConversacionCanal.telefono.contains(_TEL[-10:]))).all():
            cv.estado, cv.contexto_json, cv.ticket_id, cv.abonado_id = "cerrado", "{}", "", ""
        db.commit()
        conv = crepo.get_or_create_conversacion(db, org.id, telefono=_TEL, canal="whatsapp", wa_id=_TEL)
        conv.estado, conv.abonado_id = "bot", abo.id
        crepo.set_contexto(conv, {"saludo": True, "identificado": True, "dni": "30111222"})
        db.commit()
        org_id, conv_id = org.id, conv.id

    calls = {"ticket": MagicMock(), "action": MagicMock()}

    def _llm_caido(*_a, **_k):
        raise HTTPException(status_code=503, detail="LLM no disponible")

    def say(texto: str):
        sent: list[str] = []
        with Session() as db, \
            patch("app.services.canal_abonado._enviar_respuesta", lambda _d, _o, _c, resp, **k: sent.append(resp)), \
            patch("app.services.portal_services.catalog_for_selection", lambda _db, abonado: {"status": "ok", "services": _CAT}), \
            patch("app.llm.chat_completion", _llm_caido), \
            patch("app.services.eko_journeys._login_count", return_value=2), \
            patch("app.services.billtrack.lookup_servicios_cuenta_por_dni", lambda **k: ([], True)), \
            patch("app.services.billtrack.lookup_servicios_conectividad", lambda **k: []), \
            patch("app.services.billtrack.lookup_servicios_conectividad_por_dni", lambda **k: []), \
            patch("app.services.handoff_notify.notify_espera_agente", return_value=0), \
            patch("app.services.canal_abonado._crear_ticket_n2", calls["ticket"]), \
            patch("app.services.eko_action_runtime.execute_action", calls["action"]):
            out = c.procesar_mensaje_entrante(
                db, org_id, telefono=_TEL, texto=texto, canal="whatsapp", wa_id=_TEL, usar_llama=True
            )
            conv = db.get(ConversacionCanal, conv_id)
            return out, sent, conv.estado, conv.ticket_id or ""

    yield say, calls

    with Session() as db:
        cv = db.get(ConversacionCanal, conv_id)
        cv.estado = "cerrado"
        db.commit()


def _seleccionar_movil(say):
    out, sent, _e, _t = say("tengo problemas con mi línea de imowi")
    assert sent and "seleccioné" in sent[0]  # journey service_catalog → done


@pytest.mark.parametrize(
    "texto",
    ["no puedo hacer llamadas", "ya reinicié y sigue sin llamar"],
)
def test_movil_tras_seleccion_ya_no_queda_en_silencio(chat, texto):
    say, calls = chat
    _seleccionar_movil(say)
    out, sent, estado, ticket = say(texto)
    assert len(sent) == 1 and sent[0].strip(), "el abonado debe recibir un mensaje"
    assert out["respuesta"] == sent[0] or out.get("respuesta")
    assert estado == "bot" and ticket == ""


@pytest.mark.parametrize("texto", ["sigue igual", "no anda nada, quiero hablar con un agente"])
def test_otros_turnos_de_la_simulacion_siguen_respondiendo(chat, texto):
    say, calls = chat
    _seleccionar_movil(say)
    out, sent, estado, ticket = say(texto)
    assert len(sent) == 1 and sent[0].strip()
    assert ticket == "", "pedir agente exige confirmación; no hay ticket sin el «sí»"


def test_gracias_sigue_sin_respuesta(chat):
    say, _calls = chat
    _seleccionar_movil(say)
    out, sent, estado, ticket = say("gracias")
    assert sent == []
    assert out["respuesta"] == ""
    assert estado == "bot" and ticket == ""


def test_fallthrough_no_crea_ticket_ni_dispara_action(chat):
    say, calls = chat
    _seleccionar_movil(say)
    calls["ticket"].reset_mock()
    calls["action"].reset_mock()
    out, sent, _estado, ticket = say("no puedo hacer llamadas")
    assert sent and sent[0].strip()
    calls["ticket"].assert_not_called()
    calls["action"].assert_not_called()
    assert ticket == ""
