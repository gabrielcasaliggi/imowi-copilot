"""H31 — la clave Wi‑Fi que el abonado escribe en el chat no se persiste ni se muestra a agentes.

Turnos reales de ``procesar_mensaje_entrante`` (journeys ON, Action Runtime con ``create_ticket``, LLM caído),
destino BCM y write mockeados. Sin .env reales ni red. Claves de prueba inventadas.
"""

from __future__ import annotations

import contextlib
import json
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import app.config as app_config
import app.services.eko_action_bridge as bridge
from app.estate import canal_repo as crepo
from app.estate.database import get_session_factory
from app.estate.models import Abonado, ConversacionCanal, Organization, Ticket
from app.radius.contract import ServicioConectividad
from app.services import canal_abonado as c
from app.services import wifi_bcm as wb

_FIBRA = ServicioConectividad(
    login="lemuramatiBAI", service_type_code="INTFO", service_type_label="ACCESO INTERNET FIBRA OPTICA",
    product="Internet acceso Fo Hogar 100MB", locality="", service_on=True,
)


def _flujo(
    script: list[str], *, entrada_audio: bool = False, canal: str = "whatsapp", bcm_ok: bool = True
) -> dict[str, Any]:
    """Corre ``script`` y devuelve respuestas, valores que llegaron a BCM, mensajes y contexto persistidos.

    ``bcm_ok=False``: el write BCM falla en ambas bandas (el bot ofrece derivar).
    """
    wb.clear_wifi_ephemeral_for_tests()
    uid = uuid.uuid4().int
    tel = f"549223{uid % 10_000_000:07d}"
    dni = f"9{(uid >> 20) % 10_000_000:07d}"
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        abo = Abonado(organizacion_id=org.id, dni=dni, nombre="María Pérez", servicio="internet",
                      deuda_monto="0", client_number=str(uid % 10_000_000), plan="Fibra 100")
        db.add(abo)
        db.commit()
        conv = crepo.get_or_create_conversacion(db, org.id, telefono=tel, canal=canal, wa_id=tel)
        conv.estado, conv.abonado_id = "bot", abo.id
        crepo.set_contexto(conv, {"identificado": True, "dni": dni})
        db.commit()
        org_id, conv_id, abo_id = org.id, conv.id, abo.id

    bcm: list[str] = []
    turnos: list[dict[str, Any]] = []

    def _aplicar(_db, _dest, password):
        bcm.append(password)
        return ("ok", "", []) if bcm_ok else ("fail", "timeout", ["2.4 GHz", "5 GHz"])

    def _down(*_a, **_k):
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="LLM no disponible")

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(app_config, "EKO_JOURNEYS_ENABLED", True))
        stack.enter_context(patch.object(app_config, "EKO_JOURNEYS_CHANNELS", frozenset()))
        stack.enter_context(patch.object(app_config, "EKO_JOURNEYS_ORG_IDS", frozenset()))
        stack.enter_context(patch.object(bridge, "ACTION_RUNTIME_ENABLED", True))
        stack.enter_context(patch.object(bridge, "ACTION_RUNTIME_ACTIONS", frozenset({"create_ticket"})))
        stack.enter_context(patch("app.llm.chat_completion", _down))
        stack.enter_context(patch("app.services.billtrack.lookup_servicios_conectividad", lambda **k: [_FIBRA]))
        stack.enter_context(patch("app.services.billtrack.lookup_servicios_conectividad_por_dni", lambda **k: [_FIBRA]))
        stack.enter_context(patch("app.services.billtrack.lookup_servicios_cuenta_por_dni", lambda **k: ([], True)))
        stack.enter_context(patch("app.services.handoff_notify.notify_espera_agente", lambda *a, **k: 0))
        stack.enter_context(patch.object(
            wb, "_destino_autorizado", lambda *_a, **_k: (wb.DestinoWifiBcm("serial", "SNTEST0001"), "", "")
        ))
        stack.enter_context(patch.object(wb, "_servicios_abonado", lambda *_a, **_k: []))
        stack.enter_context(patch.object(wb, "_aplicar_password", _aplicar))
        for texto in script:
            enviados: list[str] = []
            real = c._enviar_respuesta

            def _enviar(_d, _o, _c, resp, *, _out=enviados, _real=real, **_k):
                _real(_d, _o, _c, resp, enviar_externo=False)
                _out.append(resp)

            with Session() as db, patch.object(c, "_enviar_respuesta", _enviar):
                out = c.procesar_mensaje_entrante(
                    db, org_id, telefono=tel, texto=texto, canal=canal, wa_id=tel,
                    usar_llama=True, entrada_audio=entrada_audio,
                ) or {}
                cv = db.get(ConversacionCanal, conv_id)
                turnos.append({
                    "user": texto, "replies": enviados, "respuesta": out.get("respuesta") or "",
                    "fase": crepo.get_contexto(cv).get("wifi_bcm_fase"),
                    "contexto_json": cv.contexto_json or "", "estado": cv.estado, "ticket_id": cv.ticket_id or "",
                })

    with Session() as db:
        cv = db.get(ConversacionCanal, conv_id)
        mensajes = [(m.autor, m.texto) for m in crepo.list_mensajes(db, conv_id)]
        ctx_json = cv.contexto_json or ""
        tk = db.get(Ticket, cv.ticket_id) if cv.ticket_id else None
        ticket = {k: getattr(tk, k) or "" for k in ("evidencia", "descripcion_falla", "acciones_n1_realizadas")} if tk else {}
    return SimpleNamespace(
        turnos=turnos, bcm=bcm, mensajes=mensajes, contexto_json=ctx_json, ticket=ticket,
        org_id=org_id, conv_id=conv_id, abo_id=abo_id, telefono=tel,
    ).__dict__



# --------------------------------------------------------------------------- H31
_MARCADOR = "••••••"
_CLAVE = "ClaveSegura99"  # la normalización léxica no la altera
_PEDIDO = "quiero cambiar la clave del wifi"
# (canal, entrada_audio): texto de WhatsApp, nota de voz de WhatsApp y audio del portal/app.
_ENTRADAS = [("whatsapp", False), ("whatsapp", True), ("web", True)]


def _entrantes(r: dict[str, Any]) -> list[str]:
    return [t for autor, t in r["mensajes"] if autor == "cliente"]


@pytest.mark.xfail(strict=True, reason="H31: la clave Wi‑Fi se guarda en claro en mensajes_canal")
@pytest.mark.parametrize(("canal", "audio"), _ENTRADAS)
def test_a_mensaje_de_la_clave_guardado_enmascarado(canal, audio):
    r = _flujo([_PEDIDO, _CLAVE], canal=canal, entrada_audio=audio)
    assert r["turnos"][1]["fase"] == "confirmar_clave"
    assert _entrantes(r) == [_PEDIDO, _MARCADOR]
    assert all(_CLAVE not in t for _a, t in r["mensajes"])


@pytest.mark.xfail(strict=True, reason="H31: comprension_turno y mensaje_original guardan la clave en claro")
@pytest.mark.parametrize("clave", [_CLAVE, "Mi  Clave  99"])  # la segunda deja mensaje_original (la normalización la cambia)
def test_b_comprension_turno_enmascarada(clave):
    r = _flujo([_PEDIDO, clave])
    ctx = json.loads(r["turnos"][1]["contexto_json"])
    comp = ctx["comprension_turno"]
    assert comp["texto_original"] == _MARCADOR
    assert comp["texto_para_reglas"] == _MARCADOR
    if clave != _CLAVE:
        assert ctx["mensaje_original"] == _MARCADOR
    assert clave not in r["turnos"][1]["contexto_json"]


@pytest.mark.xfail(strict=True, reason="H31: la API de Bandeja devuelve la clave en mensajes, vista previa y contexto")
def test_c_bandeja_no_devuelve_la_clave():
    from main import app

    r = _flujo([_PEDIDO, _CLAVE])
    client = TestClient(app)
    login = client.post("/api/login", json={"usuario": "batan", "password": "batan"})
    headers = {"Authorization": f"Bearer {login.json()['token']}"}
    detalle = client.get(f"/api/v1/inbox/conversations/{r['conv_id']}", headers=headers)
    assert detalle.status_code == 200
    cuerpo = detalle.json()
    assert _CLAVE not in json.dumps(cuerpo["mensajes"], ensure_ascii=False)
    assert _CLAVE not in json.dumps(cuerpo["conversacion"]["contexto"], ensure_ascii=False)
    assert _MARCADOR in [m["texto"] for m in cuerpo["mensajes"]]
    listado = client.get("/api/v1/inbox/conversations", headers=headers)
    assert listado.status_code == 200
    assert _CLAVE not in listado.text
    # Vista previa si el último mensaje fuera el de la clave (p. ej. el bot todavía no respondió).
    with get_session_factory()() as db:
        cv = db.get(ConversacionCanal, r["conv_id"])
        msg_clave = [m for m in crepo.list_mensajes(db, cv.id) if m.direccion == "in"][1]
        assert crepo.conversacion_to_dict(cv, ultimo=msg_clave)["ultimo_mensaje_texto"] == _MARCADOR


@pytest.mark.xfail(strict=True, reason="H31: la evidencia del ticket derivado lleva la clave en claro")
def test_d_ticket_derivado_y_respuestas_del_bot_sin_la_clave():
    r = _flujo([_PEDIDO, _CLAVE, "sí", "sí"], bcm_ok=False)
    assert r["bcm"] == [_CLAVE]
    assert r["turnos"][-1]["estado"] == "espera_agente" and r["turnos"][-1]["ticket_id"]
    assert r["ticket"]["evidencia"]
    for campo, valor in r["ticket"].items():
        assert _CLAVE not in valor, campo
    for t in r["turnos"]:
        assert all(_CLAVE not in resp for resp in t["replies"] + [t["respuesta"]])


@pytest.mark.parametrize(("canal", "audio"), _ENTRADAS)
@pytest.mark.parametrize("clave", [_CLAVE, "Mi  Clave  99"])
def test_e_bcm_recibe_la_clave_real_exacta(canal, audio, clave):
    """Guarda (no xfail: ya pasa): enmascarar lo persistido no puede cambiar lo que recibe BCM."""
    r = _flujo([_PEDIDO, clave, "sí"], canal=canal, entrada_audio=audio)
    assert [t["fase"] for t in r["turnos"]] == ["pedir_clave", "confirmar_clave", "hecho"]
    assert r["bcm"] == [clave]


@pytest.mark.xfail(strict=True, reason="H31: la clave reescrita en confirmar_clave se guarda en claro")
def test_f_confirmar_clave_con_la_clave_reescrita():
    r = _flujo([_PEDIDO, _CLAVE, _CLAVE, "sí"])
    assert [t["fase"] for t in r["turnos"]] == ["pedir_clave", "confirmar_clave", "confirmar_clave", "hecho"]
    assert _entrantes(r) == [_PEDIDO, _MARCADOR, _MARCADOR, "sí"]
    assert _CLAVE not in r["turnos"][2]["contexto_json"]
    assert r["bcm"] == [_CLAVE]


def test_f_control_confirmar_clave_otro_texto_no_se_enmascara():
    """En confirmar_clave solo se enmascara la clave pendiente; una respuesta ambigua queda como se escribió."""
    r = _flujo([_PEDIDO, _CLAVE, "tal vez", "sí"])
    assert _entrantes(r)[2:] == ["tal vez", "sí"]
    assert r["bcm"] == [_CLAVE]


@pytest.mark.xfail(strict=True, reason="H31: contexto_json persiste la clave (comprension_turno)")
def test_g_contexto_json_nunca_contiene_la_clave():
    r = _flujo([_PEDIDO, _CLAVE, "sí"])
    assert r["bcm"] == [_CLAVE]
    for t in r["turnos"]:
        assert _CLAVE not in t["contexto_json"], t["user"]


def test_control_resto_de_los_turnos_sin_enmascarar():
    r = _flujo([_PEDIDO, _CLAVE, "sí"])
    entrantes = _entrantes(r)
    assert entrantes[0] == _PEDIDO and entrantes[2] == "sí"
