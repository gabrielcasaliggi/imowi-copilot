"""Portal web del abonado — chat con bot N1 y espera de agente (sin login de consola)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import _secret_efectivo  # noqa: PLC2701 — secret compartido JWT portal
from app.config import WHATSAPP_DEFAULT_ORG_SLUG
from app.estate import canal_repo as crepo
from app.estate import repository as repo
from app.estate.database import get_db
from app.estate.models import Abonado
from app.services.canal_abonado import procesar_mensaje_entrante

router = APIRouter(tags=["Portal"])

_PORTAL_HOURS = 12
_ALG = "HS256"


class PortalSessionIn(BaseModel):
    telefono: str = Field(default="", max_length=40)
    dni: str = Field(default="", max_length=20)
    org_slug: str = Field(default="")


class PortalMessageIn(BaseModel):
    texto: str = Field(..., min_length=1, max_length=4000)


def _org_slug(raw: str) -> str:
    return (raw or "").strip() or WHATSAPP_DEFAULT_ORG_SLUG or "coop-batan"


def _crear_portal_token(
    *,
    org_id: str,
    org_slug: str,
    conversacion_id: str,
    telefono: str,
    abonado_id: str = "",
) -> str:
    exp = datetime.now(UTC) + timedelta(hours=_PORTAL_HOURS)
    return jwt.encode(
        {
            "typ": "portal",
            "org_id": org_id,
            "org_slug": org_slug,
            "conversacion_id": conversacion_id,
            "telefono": telefono,
            "abonado_id": abonado_id,
            "exp": exp,
        },
        _secret_efectivo(),
        algorithm=_ALG,
    )


def _leer_portal_token(token: str | None) -> dict:
    if not token:
        raise HTTPException(401, "Sesión de portal requerida")
    raw = token[7:] if token.lower().startswith("bearer ") else token
    try:
        payload = jwt.decode(raw, _secret_efectivo(), algorithms=[_ALG])
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Sesión de portal inválida o expirada") from exc
    if payload.get("typ") != "portal":
        raise HTTPException(401, "Token no es de portal")
    return payload


def _portal_auth(
    authorization: str | None = Header(default=None),
) -> dict:
    return _leer_portal_token(authorization)


@router.post("/portal/session")
def abrir_sesion_portal(body: PortalSessionIn, db: Session = Depends(get_db)):
    """Abre chat web. Si hay match de teléfono/DNI, identifica; si no, permite invitado."""
    slug = _org_slug(body.org_slug)
    org = repo.get_org_by_slug(db, slug)
    if not org:
        raise HTTPException(404, f"Organización '{slug}' no encontrada")

    tel = crepo.normalizar_telefono(body.telefono)
    dni = crepo.normalizar_dni(body.dni)

    abonado: Abonado | None = None
    if tel:
        abonado = crepo.find_abonado_por_telefono(db, org.id, tel)
    if not abonado and dni:
        abonado = crepo.find_abonado_por_dni(db, org.id, dni)
        if abonado and abonado.telefono_e164:
            tel = crepo.normalizar_telefono(abonado.telefono_e164)

    # Sin padrón conectado: igual dejamos iniciar conversación (guest)
    if not tel:
        if dni:
            tel = f"guest{dni}"
        else:
            tel = f"guest{uuid.uuid4().hex[:12]}"

    conv = crepo.get_or_create_conversacion(db, org.id, telefono=tel, canal="web", wa_id=tel)
    if abonado and not conv.abonado_id:
        conv.abonado_id = abonado.id
    # Portal siempre opera como canal web (aunque hubiera un hilo previo)
    conv.canal = "web"
    db.commit()
    db.refresh(conv)

    ctx = crepo.get_contexto(conv)
    ctx["saludo"] = True
    if abonado:
        ctx["identificado"] = True
        ctx.pop("invitado", None)
    else:
        ctx["invitado"] = True
        if dni:
            ctx["dni_intentado"] = dni
    crepo.set_contexto(conv, ctx)
    db.commit()

    token = _crear_portal_token(
        org_id=org.id,
        org_slug=org.slug,
        conversacion_id=conv.id,
        telefono=tel,
        abonado_id=abonado.id if abonado else conv.abonado_id or "",
    )
    abo = db.get(Abonado, conv.abonado_id) if conv.abonado_id else abonado
    mensajes = [crepo.mensaje_to_dict(m) for m in crepo.list_mensajes(db, conv.id)]

    saludo = ""
    if not mensajes:
        if abo:
            saludo = (
                f"Hola {abo.nombre.split()[0]}, soy el asistente de Cooperativa Batán. "
                "¿Tu consulta es por internet (radio/antena o ADSL), móvil IMOVI, o factura/deuda?"
            )
        else:
            saludo = (
                "Hola, soy el asistente de Cooperativa Batán. "
                "Todavía no te encontramos en el padrón (próximamente se conecta la base). "
                "Igual podés consultar: ¿internet por radio/antena, ADSL, móvil IMOVI, o factura/deuda?"
            )
        crepo.add_mensaje(db, org.id, conv.id, direccion="out", autor="bot", texto=saludo)
        mensajes = [crepo.mensaje_to_dict(m) for m in crepo.list_mensajes(db, conv.id)]

    return {
        "portal_token": token,
        "org_slug": org.slug,
        "conversacion": crepo.conversacion_to_dict(conv, abonado=abo),
        "mensajes": mensajes,
        "abonado_identificado": bool(abo),
        "modo_invitado": not bool(abo),
    }


@router.post("/portal/messages")
def portal_enviar_mensaje(
    body: PortalMessageIn,
    payload: dict = Depends(_portal_auth),
    db: Session = Depends(get_db),
):
    org_id = payload["org_id"]
    telefono = payload["telefono"]
    result = procesar_mensaje_entrante(
        db,
        org_id,
        telefono=telefono,
        texto=body.texto,
        canal="web",
        usar_llama=False,
    )
    conv_id = result.get("conversacion_id") or payload["conversacion_id"]
    c = crepo.get_conversacion(db, org_id, conv_id)
    abo = db.get(Abonado, c.abonado_id) if c and c.abonado_id else None
    mensajes = [crepo.mensaje_to_dict(m) for m in crepo.list_mensajes(db, conv_id)] if c else []
    return {
        **result,
        "conversacion": crepo.conversacion_to_dict(c, abonado=abo) if c else None,
        "mensajes": mensajes,
    }


@router.get("/portal/conversations/{conv_id}")
def portal_obtener_conversacion(
    conv_id: str,
    payload: dict = Depends(_portal_auth),
    db: Session = Depends(get_db),
):
    if conv_id != payload.get("conversacion_id"):
        raise HTTPException(403, "Sesión no corresponde a esta conversación")
    c = crepo.get_conversacion(db, payload["org_id"], conv_id)
    if not c:
        raise HTTPException(404, "Conversación no encontrada")
    abo = db.get(Abonado, c.abonado_id) if c.abonado_id else None
    mensajes = [crepo.mensaje_to_dict(m) for m in crepo.list_mensajes(db, c.id)]
    return {
        "conversacion": crepo.conversacion_to_dict(c, abonado=abo),
        "mensajes": mensajes,
    }
