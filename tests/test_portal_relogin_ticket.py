"""H24: el re-login del portal (``login-pin`` y ``verify``) solo devuelve la conversación a «bot» si no tiene un ticket abierto ligado."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.estate import canal_repo as crepo
from app.estate import repository as repo
from app.estate.database import get_session_factory
from app.estate.models import (
    Abonado,
    ConversacionCanal,
    PortalAbonadoLink,
    PortalOtpChallenge,
    Ticket,
)
from app.estate.security import hash_dni, hash_pin, hash_token
from main import app

client = TestClient(app)
PIN, OTP = "123456", "4821"

xf_h24 = pytest.mark.xfail(strict=True, reason="H24: el re-login resetea espera_agente → bot y borra el ticket_id aunque el ticket siga abierto")


def _escenario(*, estado="espera_agente", ticket: str | None = "Abierto", agente_id: str = "", visitante: bool = False):
    """Abonado con teléfono conocido y una conversación propia (web) en ``estado``; ``ticket``: estado del ticket ligado o None."""
    uid = uuid.uuid4().int
    dni, tel = f"8{uid % 10_000_000:07d}", f"549223{(uid >> 24) % 10_000_000:07d}"
    with get_session_factory()() as db:
        org = repo.get_org_by_slug(db, "coop-batan")
        abo = Abonado(organizacion_id=org.id, dni=dni, nombre="Prueba Test", servicio="internet", telefono_e164=tel, client_number=dni)
        db.add(abo)
        conv = crepo.get_or_create_conversacion(db, org.id, telefono=tel, canal="web", wa_id=tel)
        conv.estado, conv.agente_id = estado, agente_id
        conv.abonado_id = "" if visitante else abo.id
        tid = ""
        if ticket:
            tid = f"T{uuid.uuid4().hex[:8].upper()}"
            db.add(Ticket(id=tid, organizacion_id=org.id, linea="2235551111", descripcion_falla="Sin internet", estado=ticket, origen="Portal"))
            conv.ticket_id = tid
        if visitante:
            crepo.set_contexto(conv, {"visitante": True, "cola_prioridad": "baja"})
        db.add(PortalAbonadoLink(organizacion_id=org.id, dni_normalized=dni, dni_hash=hash_dni(dni), abonado_ref=f"ref{dni}", pin_hash=hash_pin(PIN), activo="Sí"))
        db.commit()
        return SimpleNamespace(org_id=org.id, dni=dni, conv_id=conv.id, ticket_id=tid)


def _relogin(e, via: str, canal: str = "web") -> dict:
    hdr = {"X-Canal": canal}
    if via == "pin":
        r = client.post("/api/v1/portal/auth/login-pin", headers=hdr, json={"dni": e.dni, "pin": PIN, "org_slug": "coop-batan"})
    else:
        with get_session_factory()() as db:
            ch = PortalOtpChallenge(organizacion_id=e.org_id, dni_normalized=e.dni, code_hash=hash_token(OTP), abonado_ref=f"ref{e.dni}",
                                    expires_at=datetime.now(UTC) + timedelta(minutes=10))
            db.add(ch)
            db.commit()
            cid = ch.id
        r = client.post("/api/v1/portal/auth/verify", headers=hdr, json={"challenge_id": cid, "otp": OTP, "org_slug": "coop-batan"})
    assert r.status_code == 200, r.text
    return r.json()["conversacion"]


def _conv(e) -> ConversacionCanal:
    with get_session_factory()() as db:
        return db.get(ConversacionCanal, e.conv_id)


VIAS = [(v, c) for v in ("pin", "otp") for c in ("web", "app")]
VIAS_IDS = [f"{v}-{c}" for v, c in VIAS]


@xf_h24
@pytest.mark.parametrize(("via", "canal"), VIAS, ids=VIAS_IDS)
def test_relogin_con_ticket_abierto_conserva_conversacion_ticket_y_estado(via, canal):
    e = _escenario()
    c = _relogin(e, via, canal)
    assert c["id"] == e.conv_id and c["estado"] == "espera_agente" and c["ticket_id"] == e.ticket_id, c
    assert (_conv(e).ticket_id, _conv(e).estado) == (e.ticket_id, "espera_agente")


@pytest.mark.parametrize(("via", "canal"), VIAS, ids=VIAS_IDS)
def test_relogin_con_agente_asignado_conserva_ticket(via, canal):
    e = _escenario(estado="con_agente", agente_id="agente-1")
    c = _relogin(e, via, canal)
    assert c["id"] == e.conv_id and c["estado"] == "con_agente" and c["ticket_id"] == e.ticket_id, c


@pytest.mark.parametrize("via", ["pin", "otp"])
def test_relogin_con_ticket_cerrado_no_cambia_el_comportamiento(via):
    """Ticket ya cerrado: ``get_or_create_conversacion`` cierra el hilo viejo y abre uno nuevo en «bot» sin ticket (igual que antes)."""
    e = _escenario(ticket="Cerrado")
    c = _relogin(e, via)
    assert c["id"] != e.conv_id and c["estado"] == "bot" and not c.get("ticket_id"), c
    assert _conv(e).estado == "cerrado"


@pytest.mark.parametrize("via", ["pin", "otp"])
def test_relogin_de_visitante_en_cola_sin_ticket_sale_de_la_cola(via):
    """Negativo: sin ticket ligado el reset se mantiene (el visitante anónimo identificado deja la cola y vuelve a «bot»)."""
    e = _escenario(ticket=None, visitante=True)
    c = _relogin(e, via)
    assert c["id"] == e.conv_id and c["estado"] == "bot" and not c.get("ticket_id"), c
    assert not (crepo.get_contexto(_conv(e)).get("cola_prioridad"))


@pytest.mark.parametrize("via", ["pin", "otp"])
def test_relogin_en_espera_sin_ticket_vuelve_a_bot(via):
    e = _escenario(ticket=None)
    c = _relogin(e, via)
    assert c["id"] == e.conv_id and c["estado"] == "bot" and not c.get("ticket_id"), c
