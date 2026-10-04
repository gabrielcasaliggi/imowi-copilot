"""EKO A — la intención explícita gana sobre la que dejó un journey en el menú.

Sin .env reales ni servicios externos: LLM, BillTrack y catálogo mockeados.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import app.config as app_config
import app.services.eko_action_bridge as bridge
from app.domain.conversation_state import CS_KEY, KIND_TECNICO
from app.domain.domain_lifecycle import create_domain, new_conversation_state
from app.estate import canal_repo as crepo
from app.estate.database import get_session_factory
from app.estate.models import Abonado, ConversacionCanal, Organization
from app.services import canal_abonado as c
from app.services.canal_abonado import _intencion_tras_lifecycle

_NOOP = SimpleNamespace(changed=False)
_CAMBIO = SimpleNamespace(changed=True)


def _ctx_con_playbook_activo(playbook: str, intencion: str) -> dict:
    cs = new_conversation_state(turn=2)
    create_domain(cs, kind=KIND_TECNICO, playbook=playbook)
    return {CS_KEY: cs.to_dict(), "intencion": intencion}


# --------------------------------------------------------------------------- unitarios
@pytest.mark.parametrize("previa", ["consulta_servicios", "facturacion", "estado_ticket"])
def test_explicita_tecnica_gana_sobre_resto_de_journey(previa):
    assert _intencion_tras_lifecycle({"intencion": previa}, "movil_llamadas", _NOOP) == "movil_llamadas"
    assert _intencion_tras_lifecycle({"intencion": previa}, "internet_lento", None) == "internet_lento"


def test_playbook_de_journey_en_el_dominio_no_cuenta_como_diagnostico_activo():
    ctx = _ctx_con_playbook_activo("consulta_servicios", "consulta_servicios")
    assert _intencion_tras_lifecycle(ctx, "movil_llamadas", _NOOP) == "movil_llamadas"


@pytest.mark.parametrize("explicita", ["general", "", "facturacion_pago", "aviso_deuda"])
def test_explicita_generica_o_no_tecnica_no_pisa(explicita):
    assert _intencion_tras_lifecycle({"intencion": "consulta_servicios"}, explicita, _NOOP) == "consulta_servicios"


def test_diagnostico_activo_no_se_pisa():
    # ctx.intencion de un diagnóstico (no de journey): sigue ganando
    assert _intencion_tras_lifecycle({"intencion": "internet_ftth"}, "movil_llamadas", _NOOP) == "internet_ftth"
    # resto de journey, pero el dominio tiene un playbook de diagnóstico activo
    ctx = _ctx_con_playbook_activo("internet_ftth", "consulta_servicios")
    assert _intencion_tras_lifecycle(ctx, "movil_llamadas", _NOOP) == "consulta_servicios"


def test_si_el_lifecycle_cambio_algo_gana_la_proyeccion():
    assert _intencion_tras_lifecycle({"intencion": "consulta_servicios"}, "movil_llamadas", _CAMBIO) == "consulta_servicios"


def test_sin_intencion_previa_usa_la_explicita():
    assert _intencion_tras_lifecycle({}, "movil_datos", _NOOP) == "movil_datos"


# --------------------------------------------------------------------------- end to end
_TEL = "5492235557002"
_CAT = [
    {"id": f"m{i}", "login": f"223555000{i}", "type": "movil", "label": n, "product": n, "active": True,
     "line_msisdn": f"223555000{i}"}
    for i, n in enumerate(["Imowi 5 GB", "Imowi 3 GB", "Imowi 3 GB", "Imowi 1.5 GB"], start=1)
]


@pytest.fixture
def chat(monkeypatch):
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ENABLED", True)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(
        bridge, "ACTION_RUNTIME_ACTIONS",
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
        crepo.set_contexto(conv, {"identificado": True, "dni": "30111222"})
        db.commit()
        org_id, conv_id = org.id, conv.id

    def _llm_caido(*_a, **_k):
        raise HTTPException(status_code=503, detail="LLM no disponible")

    def say(texto: str):
        sent: list[str] = []
        with Session() as db, \
            patch("app.services.canal_abonado._enviar_respuesta", lambda _d, _o, _c, resp, **k: sent.append(resp)), \
            patch("app.services.portal_services.catalog_for_selection", lambda _db, abonado: {"status": "ok", "services": _CAT}), \
            patch("app.llm.chat_completion", _llm_caido), \
            patch("app.services.eko_journeys._login_count", return_value=0), \
            patch("app.services.eko_context.internet_logins_count", return_value=0), \
            patch("app.services.eko_context.servicio_agregado", return_value="movil"), \
            patch("app.services.billtrack.lookup_servicios_cuenta_por_dni", lambda **k: ([], True)), \
            patch("app.services.billtrack.lookup_servicios_conectividad", lambda **k: []), \
            patch("app.services.billtrack.lookup_servicios_conectividad_por_dni", lambda **k: []), \
            patch("app.services.handoff_notify.notify_espera_agente", return_value=0):
            c.procesar_mensaje_entrante(db, org_id, telefono=_TEL, texto=texto, canal="whatsapp", wa_id=_TEL, usar_llama=True)
            cv = db.get(ConversacionCanal, conv_id)
            return sent, crepo.get_contexto(cv), cv.ticket_id or ""

    yield say

    with Session() as db:
        db.get(ConversacionCanal, conv_id).estado = "cerrado"
        db.commit()


def test_movil_elegido_y_luego_llamadas_responde_playbook_movil(chat):
    say = chat
    say("hola")  # deja menu_paso=servicio
    say("tengo problemas con mi linea de imowi")  # menú de selección (journey)
    say("1")  # selecciona
    sent, ctx, ticket = say("no puedo hacer llamadas")
    assert len(sent) == 1 and sent[0].strip()
    assert "En qué te ayudo" not in sent[0], "no debe ser el saludo genérico"
    assert ctx.get("intencion") == "movil_llamadas"
    assert ticket == ""


def test_menu_sin_journey_previo_no_cambia(chat):
    say = chat
    say("hola")
    sent, ctx, _t = say("no puedo hacer llamadas")
    assert len(sent) == 1 and "En qué te ayudo" not in sent[0]
    assert ctx.get("intencion") == "movil_llamadas"
