"""Administración de cooperativas, usuarios e importación CSV — solo admin plataforma."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.schemas import OrganizationCreate, OrganizationUpdate, UserCreate, UserUpdate
from app.auth import UsuarioSesion, requiere_admin
from app.estate import repository as repo
from app.estate.audit import log_audit
from app.estate.database import get_db
from app.estate.import_csv import import_usuarios_csv
from app.estate.security import valid_email, valid_password
from app.rbac import roles_alta_permitidos

router = APIRouter(tags=["Admin"])


def _org_or_404(db: Session, slug: str):
    org = repo.get_org_by_slug(db, slug)
    if not org:
        raise HTTPException(404, f"Cooperativa '{slug}' no encontrada")
    return org


@router.get("/admin/organizations")
def list_organizations_admin(
    _: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    return {"organizaciones": repo.list_organizations_admin(db)}


@router.post("/admin/organizations")
def create_organization(
    body: OrganizationCreate,
    admin: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    if not body.nombre.strip():
        raise HTTPException(400, "El nombre es obligatorio")
    org = repo.create_organization(
        db,
        nombre=body.nombre.strip(),
        slug=body.slug.strip() if body.slug else None,
        logo_label=body.logo_label,
        brand_color=body.brand_color,
    )
    log_audit(
        db,
        org_id=org.id,
        actor=admin.usuario,
        accion="cooperativa_alta",
        recurso=org.slug,
        detalle=f"Cooperativa creada: {org.nombre}",
    )
    return {
        "status": "ok",
        "organizacion": {
            "slug": org.slug,
            "nombre": org.nombre,
            "brand_color": org.brand_color,
            "logo_label": org.logo_label,
            **repo.organization_stats(db, org.id),
        },
    }


@router.put("/admin/organizations/{slug}")
def update_organization(
    slug: str,
    body: OrganizationUpdate,
    _: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    org = repo.update_organization(
        db,
        slug,
        nombre=body.nombre.strip() if body.nombre else None,
        logo_label=body.logo_label,
        brand_color=body.brand_color,
    )
    if not org:
        raise HTTPException(404, f"Cooperativa '{slug}' no encontrada")
    return {
        "status": "ok",
        "organizacion": {
            "slug": org.slug,
            "nombre": org.nombre,
            "brand_color": org.brand_color,
            "logo_label": org.logo_label,
            **repo.organization_stats(db, org.id),
        },
    }


@router.delete("/admin/organizations/{slug}")
def delete_organization(
    slug: str,
    confirm_slug: str = "",
    admin: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    """Elimina cooperativa + usuarios y datos asociados. Requiere confirm_slug=slug."""
    if (confirm_slug or "").strip() != slug:
        raise HTTPException(
            400,
            "Confirmación inválida: pasá ?confirm_slug=<mismo-slug> para confirmar el borrado",
        )
    try:
        result = repo.delete_organization(db, slug, actor=admin.usuario)
    except ValueError as exc:
        code = str(exc)
        if code == "not_found":
            raise HTTPException(404, f"Cooperativa '{slug}' no encontrada") from exc
        if code == "protected":
            raise HTTPException(400, "No se puede eliminar la organización plataforma (imowi)") from exc
        raise HTTPException(400, code) from exc
    return {"status": "ok", "eliminada": result}


@router.get("/admin/organizations/{slug}/users")
def list_organization_users(
    slug: str,
    _: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    org = _org_or_404(db, slug)
    users = repo.list_users_for_org(db, org.id)
    return {
        "slug": slug,
        "usuarios": [repo.user_to_dict(u) for u in users],
    }


@router.post("/admin/organizations/{slug}/users")
def create_organization_user(
    slug: str,
    body: UserCreate,
    admin: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    org = _org_or_404(db, slug)
    from app.rbac import normalizar_rol_consola

    allowed = roles_alta_permitidos(actor_rol="admin", org_slug=slug)
    rol_norm = normalizar_rol_consola(body.rol or "agente", slug)
    if rol_norm not in allowed:
        raise HTTPException(
            400,
            f"Rol '{body.rol}' no permitido en esta organización. Permitidos: {', '.join(sorted(allowed))}",
        )
    if not body.email.strip() or not body.nombre.strip():
        raise HTTPException(400, "Email y nombre son obligatorios")
    if not valid_email(body.email.strip()):
        raise HTTPException(400, "Email inválido")
    import secrets
    import string

    pwd = (body.password or "").strip()
    generated = False
    if not pwd:
        alphabet = string.ascii_letters + string.digits
        pwd = "Tmp" + "".join(secrets.choice(alphabet) for _ in range(10)) + "1a"
        generated = True
    if not valid_password(pwd):
        from app.estate.security import password_policy_errors

        raise HTTPException(
            400,
            "La clave no cumple la política: " + ", ".join(password_policy_errors(pwd)),
        )
    try:
        user = repo.create_user_for_org(
            db,
            org.id,
            email=body.email.strip(),
            nombre=body.nombre.strip(),
            password=pwd,
            rol=rol_norm,
            telefono=body.telefono,
            linea_principal=body.linea_principal,
            must_change_password=True,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    log_audit(
        db,
        org_id=org.id,
        actor=admin.usuario,
        accion="usuario_alta",
        recurso=user.email,
        detalle=f"Usuario {user.nombre} ({user.rol}) en {slug}",
    )
    out: dict = {"status": "ok", "usuario": repo.user_to_dict(user)}
    if generated:
        out["temporary_password"] = pwd
    return out


@router.patch("/admin/organizations/{slug}/users/{user_id}")
def update_organization_user(
    slug: str,
    user_id: str,
    body: UserUpdate,
    admin: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    org = _org_or_404(db, slug)
    allowed = roles_alta_permitidos(actor_rol="admin", org_slug=slug)
    try:
        user = repo.update_user_for_org(
            db,
            org.id,
            user_id,
            nombre=body.nombre,
            rol=body.rol,
            telefono=body.telefono,
            linea_principal=body.linea_principal,
            activo=body.activo,
            password=body.password,
            allowed_roles=allowed if body.rol is not None else None,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not user:
        raise HTTPException(404, "Usuario no encontrado")
    log_audit(
        db,
        org_id=org.id,
        actor=admin.usuario,
        accion="usuario_actualizacion",
        recurso=user.email,
        detalle=f"activo={repo.user_is_active(user)} rol={user.rol}",
    )
    return {"status": "ok", "usuario": repo.user_to_dict(user)}


@router.post("/admin/organizations/{slug}/users/{user_id}/reset-password")
def admin_reset_user_password(
    slug: str,
    user_id: str,
    admin: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    """Envía link de reset por email. El usuario define su nueva clave en /invite."""
    from datetime import UTC, datetime, timedelta

    from app.estate.models import UserInvite
    from app.estate.security import generate_invite_token, hash_token
    from app.services import email as email_svc

    org = _org_or_404(db, slug)
    user = repo.get_user_by_id(db, org.id, user_id)
    if not user:
        raise HTTPException(404, "Usuario no encontrado")

    # Invalidar resets pendientes previos
    now = datetime.now(UTC)
    pending = list(
        db.scalars(
            select(UserInvite).where(
                UserInvite.organizacion_id == org.id,
                UserInvite.email == user.email,
                UserInvite.purpose == "password_reset",
                UserInvite.accepted_at.is_(None),
            )
        ).all()
    )
    for inv in pending:
        inv.accepted_at = now

    raw = generate_invite_token()
    invite = UserInvite(
        organizacion_id=org.id,
        email=user.email,
        nombre=user.nombre or "",
        rol=user.rol,
        purpose="password_reset",
        token_hash=hash_token(raw),
        invited_by=admin.usuario,
        expires_at=now + timedelta(hours=24),
    )
    db.add(invite)
    user.token_version = int(getattr(user, "token_version", 0) or 0) + 1
    db.commit()

    sent = email_svc.send_password_reset_email(
        to=user.email,
        nombre=user.nombre or user.email,
        org_nombre=org.nombre,
        token=raw,
    )
    log_audit(
        db,
        org_id=org.id,
        actor=admin.usuario,
        accion="auth.reset_password_email",
        recurso=user.email,
        detalle=f"admin_hub sent={sent}",
    )
    from app.config import es_produccion

    out: dict = {
        "status": "ok",
        "email": user.email,
        "via_email": True,
        "email_sent": sent,
        "must_change_password": True,
    }
    if not sent:
        out["email_error"] = email_svc.get_last_error() or "No se pudo enviar el email"
    if not sent or not es_produccion():
        out["token"] = raw
        out["invite_link"] = email_svc.invite_public_link(raw)
    return out


@router.post("/admin/organizations/{slug}/invites")
def admin_create_invite(
    slug: str,
    body: dict = Body(...),
    admin: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    """Invitación por email desde Admin Hub (alta de operador sin clave temporal)."""
    from datetime import UTC, datetime, timedelta

    from app.estate.models import User, UserInvite
    from app.estate.security import generate_invite_token, hash_token, valid_email
    from app.rbac import normalizar_rol_consola
    from app.services import email as email_svc

    org = _org_or_404(db, slug)
    email = str(body.get("email") or "").strip().lower()
    nombre = str(body.get("nombre") or "").strip()
    if not email or not valid_email(email):
        raise HTTPException(400, "Email inválido")
    allowed = roles_alta_permitidos(actor_rol="admin", org_slug=slug)
    rol = normalizar_rol_consola(str(body.get("rol") or "agente"), slug)
    if rol not in allowed:
        raise HTTPException(400, f"Rol '{rol}' no permitido. Permitidos: {', '.join(sorted(allowed))}")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(400, "El email ya está registrado — usá «Reset por email»")

    now = datetime.now(UTC)
    for inv in db.scalars(
        select(UserInvite).where(
            UserInvite.organizacion_id == org.id,
            UserInvite.email == email,
            UserInvite.purpose == "invite",
            UserInvite.accepted_at.is_(None),
        )
    ).all():
        inv.accepted_at = now

    raw = generate_invite_token()
    invite = UserInvite(
        organizacion_id=org.id,
        email=email,
        nombre=nombre,
        rol=rol,
        purpose="invite",
        token_hash=hash_token(raw),
        invited_by=admin.usuario,
        expires_at=now + timedelta(hours=72),
    )
    db.add(invite)
    db.commit()

    sent = email_svc.send_invite_email(
        to=email,
        nombre=nombre or email,
        org_nombre=org.nombre,
        token=raw,
        rol=rol,
    )
    log_audit(
        db,
        org_id=org.id,
        actor=admin.usuario,
        accion="auth.invite_create",
        recurso=email,
        detalle=f"admin_hub rol={rol} sent={sent}",
    )
    from app.config import es_produccion

    out: dict = {
        "status": "ok",
        "email": email,
        "rol": rol,
        "purpose": "invite",
        "expires_at": invite.expires_at.isoformat(),
        "email_sent": sent,
    }
    if not sent:
        out["email_error"] = email_svc.get_last_error() or "No se pudo enviar el email"
    if not sent or not es_produccion():
        out["token"] = raw
        out["invite_link"] = email_svc.invite_public_link(raw)
    return out


@router.post("/admin/organizations/{slug}/import-csv")
async def import_organization_csv(
    slug: str,
    file: UploadFile = File(...),
    admin: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    org = _org_or_404(db, slug)
    if org.slug == "imowi":
        raise HTTPException(400, "Importá usuarios en una cooperativa operativa, no en la plataforma NOC")
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "El CSV debe estar en UTF-8") from exc

    result = import_usuarios_csv(db, org, text)
    log_audit(
        db,
        org_id=org.id,
        actor=admin.usuario,
        accion="usuarios_import_csv",
        recurso=slug,
        detalle=f"creados={result.creados} actualizados={result.actualizados} omitidos={result.omitidos}",
    )
    return {
        "status": "ok",
        "slug": slug,
        "creados": result.creados,
        "actualizados": result.actualizados,
        "lineas_creadas": result.lineas_creadas,
        "omitidos": result.omitidos,
        "errores": result.errores,
        "filas": result.filas,
    }


@router.get("/admin/audit")
def list_audit_events(
    limit: int = 50,
    admin: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    from app.estate.audit import list_audit

    org = repo.get_org_by_slug(db, "imowi")
    org_id = org.id if org else ""
    events = list_audit(db, org_id, limit=min(limit, 200), admin_global=True)
    return {
        "eventos": [
            {
                "id": e.id,
                "organizacion_id": e.organizacion_id,
                "actor": e.actor,
                "accion": e.accion,
                "recurso": e.recurso,
                "detalle": e.detalle,
                "created_at": e.created_at.isoformat() if e.created_at else "",
            }
            for e in events
        ]
    }


@router.get("/admin/settings")
def get_platform_settings(
    _: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    from app.services.platform_settings import public_status

    return public_status(db)


@router.put("/admin/settings")
def update_platform_settings(
    body: dict,
    admin: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    from app.services.platform_settings import public_status, save_settings

    patch = body.get("settings") if isinstance(body.get("settings"), dict) else body
    if not isinstance(patch, dict):
        raise HTTPException(400, "Body inválido")
    # Solo secciones conocidas
    allowed = {"ai", "whatsapp", "telegram", "database", "billtrack", "knowledge", "canal", "playbooks"}
    clean = {k: v for k, v in patch.items() if k in allowed}
    save_settings(db, clean, actor=admin.usuario)
    org = repo.get_org_by_slug(db, "imowi")
    log_audit(
        db,
        org_id=org.id if org else "",
        actor=admin.usuario,
        accion="platform_settings_update",
        recurso="platform_config",
        detalle=f"secciones={','.join(sorted(clean.keys()))}",
    )
    return public_status(db)


@router.post("/admin/settings/test-ai")
def test_ai_connection(
    _: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    from app.services.platform_settings import resolve_ai

    cfg = resolve_ai(db)
    try:
        from openai import OpenAI

        client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"] or "ollama")
        resp = client.chat.completions.create(
            model=cfg["model"],
            messages=[{"role": "user", "content": "Respondé solo: ok"}],
            temperature=0,
            max_tokens=8,
        )
        text = (resp.choices[0].message.content or "").strip()
        return {"ok": True, "model": cfg["model"], "base_url": cfg["base_url"], "reply": text[:80]}
    except Exception as e:
        return {"ok": False, "model": cfg["model"], "base_url": cfg["base_url"], "error": str(e)[:240]}


@router.post("/admin/playbooks/convert")
def convert_playbooks_document(
    body: dict = Body(default={}),
    _: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    """Convierte texto de troubleshooting a playbooks N1 estructurados vía IA."""
    from app.services.playbook_convert import convert_document_to_playbooks

    texto = str((body or {}).get("texto") or "").strip()
    if not texto:
        raise HTTPException(400, "Campo 'texto' obligatorio")
    try:
        result = convert_document_to_playbooks(db, texto)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"Error al convertir con IA: {str(e)[:240]}") from e
    return result


@router.post("/admin/settings/test-whatsapp")
def test_whatsapp_config(
    _: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    from app.services.platform_settings import resolve_whatsapp
    from app.services.whatsapp_client import verificar_credenciales

    cfg = resolve_whatsapp(db)
    live = verificar_credenciales()
    return {
        "ok": bool(live.get("ok")),
        "phone_number_id_set": bool(cfg.get("phone_number_id")),
        "token_set": bool(cfg.get("token")),
        "verify_token": cfg.get("verify_token") or "",
        "default_org_slug": cfg.get("default_org_slug") or "",
        "display_phone_number": live.get("display_phone_number") or "",
        "verified_name": live.get("verified_name") or "",
        "quality_rating": live.get("quality_rating") or "",
        "code_verification_status": live.get("code_verification_status") or "",
        "error": live.get("error") or "",
        "webhook_url": "/api/v1/whatsapp/webhook",
        "nota": (
            "Consulta Graph API al Phone Number ID (no envía mensaje). "
            "Webhook público: https://<dominio>/api/v1/whatsapp/webhook"
        ),
    }


@router.post("/admin/settings/test-telegram")
def test_telegram_config(
    _: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    from app.services.platform_settings import resolve_telegram
    from app.services.telegram_client import get_me, get_webhook_info, telegram_configurado

    cfg = resolve_telegram(db)
    if not telegram_configurado():
        return {
            "ok": False,
            "token_set": False,
            "default_org_slug": cfg.get("default_org_slug") or "",
            "webhook_secret_set": bool(cfg.get("webhook_secret")),
            "nota": "Falta TELEGRAM_BOT_TOKEN / bot_token en settings.",
        }
    me = get_me()
    wh = get_webhook_info()
    allowed = wh.get("allowed_updates") or []
    # Si allowed_updates está vacío, Telegram envía TODO. Si está seteado, debe incluir callback_query.
    callbacks_ok = (not allowed) or ("callback_query" in allowed)
    return {
        "ok": bool(me.get("ok")),
        "token_set": True,
        "webhook_secret_set": bool(cfg.get("webhook_secret")),
        "default_org_slug": cfg.get("default_org_slug") or "",
        "bot_username": me.get("username") or "",
        "bot_id": me.get("id"),
        "error": me.get("detail") or me.get("reason") or "",
        "webhook": wh,
        "callbacks_enabled": callbacks_ok,
        "nota": (
            "OK: el webhook recibe botones CSAT."
            if callbacks_ok
            else (
                "El webhook NO recibe callback_query — re-registralo con "
                "POST /api/v1/admin/settings/telegram-webhook."
            )
        ),
    }


class TelegramWebhookIn(BaseModel):
    url: str = Field(
        default="",
        max_length=500,
        description="HTTPS público del webhook. Vacío = https://{host}/api/v1/telegram/webhook",
    )
    drop_pending: bool = False


@router.post("/admin/settings/telegram-webhook")
def register_telegram_webhook(
    body: TelegramWebhookIn,
    request: Request,
    _: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    """Re-registra el webhook incluyendo callback_query (necesario para encuesta CSAT)."""
    from app.services.platform_settings import resolve_telegram
    from app.services.telegram_client import set_webhook, telegram_configurado

    if not telegram_configurado():
        raise HTTPException(400, "Telegram no configurado (falta bot_token)")

    url = (body.url or "").strip()
    if not url:
        # Inferir desde el request (proxy) o PUBLIC_URL
        from app.config import PUBLIC_URL

        base = (PUBLIC_URL or "").strip().rstrip("/")
        if not base:
            # X-Forwarded-Proto/Host detrás de nginx
            proto = (
                request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
            ).split(",")[0].strip()
            host = (
                request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
            ).split(",")[0].strip()
            if host:
                base = f"{proto}://{host}"
        if not base:
            raise HTTPException(
                400, "Indicá url=https://tu-dominio/api/v1/telegram/webhook"
            )
        url = f"{base}/api/v1/telegram/webhook"

    cfg = resolve_telegram(db)
    result = set_webhook(
        url,
        secret_token=cfg.get("webhook_secret") or "",
        drop_pending=body.drop_pending,
    )
    if not result.get("ok"):
        raise HTTPException(400, result.get("detail") or result.get("reason") or "setWebhook falló")
    return result


@router.post("/admin/settings/test-database")
def test_database_connection(
    _: UsuarioSesion = Depends(requiere_admin),
):
    """Prueba el Data Estate activo del proceso (DATABASE_URL), no BillTrack."""
    from app.estate.health import probar_conexion_database

    result = probar_conexion_database()
    result["scope"] = "data_estate"
    result["nota"] = "Conexión del sistema (tickets/config). No es el padrón BillTrack de clientes."
    return result


@router.post("/admin/settings/test-smtp")
def test_smtp_connection(
    body: dict = Body(default={}),
    _: UsuarioSesion = Depends(requiere_admin),
):
    """Prueba SMTP: login + envío opcional a `to` (default SMTP_FROM)."""
    from app.config import SMTP_FROM
    from app.services import email as email_svc

    status = email_svc.smtp_status()
    if not status["configured"]:
        return {
            "ok": False,
            "smtp": status,
            "error": status.get("last_error")
            or "SMTP_HOST/SMTP_FROM vacíos en el proceso. Editá .env y reiniciá la API.",
        }

    to = str((body or {}).get("to") or SMTP_FROM or "").strip()
    ok = email_svc.send_email(
        to=to,
        subject="Operations Hub — prueba SMTP",
        body_text=(
            "Este es un email de prueba desde Operations Hub.\n"
            "Si lo recibiste, SMTP está funcionando.\n"
        ),
        html="<p>Este es un email de prueba desde <strong>Operations Hub</strong>.</p>",
    )
    return {
        "ok": ok,
        "to": to,
        "smtp": email_svc.smtp_status(),
        "error": None if ok else (email_svc.get_last_error() or "Fallo al enviar"),
    }


@router.post("/admin/settings/test-billtrack")
def test_billtrack_connection(
    body: dict = Body(default={}),
    _: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    """Prueba el Postgres externo BillTrack (consulta de clientes para el bot)."""
    from app.estate.health import probar_conexion_database
    from app.services.billtrack import connection_params
    from app.services.platform_settings import resolve_billtrack

    payload = body if isinstance(body, dict) else {}
    cfg = resolve_billtrack(db)

    # Overlay del formulario (password enmascarada → se conserva la guardada)
    for key in ("host", "port", "user", "password", "dbname", "url", "sslmode"):
        if key in payload and payload.get(key) is not None:
            val = payload.get(key)
            if key == "password" and "***" in str(val or ""):
                continue
            if key == "url" and "***" in str(val or ""):
                continue
            cfg[key] = val

    params = connection_params(cfg)
    url = str(params.get("url") or cfg.get("url") or "").strip()
    sslmode = str(params.get("sslmode") or "disable")
    host = str(params.get("host") or cfg.get("host") or "").strip()
    port = params.get("port") or cfg.get("port") or 5432

    if not url and not (cfg.get("host") and cfg.get("user")):
        return {
            "ok": False,
            "connected": False,
            "scope": "billtrack",
            "error": "BillTrack sin host/usuario (o URL) configurado",
            "hint": "Completá host, puerto, usuario, contraseña y nombre de base. SSL: disable.",
            "nota": "Postgres externo de solo lectura para validar clientes. Independiente del Data Estate.",
        }

    if not url:
        return {
            "ok": False,
            "connected": False,
            "scope": "billtrack",
            "error": "Falta la contraseña para armar la conexión",
            "hint": "Reingresá la contraseña (no se puede probar con el valor enmascarado si nunca se guardó).",
        }

    # Preflight TCP: falla claro si el proceso del API no tiene ruta (VPN) al host
    from app.services.billtrack import preflight_tcp

    tcp = preflight_tcp(host, port)
    if host and not tcp.get("tcp_ok"):
        return {
            "ok": False,
            "connected": False,
            "scope": "billtrack",
            "tcp_ok": False,
            "sslmode": sslmode,
            "error": f"TCP no alcanza {host}:{tcp.get('port')}: {tcp.get('error') or 'sin ruta'}",
            "hint": tcp.get("hint")
            or (
                "Activá la VPN (WireGuard) en la máquina donde corre el API, "
                "o ejecutá el backend en local — no en Render/cloud."
            ),
            "nota": (
                "Postgres externo de solo lectura (padrón de clientes). "
                "No es la base del sistema ni debe usarse para persistir tickets."
            ),
        }

    result = probar_conexion_database(url, sslmode=sslmode)
    result["scope"] = "billtrack"
    result["sslmode"] = sslmode
    result["tcp_ok"] = True
    result["nota"] = (
        "Postgres externo de solo lectura (padrón de clientes). "
        "No es la base del sistema ni debe usarse para persistir tickets."
    )
    return result
