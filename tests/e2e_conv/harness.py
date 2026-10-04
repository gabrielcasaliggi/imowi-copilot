"""Harness e2e conversacional: turnos reales de ``procesar_mensaje_entrante``.

Configura como producción (journeys ON, Action Runtime solo con ``create_ticket``) y mockea
LLM, BillTrack y fuentes de planta. Sin .env reales ni red. No toca código de producto.
"""

from __future__ import annotations

import contextlib
import json
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import select

import app.config as app_config
import app.services.eko_action_bridge as bridge
from app.estate import canal_repo as crepo
from app.estate import repository as repo
from app.estate.database import get_session_factory
from app.estate.models import Abonado, ConversacionCanal, NetworkOutage, Organization, Ticket
from app.radius.contract import ServicioConectividad
from app.services import canal_abonado as c


# --------------------------------------------------------------------------- perfiles
def _sc(login: str) -> ServicioConectividad:
    return ServicioConectividad(
        login=login, service_type_code="INTBA", service_type_label="ACCESO INTERNET INALAMBRICO",
        product="Internet Fibra 100", locality="", service_on=True,
    )


def _internet_rows(logins: list[str]) -> list[dict]:
    return [
        {"id": f"int{i}", "login": lg, "type": "internet", "label": f"Internet {lg}",
         "product": f"Internet {lg}", "active": True}
        for i, lg in enumerate(logins, 1)
    ]


MOVILES = [
    {"id": f"m{i}", "login": f"223555000{i}", "type": "movil", "label": n, "product": n, "active": True,
     "line_msisdn": f"223555000{i}"}
    for i, n in enumerate(["Imowi 5 GB", "Imowi 3 GB", "Imowi 3 GB", "Imowi 1.5 GB"], 1)
]
TV = [{"id": "tv1", "login": "", "type": "tv", "label": "Sensa", "product": "Sensa TV", "active": True}]
LOGIN1 = ["lemuramatiBAI"]
LOGIN3 = ["lemuramatiBAI", "tupaciretacuidaBAI", "tupaciretaBAI"]

PROFILES: dict[str, dict[str, Any]] = {
    "int1": dict(servicio="internet", deuda="0", logins=LOGIN1, catalogo=_internet_rows(LOGIN1)),
    "multi": dict(servicio="internet", deuda="0", logins=LOGIN3, catalogo=_internet_rows(LOGIN3)),
    "deuda": dict(servicio="internet", deuda="15000.00", logins=LOGIN1, catalogo=_internet_rows(LOGIN1)),
    "movil": dict(servicio="movil", deuda="0", logins=[], catalogo=MOVILES),
    "movil_deuda": dict(servicio="movil", deuda="15000.00", logins=[], catalogo=MOVILES),
    "sensa": dict(servicio="ambos", deuda="0", logins=LOGIN1, catalogo=_internet_rows(LOGIN1) + TV),
}


# --------------------------------------------------------------------------- resultado
@dataclass
class Turn:
    user: str
    replies: list[str] = field(default_factory=list)
    estado: str = ""
    modo: str | None = None
    ticket_created: bool = False
    ticket_id: str = ""
    branch: str = ""
    journey: dict | None = None
    journey_state: dict = field(default_factory=dict)  # ctx['eko_journey'] persistido tras el turno
    error: str | None = None

    @property
    def reply(self) -> str:
        return " | ".join(r.strip() for r in self.replies if r and r.strip())


def _llm(modo: str):
    n = {"i": 0}

    def down(*_a, **_k):
        raise HTTPException(status_code=503, detail="LLM no disponible")

    def normal(*_a, **_k):
        n["i"] += 1
        msg = f"Gracias por contarme ({n['i']}). ¿Podés darme un poco más de detalle?"
        return json.dumps({"accion": "ask", "mensaje": msg, "paso_cubierto": "", "motivo": "ia"}, ensure_ascii=False)

    return down if modo == "down" else normal


def converse(
    script: list[str],
    *,
    canal: str = "whatsapp",
    profile: str = "int1",
    journeys: bool = True,
    runtime_actions: tuple[str, ...] = ("create_ticket",),
    llm: str = "down",
    ticket_abierto: bool = False,
    corte_activo: bool = False,
) -> list[Turn]:
    prof = PROFILES[profile]
    uid = uuid.uuid4().int
    tel = f"549223{uid % 10_000_000:07d}"
    dni = f"9{(uid >> 20) % 10_000_000:07d}"
    Session = get_session_factory()
    created: dict[str, Any] = {}
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        kw = dict(organizacion_id=org.id, dni=dni, nombre="María Pérez", servicio=prof["servicio"],
                  deuda_monto=prof["deuda"], client_number=str(uid % 10_000_000), plan="Fibra 100")
        abo = Abonado(**{k: v for k, v in kw.items() if hasattr(Abonado, k)})
        db.add(abo)
        db.commit()
        created["abonado"] = abo.id
        conv = crepo.get_or_create_conversacion(db, org.id, telefono=tel, canal=canal, wa_id=tel)
        conv.estado, conv.abonado_id = "bot", abo.id
        crepo.set_contexto(conv, {"identificado": True, "dni": dni})
        if ticket_abierto:
            tk = Ticket(id=f"T{uuid.uuid4().hex[:8].upper()}", organizacion_id=org.id, linea="2235551111",
                        descripcion_falla="Sin internet", estado="Abierto")
            db.add(tk)
            conv.ticket_id = tk.id
            created["ticket"] = tk.id
        if corte_activo:
            ob = repo.create_network_outage(
                db, org.id, nas_shortname="apposada", comentario="corte",
                mensaje_cliente="Detectamos una incidencia que afecta a tu zona.", eta_minutos=45,
            )
            created["outage"] = ob.id
        db.commit()
        org_id, conv_id = org.id, conv.id

    turns: list[Turn] = []
    last_journey: dict[str, Any] = {}
    import app.services.eko_journeys as ej

    orig_journey = ej.maybe_handle_journey_turn

    def spy_journey(*a, **k):
        t = orig_journey(*a, **k)
        last_journey["j"] = None if t is None else {
            "journey": t.journey, "step": t.step, "reason": t.reason_code,
            "handled": t.handled, "empty": not (t.user_message or "").strip(),
        }
        return t

    svcs = [_sc(lg) for lg in prof["logins"]]
    try:
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(app_config, "EKO_JOURNEYS_ENABLED", journeys))
            stack.enter_context(patch.object(app_config, "EKO_JOURNEYS_CHANNELS", frozenset()))
            stack.enter_context(patch.object(app_config, "EKO_JOURNEYS_ORG_IDS", frozenset()))
            stack.enter_context(patch.object(bridge, "ACTION_RUNTIME_ENABLED", True))
            stack.enter_context(patch.object(bridge, "ACTION_RUNTIME_ACTIONS", frozenset(runtime_actions)))
            stack.enter_context(patch.object(ej, "maybe_handle_journey_turn", spy_journey))
            stack.enter_context(patch("app.llm.chat_completion", _llm(llm)))
            stack.enter_context(patch("app.services.billtrack.lookup_servicios_conectividad", lambda **k: svcs))
            stack.enter_context(patch("app.services.billtrack.lookup_servicios_conectividad_por_dni", lambda **k: svcs))
            stack.enter_context(patch("app.services.billtrack.lookup_servicios_cuenta_por_dni", lambda **k: ([], True)))
            stack.enter_context(patch(
                "app.services.portal_services.catalog_for_selection",
                lambda _db, abonado: {"status": "ok", "services": prof["catalogo"]},
            ))
            stack.enter_context(patch(
                "app.services.portal_services.evaluar_servicios_portal",
                lambda _db, abonado=None, **_k: {
                    "status": "ok", "reason_code": None,
                    "services": [{k: v for k, v in r.items() if k != "login"} for r in prof["catalogo"]],
                },
            ))
            stack.enter_context(patch("app.services.handoff_notify.notify_espera_agente", lambda *a, **k: 0))
            if corte_activo:
                stack.enter_context(patch("app.services.outages.resolver_nas_abonado", lambda db, abonado: "apposada"))

            for texto in script:
                sent: list[str] = []
                frames: list[str] = []

                def _enviar(_d, _o, _c, resp, *, _sent=sent, _frames=frames, **_k):
                    _sent.append(resp)
                    if not _frames:
                        _frames.extend(
                            f"{f.filename.rsplit('/', 1)[-1]}:{f.lineno}:{f.name}"
                            for f in traceback.extract_stack()
                            if "/app/" in f.filename
                        )

                last_journey.clear()
                t = Turn(user=texto)
                with Session() as db, patch("app.services.canal_abonado._enviar_respuesta", _enviar):
                    antes = bool((db.get(ConversacionCanal, conv_id).ticket_id or "").strip())
                    try:
                        out = c.procesar_mensaje_entrante(
                            db, org_id, telefono=tel, texto=texto, canal=canal, wa_id=tel, usar_llama=True
                        ) or {}
                    except Exception as e:  # noqa: BLE001
                        out, t.error = {}, f"{type(e).__name__}: {str(e)[:120]}"
                    cv = db.get(ConversacionCanal, conv_id)
                    t.estado, t.modo = cv.estado, out.get("modo")
                    t.ticket_id = (cv.ticket_id or "").strip()
                    t.ticket_created = bool(t.ticket_id) and not antes
                    t.journey_state = dict(crepo.get_contexto(cv).get("eko_journey") or {})
                t.replies = list(sent)
                t.journey = last_journey.get("j")
                j = t.journey
                if j and j["handled"] and not j["empty"]:
                    t.branch = f"journey:{j['journey']}/{j['reason'] or j['step']}"
                elif frames:
                    t.branch = "legacy:" + ">".join(x.split(":", 2)[2] + "@" + x.split(":")[1] for x in frames[-3:])
                elif j and j["handled"]:
                    t.branch = f"journey-silencio:{j['journey']}/{j['reason']}"
                else:
                    t.branch = "sin-respuesta"
                turns.append(t)
    finally:
        with Session() as db:
            cv = db.get(ConversacionCanal, conv_id)
            if cv is not None:
                cv.estado = "cerrado"
            if created.get("outage"):
                with contextlib.suppress(Exception):
                    repo.resolve_network_outage(db, db.get(NetworkOutage, created["outage"]))
            if cv is not None:
                cv.abonado_id = ""
            for kind, model in (("abonado", Abonado), ("ticket", Ticket)):
                row = db.get(model, created[kind]) if created.get(kind) else None
                if row is not None:
                    db.delete(row)
            db.commit()
    return turns
