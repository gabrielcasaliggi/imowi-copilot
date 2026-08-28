"""Portal del abonado — auth DNI+OTP/PIN + chat (JWT typ=portal). Canales web y app."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branding_assistant import frase_soy_eko, saludo_con_menu
from app.config import (
    OTP_LENGTH,
    OTP_MAX_ATTEMPTS,
    OTP_TTL_MINUTES,
    PORTAL_ALLOW_GUEST,
    PORTAL_AUTH_SECRET,
    PORTAL_JWT_AUD,
    PORTAL_TOKEN_HOURS,
    WHATSAPP_DEFAULT_ORG_SLUG,
    es_produccion,
)
from app.domain.canales import normalizar_canal_portal
from app.domain.flujos_abonado import texto_menu_consulta
from app.estate import canal_repo as crepo
from app.estate import repository as repo
from app.estate.database import get_db
from app.estate.models import Abonado, PortalAbonadoLink, PortalDevice, PortalOtpChallenge
from app.estate.security import (
    generate_otp,
    hash_dni,
    hash_pin,
    hash_token,
    mask_email,
    normalizar_dni,
    valid_dni_ar,
    valid_pin,
    verify_pin,
)
from app.services import auth_security as aseg
from app.services import email as email_svc
from app.services.billtrack import lookup_abonado_por_dni
from app.services.canal_abonado import (
    marcar_cola_visitante,
    mensaje_derivacion_visitante,
    procesar_mensaje_entrante,
)
from app.services.platform_settings import resolve_canal_usar_llama

router = APIRouter(tags=["Portal"])

_ALG = "HS256"
_PORTAL_TYP = "portal"
_GENERIC_AUTH_MSG = "No pudimos verificar los datos. Revisá DNI y cooperativa o intentá más tarde."


class PortalSessionIn(BaseModel):
    telefono: str = Field(default="", max_length=40)
    dni: str = Field(default="", max_length=20)
    org_slug: str = Field(default="")


class PortalMessageIn(BaseModel):
    texto: str = Field(..., min_length=1, max_length=4000)


class PortalAuthStartIn(BaseModel):
    dni: str = Field(..., max_length=20)
    org_slug: str = Field(default="")
    linea: str = Field(default="", max_length=20)


class PortalAuthVerifyIn(BaseModel):
    challenge_id: str = Field(..., max_length=36)
    otp: str = Field(..., min_length=4, max_length=8)
    org_slug: str = Field(default="")


class PortalPinLoginIn(BaseModel):
    dni: str = Field(..., max_length=20)
    pin: str = Field(..., min_length=6, max_length=8)
    org_slug: str = Field(default="")


class PortalSetPinIn(BaseModel):
    pin: str = Field(..., min_length=6, max_length=8)


class PortalDeviceIn(BaseModel):
    expo_push_token: str = Field(..., min_length=16, max_length=191)
    platform: str = Field(default="", max_length=16)
    device_name: str = Field(default="", max_length=80)


def _org_slug(raw: str) -> str:
    return (raw or "").strip() or WHATSAPP_DEFAULT_ORG_SLUG or "coop-batan"


def _portal_secret() -> str:
    if PORTAL_AUTH_SECRET:
        return PORTAL_AUTH_SECRET
    if es_produccion():
        raise HTTPException(503, "PORTAL_AUTH_SECRET no configurado")
    # Dev fallback
    from app.auth import _secret_efectivo

    return _secret_efectivo()


def _client_ip(request: Request | None) -> str:
    if request is None:
        return ""
    forwarded = request.headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client:
        return (request.client.host or "")[:64]
    return ""


def _canal_desde_request(request: Request | None, payload: dict | None = None) -> str:
    header = ""
    if request is not None:
        header = request.headers.get("x-canal") or ""
    jwt_canal = (payload or {}).get("canal") or ""
    return normalizar_canal_portal(header or jwt_canal or "web")


def _crear_portal_token(
    *,
    org_id: str,
    org_slug: str,
    conversacion_id: str,
    telefono: str,
    abonado_id: str = "",
    dni: str = "",
    abonado_ref: str = "",
    identified: bool = False,
    canal: str = "web",
) -> str:
    exp = datetime.now(UTC) + timedelta(hours=PORTAL_TOKEN_HOURS)
    return jwt.encode(
        {
            "typ": _PORTAL_TYP,
            "aud": PORTAL_JWT_AUD,
            "org_id": org_id,
            "org_slug": org_slug,
            "conversacion_id": conversacion_id,
            "telefono": telefono,
            "abonado_id": abonado_id,
            "dni": dni,
            "abonado_ref": abonado_ref,
            "identified": identified,
            "canal": normalizar_canal_portal(canal),
            "jti": str(uuid.uuid4()),
            "exp": exp,
        },
        _portal_secret(),
        algorithm=_ALG,
    )


def _leer_portal_token(token: str | None) -> dict:
    if not token:
        raise HTTPException(401, "Sesión de portal requerida")
    raw = token[7:] if token.lower().startswith("bearer ") else token
    try:
        payload = jwt.decode(
            raw,
            _portal_secret(),
            algorithms=[_ALG],
            audience=PORTAL_JWT_AUD,
        )
    except jwt.PyJWTError:
        # Compat tokens antiguos sin aud (solo non-prod)
        if es_produccion():
            raise HTTPException(401, "Sesión de portal inválida o expirada") from None
        try:
            payload = jwt.decode(
                raw,
                _portal_secret(),
                algorithms=[_ALG],
                options={"verify_aud": False},
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(401, "Sesión de portal inválida o expirada") from exc
    if payload.get("typ") != _PORTAL_TYP:
        raise HTTPException(401, "Token no es de portal")
    return payload


def _portal_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict:
    from app.http_cookies import portal_token_from_request

    token = portal_token_from_request(request, authorization)
    return _leer_portal_token(token)


def _get_or_create_link(
    db: Session,
    *,
    org_id: str,
    dni_n: str,
    abonado_ref: str,
    email_masked: str,
) -> PortalAbonadoLink:
    link = db.scalar(
        select(PortalAbonadoLink).where(
            PortalAbonadoLink.organizacion_id == org_id,
            PortalAbonadoLink.dni_normalized == dni_n,
        )
    )
    if link:
        if abonado_ref:
            link.abonado_ref = abonado_ref
        if email_masked:
            link.contacto_email_masked = email_masked
        link.last_login_at = datetime.now(UTC)
        db.commit()
        db.refresh(link)
        return link
    link = PortalAbonadoLink(
        organizacion_id=org_id,
        dni_normalized=dni_n,
        dni_hash=hash_dni(dni_n),
        abonado_ref=abonado_ref,
        contacto_email_masked=email_masked,
        last_login_at=datetime.now(UTC),
        activo="Sí",
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def _abrir_conversacion_identificada(
    db: Session,
    *,
    org,
    dni_n: str,
    telefono: str,
    abonado_ref: str,
    hit: dict | None = None,
    canal: str = "web",
) -> tuple:
    from app.services.billtrack import ensure_local_abonado

    abo = crepo.find_abonado_por_dni(db, org.id, dni_n)
    if hit:
        try:
            abo = ensure_local_abonado(db, org.id, {**hit, "dni": dni_n})
        except Exception:
            abo = abo or None
    tel = crepo.normalizar_telefono(telefono) if telefono else ""
    if abo and abo.telefono_e164:
        tel = crepo.normalizar_telefono(abo.telefono_e164)
    if not tel:
        tel = f"portal{dni_n}"
    canal_n = normalizar_canal_portal(canal)
    conv = crepo.get_or_create_conversacion(db, org.id, telefono=tel, canal=canal_n, wa_id=tel)
    msgs_previos = crepo.list_mensajes(db, conv.id)
    if abo and not conv.abonado_id:
        conv.abonado_id = abo.id
    conv.canal = canal_n
    db.commit()
    db.refresh(conv)
    ctx = crepo.get_contexto(conv)
    ctx["saludo"] = True
    ctx["identificado"] = True
    ctx["dni"] = dni_n
    ctx["abonado_ref"] = abonado_ref
    if hit and hit.get("fuente"):
        ctx["padron_fuente"] = hit.get("fuente")
    ctx.pop("invitado", None)
    ctx.pop("visitante", None)
    ctx.pop("cola_prioridad", None)
    ctx.pop("motivo_derivacion", None)
    ctx.pop("pidio_humano", None)
    crepo.set_contexto(conv, ctx)
    db.commit()

    # Re-login identificado: si no hay agente activo, volver a modo bot N1
    if conv.estado in ("espera_agente", "cerrado") and not conv.agente_id:
        conv.estado = "bot"
        conv.ticket_id = ""
        db.commit()
        db.refresh(conv)

    if not msgs_previos:
        nombre = (abo.nombre if abo else "") or ""
        primer = nombre.split()[0].title() if nombre.strip() else ""
        estado = ((abo.estado if abo else "") or "").lower()
        if estado == "baja":
            saludo = (
                f"{frase_soy_eko(primer_nombre=primer)}. "
                "Tu cuenta figura «de baja» en el padrón. "
                "Igual puedo ayudarte (reactivación, factura u otro trámite). ¿Qué necesitás?"
            )
        else:
            menu = texto_menu_consulta(abo.servicio if abo else "")
            saludo = saludo_con_menu(primer_nombre=primer, menu=menu)
        crepo.add_mensaje(
            db, org.id, conv.id, direccion="out", autor="bot", texto=saludo
        )
    return conv, abo, tel


@router.post("/portal/auth/start")
def portal_auth_start(
    body: PortalAuthStartIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """Inicia auth abonado: DNI → BillTrack RO → OTP email (anti-enumeración)."""
    ip = _client_ip(request)
    slug = _org_slug(body.org_slug)
    dni_n = normalizar_dni(body.dni)
    actor = f"{slug}:{dni_n or 'invalid'}"

    if aseg.is_locked(db, superficie="portal", actor=actor, ip=ip):
        aseg.record_login_event(
            db, superficie="portal", actor=actor, ip=ip, ok=False, reason="locked", org_slug=slug
        )
        raise HTTPException(429, "Demasiados intentos. Probá más tarde.")

    # Respuesta genérica siempre (anti-enum) salvo éxito con challenge
    def _fail(reason: str):
        aseg.record_login_event(
            db, superficie="portal", actor=actor, ip=ip, ok=False, reason=reason, org_slug=slug
        )
        aseg.register_failure(db, superficie="portal", actor=actor, ip=ip)
        # Misma forma de respuesta exitosa engañosa? Plan: mismo mensaje de error
        raise HTTPException(400, _GENERIC_AUTH_MSG)

    if not valid_dni_ar(dni_n):
        _fail("bad_dni")

    org = repo.get_org_by_slug(db, slug)
    if not org:
        _fail("bad_org")

    try:
        hit = lookup_abonado_por_dni(dni_n, org_slug=slug, linea=body.linea, db=db)
    except Exception:
        _fail("billtrack_error")

    if not hit:
        _fail("not_found_or_inactive")

    email = (hit.get("email") or "").strip()
    if not email or "@" not in email:
        _fail("no_contact")

    # Cuentas de baja / inactivas: se identifican igual (OTP) para trámites y consultas.

    otp = generate_otp(OTP_LENGTH)
    challenge = PortalOtpChallenge(
        organizacion_id=org.id,
        dni_normalized=dni_n,
        code_hash=hash_token(otp),
        contact_masked=mask_email(email),
        abonado_ref=str(hit.get("ref") or ""),
        email_destino=email,
        ip=ip,
        expires_at=datetime.now(UTC) + timedelta(minutes=OTP_TTL_MINUTES),
    )
    db.add(challenge)
    db.commit()
    db.refresh(challenge)

    sent = email_svc.send_otp_email(
        to=email,
        otp=otp,
        org_nombre=org.nombre,
        ttl_minutes=OTP_TTL_MINUTES,
    )
    if not sent and es_produccion():
        _fail("email_failed")

    aseg.record_login_event(
        db, superficie="portal", actor=actor, ip=ip, ok=True, reason="otp_sent", org_slug=slug
    )
    out = {
        "status": "otp_sent",
        "challenge_id": challenge.id,
        "contact_masked": challenge.contact_masked,
        "expires_in_seconds": OTP_TTL_MINUTES * 60,
        "org_slug": org.slug,
    }
    if not es_produccion():
        out["debug_otp"] = otp  # solo tests/dev
    return out


@router.post("/portal/auth/verify")
def portal_auth_verify(
    body: PortalAuthVerifyIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    ip = _client_ip(request)
    challenge = db.get(PortalOtpChallenge, body.challenge_id)
    if not challenge or challenge.consumed_at:
        raise HTTPException(400, _GENERIC_AUTH_MSG)

    exp = challenge.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    if exp < datetime.now(UTC):
        raise HTTPException(400, _GENERIC_AUTH_MSG)

    if challenge.attempts >= OTP_MAX_ATTEMPTS:
        raise HTTPException(429, "Demasiados intentos. Solicitá un nuevo código.")

    if hash_token(body.otp.strip()) != challenge.code_hash:
        challenge.attempts = int(challenge.attempts or 0) + 1
        db.commit()
        aseg.record_login_event(
            db,
            superficie="portal",
            actor=f"{challenge.dni_normalized}",
            ip=ip,
            ok=False,
            reason="bad_otp",
        )
        raise HTTPException(400, _GENERIC_AUTH_MSG)

    challenge.consumed_at = datetime.now(UTC)
    db.commit()

    org = repo.get_org_by_id(db, challenge.organizacion_id)
    if not org:
        raise HTTPException(400, _GENERIC_AUTH_MSG)

    link = _get_or_create_link(
        db,
        org_id=org.id,
        dni_n=challenge.dni_normalized,
        abonado_ref=challenge.abonado_ref,
        email_masked=challenge.contact_masked,
    )
    # Buscar teléfono/saldo del padrón (BillTrack); si falla, seguir con el link local
    try:
        hit = lookup_abonado_por_dni(challenge.dni_normalized, org_slug=org.slug, db=db) or {}
    except Exception:
        hit = {}
    conv, abo, tel = _abrir_conversacion_identificada(
        db,
        org=org,
        dni_n=challenge.dni_normalized,
        telefono=str(hit.get("telefono") or ""),
        abonado_ref=challenge.abonado_ref,
        hit=hit,
        canal=_canal_desde_request(request),
    )
    token = _crear_portal_token(
        org_id=org.id,
        org_slug=org.slug,
        conversacion_id=conv.id,
        telefono=tel,
        abonado_id=abo.id if abo else "",
        dni=challenge.dni_normalized,
        abonado_ref=challenge.abonado_ref,
        identified=True,
        canal=_canal_desde_request(request),
    )
    aseg.clear_failures(
        db, superficie="portal", actor=f"{org.slug}:{challenge.dni_normalized}", ip=ip
    )
    aseg.record_login_event(
        db,
        superficie="portal",
        actor=challenge.dni_normalized,
        ip=ip,
        ok=True,
        reason="otp_ok",
        org_slug=org.slug,
    )
    mensajes = [crepo.mensaje_to_dict(m) for m in crepo.list_mensajes(db, conv.id)]
    if not mensajes:
        nombre = (abo.nombre if abo else hit.get("nombre") or "hola").split()[0]
        saludo = saludo_con_menu(
            primer_nombre=nombre,
            menu=texto_menu_consulta(abo.servicio if abo else ""),
        )
        crepo.add_mensaje(db, org.id, conv.id, direccion="out", autor="bot", texto=saludo)
        mensajes = [crepo.mensaje_to_dict(m) for m in crepo.list_mensajes(db, conv.id)]

    from app.http_cookies import set_portal_cookie

    set_portal_cookie(response, token, request=request)
    return {
        "portal_token": token,
        "org_slug": org.slug,
        "abonado_identificado": True,
        "has_pin": bool(link.pin_hash),
        "conversacion": crepo.conversacion_to_dict(conv, abonado=abo),
        "mensajes": mensajes,
        "contact_masked": link.contacto_email_masked,
    }


@router.post("/portal/auth/login-pin")
def portal_login_pin(
    body: PortalPinLoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    ip = _client_ip(request)
    slug = _org_slug(body.org_slug)
    dni_n = normalizar_dni(body.dni)
    actor = f"{slug}:{dni_n}"

    if aseg.is_locked(db, superficie="portal", actor=actor, ip=ip):
        raise HTTPException(429, "Demasiados intentos. Probá más tarde.")
    if not valid_dni_ar(dni_n) or not valid_pin(body.pin):
        aseg.register_failure(db, superficie="portal", actor=actor, ip=ip)
        raise HTTPException(400, _GENERIC_AUTH_MSG)

    org = repo.get_org_by_slug(db, slug)
    if not org:
        raise HTTPException(400, _GENERIC_AUTH_MSG)

    link = db.scalar(
        select(PortalAbonadoLink).where(
            PortalAbonadoLink.organizacion_id == org.id,
            PortalAbonadoLink.dni_normalized == dni_n,
        )
    )
    if not link or not link.pin_hash or not verify_pin(body.pin, link.pin_hash):
        aseg.record_login_event(
            db, superficie="portal", actor=actor, ip=ip, ok=False, reason="bad_pin", org_slug=slug
        )
        aseg.register_failure(db, superficie="portal", actor=actor, ip=ip)
        raise HTTPException(400, _GENERIC_AUTH_MSG)

    try:
        hit = lookup_abonado_por_dni(dni_n, org_slug=slug, db=db) or {}
    except Exception:
        hit = {}
    try:
        conv, abo, tel = _abrir_conversacion_identificada(
            db,
            org=org,
            dni_n=dni_n,
            telefono=str(hit.get("telefono") or ""),
            abonado_ref=link.abonado_ref,
            hit=hit,
            canal=_canal_desde_request(request),
        )
        link.last_login_at = datetime.now(UTC)
        db.commit()
        token = _crear_portal_token(
            org_id=org.id,
            org_slug=org.slug,
            conversacion_id=conv.id,
            telefono=tel,
            abonado_id=abo.id if abo else "",
            dni=dni_n,
            abonado_ref=link.abonado_ref,
            identified=True,
            canal=_canal_desde_request(request),
        )
        aseg.clear_failures(db, superficie="portal", actor=actor, ip=ip)
        aseg.record_login_event(
            db, superficie="portal", actor=actor, ip=ip, ok=True, reason="pin_ok", org_slug=slug
        )
        from app.http_cookies import set_portal_cookie

        set_portal_cookie(response, token, request=request)
        return {
            "portal_token": token,
            "org_slug": org.slug,
            "abonado_identificado": True,
            "has_pin": True,
            "conversacion": crepo.conversacion_to_dict(conv, abonado=abo),
            "mensajes": [crepo.mensaje_to_dict(m) for m in crepo.list_mensajes(db, conv.id)],
        }
    except HTTPException:
        raise
    except Exception:
        import logging

        logging.getLogger("operations_hub").exception("portal login-pin falló")
        raise HTTPException(
            503,
            "No pudimos iniciar la sesión ahora. Probá de nuevo en unos segundos.",
        ) from None


@router.post("/portal/auth/set-pin")
def portal_set_pin(
    body: PortalSetPinIn,
    payload: dict = Depends(_portal_auth),
    db: Session = Depends(get_db),
):
    if not payload.get("identified") or not payload.get("dni"):
        raise HTTPException(403, "Sesión identificada requerida")
    if not valid_pin(body.pin):
        raise HTTPException(400, "El PIN debe tener entre 6 y 8 dígitos")
    link = db.scalar(
        select(PortalAbonadoLink).where(
            PortalAbonadoLink.organizacion_id == payload["org_id"],
            PortalAbonadoLink.dni_normalized == payload["dni"],
        )
    )
    if not link:
        raise HTTPException(404, "Vínculo portal no encontrado")
    link.pin_hash = hash_pin(body.pin)
    link.enrolled_at = datetime.now(UTC)
    db.commit()
    return {"status": "ok", "has_pin": True}


@router.post("/portal/session")
def abrir_sesion_portal(
    body: PortalSessionIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Abre chat web. Guest anónimo OK; DNI solo ya NO identifica (usar /portal/auth/*)."""
    slug = _org_slug(body.org_slug)
    org = repo.get_org_by_slug(db, slug)
    if not org:
        raise HTTPException(404, f"Organización '{slug}' no encontrada")

    if not PORTAL_ALLOW_GUEST:
        raise HTTPException(
            401,
            "Iniciá sesión con DNI y verificación. Usá /api/v1/portal/auth/start",
        )

    # Guest anónimo — ignorar DNI/tel para identificación (anti spoofing)
    tel = f"guest{uuid.uuid4().hex[:12]}"
    canal_n = _canal_desde_request(request)
    conv = crepo.get_or_create_conversacion(db, org.id, telefono=tel, canal=canal_n, wa_id=tel)
    conv.canal = canal_n
    db.commit()
    db.refresh(conv)

    ctx = crepo.get_contexto(conv)
    if body.dni:
        ctx["dni_hint_ignored"] = True
    # Visitante: sin bot N1 — cola de agente con prioridad baja (clientes primero)
    ctx = marcar_cola_visitante(conv, ctx, motivo="portal_invitado")
    prev = str(ctx.pop("_prev_estado_antes_cola", "") or "")
    db.commit()
    db.refresh(conv)
    try:
        from app.services.handoff_notify import notify_espera_agente

        notify_espera_agente(db, conv, prev_estado=prev)
    except Exception:
        pass

    token = _crear_portal_token(
        org_id=org.id,
        org_slug=org.slug,
        conversacion_id=conv.id,
        telefono=tel,
        abonado_id="",
        identified=False,
        canal=canal_n,
    )
    mensajes = [crepo.mensaje_to_dict(m) for m in crepo.list_mensajes(db, conv.id)]
    if not mensajes:
        saludo = mensaje_derivacion_visitante(motivo="portal_invitado")
        crepo.add_mensaje(db, org.id, conv.id, direccion="out", autor="bot", texto=saludo)
        mensajes = [crepo.mensaje_to_dict(m) for m in crepo.list_mensajes(db, conv.id)]

    from app.http_cookies import set_portal_cookie

    set_portal_cookie(response, token, request=request)
    return {
        "portal_token": token,
        "org_slug": org.slug,
        "conversacion": crepo.conversacion_to_dict(conv, abonado=None),
        "mensajes": mensajes,
        "abonado_identificado": False,
        "modo_invitado": True,
        "auth_required_for_account": True,
        "es_visitante": True,
        "cola_prioridad": "baja",
    }


@router.post("/portal/logout")
def portal_logout(response: Response):
    """Cierra cookie de portal (el JWT en denylist no aplica; solo limpia cookie)."""
    from app.http_cookies import clear_portal_cookie

    clear_portal_cookie(response)
    return {"status": "ok"}


@router.post("/portal/account/delete")
def portal_delete_account(
    response: Response,
    payload: dict = Depends(_portal_auth),
    db: Session = Depends(get_db),
):
    """Borra PIN, dispositivos y vínculo de la app. El padrón de la cooperativa no se toca."""
    if not payload.get("identified") or not payload.get("dni"):
        raise HTTPException(403, "Sesión identificada requerida")
    org_id = payload["org_id"]
    dni = str(payload["dni"])
    devices = db.scalars(
        select(PortalDevice).where(
            PortalDevice.organizacion_id == org_id,
            PortalDevice.dni_normalized == dni,
        )
    ).all()
    for row in devices:
        db.delete(row)
    otps = db.scalars(
        select(PortalOtpChallenge).where(
            PortalOtpChallenge.organizacion_id == org_id,
            PortalOtpChallenge.dni_normalized == dni,
        )
    ).all()
    for row in otps:
        db.delete(row)
    link = db.scalar(
        select(PortalAbonadoLink).where(
            PortalAbonadoLink.organizacion_id == org_id,
            PortalAbonadoLink.dni_normalized == dni,
        )
    )
    if link:
        db.delete(link)
    from app.http_cookies import clear_portal_cookie

    clear_portal_cookie(response)
    db.commit()
    return {"status": "ok"}


@router.post("/portal/messages")
def portal_enviar_mensaje(
    body: PortalMessageIn,
    payload: dict = Depends(_portal_auth),
    db: Session = Depends(get_db),
):
    org_id = payload["org_id"]
    telefono = payload["telefono"]
    canal = _canal_desde_request(None, payload)
    try:
        result = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=telefono,
            texto=body.texto,
            canal=canal,
            usar_llama=resolve_canal_usar_llama(db),
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
    except HTTPException:
        raise
    except Exception:
        import logging

        logging.getLogger("operations_hub").exception("portal/messages falló")
        raise HTTPException(
            503,
            "No pudimos procesar el mensaje ahora. Probá de nuevo en unos segundos.",
        ) from None


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


def _respuesta_chat(db: Session, org_id: str, payload: dict, result: dict) -> dict:
    conv_id = result.get("conversacion_id") or payload["conversacion_id"]
    c = crepo.get_conversacion(db, org_id, conv_id)
    abo = db.get(Abonado, c.abonado_id) if c and c.abonado_id else None
    mensajes = [crepo.mensaje_to_dict(m) for m in crepo.list_mensajes(db, conv_id)] if c else []
    return {
        **result,
        "conversacion": crepo.conversacion_to_dict(c, abonado=abo) if c else None,
        "mensajes": mensajes,
    }


@router.post("/portal/devices")
def portal_register_device(
    body: PortalDeviceIn,
    payload: dict = Depends(_portal_auth),
    db: Session = Depends(get_db),
):
    from app.services.app_push import token_push_valido

    token = body.expo_push_token.strip()
    if not token_push_valido(token):
        raise HTTPException(400, "Token de push inválido")
    if not payload.get("identified"):
        raise HTTPException(403, "Sesión identificada requerida")

    dni = str(payload.get("dni") or "")
    link = None
    if dni:
        link = db.scalar(
            select(PortalAbonadoLink).where(
                PortalAbonadoLink.organizacion_id == payload["org_id"],
                PortalAbonadoLink.dni_normalized == dni,
            )
        )
    row = db.scalar(select(PortalDevice).where(PortalDevice.expo_push_token == token))
    now = datetime.now(UTC)
    platform = (body.platform or "").strip().lower()[:16]
    name = (body.device_name or "").strip()[:80]
    if row:
        row.organizacion_id = payload["org_id"]
        row.link_id = link.id if link else row.link_id
        row.dni_normalized = dni or row.dni_normalized
        row.conversacion_id = str(payload.get("conversacion_id") or row.conversacion_id)
        row.platform = platform or row.platform
        row.device_name = name or row.device_name
        row.activo = "Sí"
        row.last_seen_at = now
    else:
        row = PortalDevice(
            organizacion_id=payload["org_id"],
            link_id=link.id if link else "",
            dni_normalized=dni,
            conversacion_id=str(payload.get("conversacion_id") or ""),
            expo_push_token=token,
            platform=platform,
            device_name=name,
            last_seen_at=now,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return {"status": "ok", "device_id": row.id}


@router.delete("/portal/devices")
def portal_unregister_device(
    body: PortalDeviceIn,
    payload: dict = Depends(_portal_auth),
    db: Session = Depends(get_db),
):
    token = body.expo_push_token.strip()
    row = db.scalar(select(PortalDevice).where(PortalDevice.expo_push_token == token))
    if row and row.organizacion_id == payload["org_id"]:
        row.activo = "No"
        db.commit()
    return {"status": "ok"}


@router.post("/portal/audio")
async def portal_enviar_audio(
    payload: dict = Depends(_portal_auth),
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
):
    from app.services.transcription import MSG_AUDIO_FALLBACK, transcribir_audio, whisper_disponible

    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Audio vacío")
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(413, "Audio demasiado grande")
    filename = (file.filename or "voice.m4a")[:80]
    mime = (file.content_type or "audio/mp4").split(";")[0].strip() or "audio/mp4"
    texto = transcribir_audio(raw, filename=filename, mime=mime) if whisper_disponible() else ""
    if not texto:
        texto = MSG_AUDIO_FALLBACK
        # No corre N1 con el fallback: se persiste como respuesta del bot
        conv_id = payload["conversacion_id"]
        org_id = payload["org_id"]
        crepo.add_mensaje(
            db, org_id, conv_id, direccion="in", autor="cliente", texto="[audio]"
        )
        crepo.add_mensaje(
            db, org_id, conv_id, direccion="out", autor="bot", texto=texto
        )
        c = crepo.get_conversacion(db, org_id, conv_id)
        abo = db.get(Abonado, c.abonado_id) if c and c.abonado_id else None
        return {
            "ok": True,
            "transcripcion": "",
            "conversacion": crepo.conversacion_to_dict(c, abonado=abo) if c else None,
            "mensajes": [crepo.mensaje_to_dict(m) for m in crepo.list_mensajes(db, conv_id)],
        }

    canal = _canal_desde_request(None, payload)
    try:
        result = procesar_mensaje_entrante(
            db,
            payload["org_id"],
            telefono=payload["telefono"],
            texto=texto,
            canal=canal,
            usar_llama=resolve_canal_usar_llama(db),
            entrada_audio=True,
        )
        out = _respuesta_chat(db, payload["org_id"], payload, result)
        out["transcripcion"] = texto
        return out
    except HTTPException:
        raise
    except Exception:
        import logging

        logging.getLogger("operations_hub").exception("portal/audio falló")
        raise HTTPException(
            503,
            "No pudimos procesar el audio ahora. Probá de nuevo en unos segundos.",
        ) from None

