"""Envío de email vía SMTP (invites consola + OTP portal)."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import (
    PUBLIC_URL,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_SSL,
    SMTP_TLS,
    SMTP_USER,
    es_produccion,
)

logger = logging.getLogger("operations_hub.email")

# Bandeja en memoria para tests / dev sin SMTP
_OUTBOX: list[dict] = []
_LAST_ERROR: str = ""


def smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_FROM)


def smtp_status() -> dict:
    """Diagnóstico liviano de config SMTP (sin secretos)."""
    return {
        "configured": smtp_configured(),
        "host": SMTP_HOST or "",
        "port": SMTP_PORT,
        "user": SMTP_USER or "",
        "from": SMTP_FROM or "",
        "tls": SMTP_TLS,
        "ssl": SMTP_SSL,
        "public_url": PUBLIC_URL or "",
        "last_error": _LAST_ERROR or None,
    }


def clear_outbox() -> None:
    _OUTBOX.clear()


def get_outbox() -> list[dict]:
    return list(_OUTBOX)


def get_last_error() -> str:
    return _LAST_ERROR


def _set_error(msg: str) -> None:
    global _LAST_ERROR
    _LAST_ERROR = (msg or "").strip()


def send_email(*, to: str, subject: str, body_text: str, html: str | None = None) -> bool:
    """Envía email. Sin SMTP en non-prod: guarda en outbox y loguea. En prod sin SMTP: False."""
    global _LAST_ERROR
    to_addr = (to or "").strip()
    if not to_addr:
        _set_error("Destinatario vacío")
        return False

    record = {"to": to_addr, "subject": subject, "body": body_text, "html": html or ""}
    _OUTBOX.append(record)

    if not smtp_configured():
        logger.info(
            "SMTP no configurado — email simulado to=%s subject=%s",
            to_addr,
            subject,
        )
        if es_produccion():
            _set_error(
                "SMTP no configurado en el proceso API (SMTP_HOST/SMTP_FROM). "
                "Verificá /opt/operations-hub/.env y reiniciá operations-hub-api"
            )
            return False
        _set_error("")
        return True

    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body_text)
    if html:
        msg.add_alternative(html, subtype="html")

    try:
        ctx = ssl.create_default_context()
        if SMTP_SSL:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20, context=ctx) as server:
                if SMTP_USER:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
                server.ehlo()
                if SMTP_TLS:
                    server.starttls(context=ctx)
                    server.ehlo()
                if SMTP_USER:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        logger.info("Email enviado to=%s subject=%s", to_addr, subject)
        _set_error("")
        return True
    except Exception as exc:
        _set_error(f"{type(exc).__name__}: {exc}")
        logger.exception("Error enviando email: %s", exc)
        return False


def send_invite_email(*, to: str, nombre: str, org_nombre: str, token: str, rol: str) -> bool:
    base = PUBLIC_URL or "http://localhost:3000"
    link = f"{base}/invite?token={token}"
    subject = f"Invitación a Operations Hub — {org_nombre}"
    body = (
        f"Hola {nombre or to},\n\n"
        f"Te invitaron a Operations Hub ({org_nombre}) con rol «{rol}».\n"
        f"Para activar tu cuenta y definir tu contraseña, abrí:\n\n{link}\n\n"
        f"El enlace vence en 72 horas.\n"
    )
    html = (
        f"<p>Hola {nombre or to},</p>"
        f"<p>Te invitaron a <strong>Operations Hub</strong> ({org_nombre}) "
        f"con rol <strong>{rol}</strong>.</p>"
        f'<p><a href="{link}">Activar cuenta y definir contraseña</a></p>'
        f"<p>El enlace vence en 72 horas.</p>"
    )
    return send_email(to=to, subject=subject, body_text=body, html=html)


def send_password_reset_email(*, to: str, nombre: str, org_nombre: str, token: str) -> bool:
    base = PUBLIC_URL or "http://localhost:3000"
    link = f"{base}/invite?token={token}"
    subject = f"Restablecer contraseña — {org_nombre}"
    body = (
        f"Hola {nombre or to},\n\n"
        f"Recibimos un pedido para restablecer tu contraseña en Operations Hub ({org_nombre}).\n"
        f"Para elegir una nueva contraseña, abrí:\n\n{link}\n\n"
        f"El enlace vence en 24 horas. Si no lo pediste, ignorá este mensaje.\n"
    )
    html = (
        f"<p>Hola {nombre or to},</p>"
        f"<p>Pedido de restablecimiento de contraseña en "
        f"<strong>Operations Hub</strong> ({org_nombre}).</p>"
        f'<p><a href="{link}">Definir nueva contraseña</a></p>'
        f"<p>El enlace vence en 24 horas. Si no lo pediste, ignorá este mensaje.</p>"
    )
    return send_email(to=to, subject=subject, body_text=body, html=html)


def invite_public_link(token: str) -> str:
    base = PUBLIC_URL or "http://localhost:3000"
    return f"{base}/invite?token={token}"


def send_otp_email(*, to: str, otp: str, org_nombre: str, ttl_minutes: int) -> bool:
    subject = f"Código de acceso — {org_nombre}"
    body = (
        f"Tu código de verificación del portal es: {otp}\n\n"
        f"Válido por {ttl_minutes} minutos. Si no solicitaste este código, ignorá este mensaje.\n"
    )
    html = (
        f"<p>Tu código de verificación del portal es:</p>"
        f"<p style='font-size:24px;letter-spacing:4px'><strong>{otp}</strong></p>"
        f"<p>Válido por {ttl_minutes} minutos.</p>"
    )
    return send_email(to=to, subject=subject, body_text=body, html=html)
