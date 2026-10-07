"""H28: ningún secreto sale en los logs (ver docs/LOGS-SIN-SECRETOS.md).

``redactar`` enmascara el valor de parámetros sensibles en texto libre: query strings y formularios (``token=…``),
JSON/dict (``"password": "…"``), headers (``Authorization: Bearer …``), la contraseña de una URL
(``scheme://user:pass@host``), el token del bot de Telegram en el path (``/bot<id>:<token>/``) y JWT sueltos.
Las claves no distinguen mayúsculas. ``instalar_redaccion_logs`` lo aplica a todo registro al crearlo (factory de
LogRecord), así lo ve cualquier handler (consola/journal, uvicorn, Sentry, caplog), y baja httpx/httpcore a WARNING.
"""

from __future__ import annotations

import logging
import re
from typing import Any

MASK = "***"

# Claves sensibles. «token»/«clave» no toman el plural («total_tokens=…», «claves=…» no son secretos).
_CLAVE = (
    r"(?:[\w.-]*(?:contrase(?:n|ñ|%c3%b1)a|passw(?:or)?d|secret|token(?!s)|api[_-]?key|apikey|clave(?!s))[\w.-]*"
    r"|pass|pwd|key|authorization|x-auth-token|celular|telefono|msisdn)"
)
_RE_CLAVE = re.compile(rf"^{_CLAVE}$", re.I)
# clave=valor / clave: valor / "clave": "valor" / 'clave': 'valor'. El valor corta en separadores de query, comillas,
# espacios y cierres; «Bearer »/«Basic » se conservan y se enmascara lo que sigue.
_RE_PARAM = re.compile(
    rf"(?<![\w.%-])([\"']?)({_CLAVE})\1(\s*[=:]\s*)([\"']?)((?:bearer|basic)\s+)?([^\s&\"',;)}}\]<>]+)",
    re.I,
)
_RE_URL_USERINFO = re.compile(r"(://[^/\s:@]+:)([^@\s/]+)(@)")
_RE_TELEGRAM_BOT = re.compile(r"(/bot)(\d+:[\w-]+)")
_RE_JWT = re.compile(r"\beyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}")


def es_clave_sensible(nombre: Any) -> bool:
    return bool(_RE_CLAVE.match(str(nombre or "").strip()))


def redactar(texto: Any) -> str:
    """Copia de ``texto`` con los valores sensibles reemplazados por ``***``."""
    s = str(texto if texto is not None else "")
    if not s:
        return s
    s = _RE_PARAM.sub(lambda m: f"{m[1]}{m[2]}{m[1]}{m[3]}{m[4]}{m[5] or ''}{MASK}", s)
    s = _RE_URL_USERINFO.sub(rf"\1{MASK}\3", s)
    s = _RE_TELEGRAM_BOT.sub(rf"\1{MASK}", s)
    return _RE_JWT.sub(MASK, s)


def redactar_registro(record: logging.LogRecord) -> None:
    """Enmascara mensaje (ya formateado con sus args), traza de excepción y stack de ``record``, en el lugar."""
    try:
        msg = record.getMessage()
    except Exception:  # noqa: BLE001 — un log mal formado no se rompe acá; lo reporta el handler
        _redactar_traza(record)
        return
    red = redactar(msg)
    if red != msg:
        # Primero arg por arg: hay formatters que desempaquetan ``record.args`` (el access log de uvicorn). Si el secreto
        # queda partido entre el formato y un arg («Authorization: Bearer %s»), se reemplaza el mensaje ya formateado.
        args = record.args
        if isinstance(args, tuple) and args:
            nuevos = tuple(_redactar_arg(a) for a in args)
            try:
                formateado = str(record.msg) % nuevos
            except Exception:  # noqa: BLE001
                formateado = None
            if formateado is not None and redactar(formateado) == formateado:
                record.args = nuevos
                _redactar_traza(record)
                return
        record.msg, record.args = red, None
    _redactar_traza(record)


def _redactar_arg(a: Any) -> Any:
    if isinstance(a, str):
        return redactar(a)
    if a is None or isinstance(a, (int, float)):
        return a
    s = str(a)
    r = redactar(s)
    return a if r == s else r


def _redactar_traza(record: logging.LogRecord) -> None:
    if record.exc_info and not record.exc_text:
        try:
            record.exc_text = redactar(logging.Formatter().formatException(record.exc_info))
        except Exception:  # noqa: BLE001
            pass
    elif record.exc_text:
        record.exc_text = redactar(record.exc_text)
    if record.stack_info:
        record.stack_info = redactar(record.stack_info)


class SecretRedactingFilter(logging.Filter):
    """Filtro que enmascara secretos; siempre deja pasar el registro."""

    def filter(self, record: logging.LogRecord) -> bool:
        redactar_registro(record)
        return True


_FILTRO = SecretRedactingFilter()
_LOGGERS_RUIDOSOS = ("httpx", "httpcore")


def instalar_redaccion_logs() -> None:
    """Idempotente. Llamar al arranque (y después de cualquier ``basicConfig``/``fileConfig`` que toque niveles)."""
    for nombre in _LOGGERS_RUIDOSOS:  # httpx loguea en INFO la URL completa de cada request
        logging.getLogger(nombre).setLevel(logging.WARNING)
    previa = logging.getLogRecordFactory()
    if getattr(previa, "_redacta_secretos", False):
        return

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = previa(*args, **kwargs)
        _FILTRO.filter(record)
        return record

    factory._redacta_secretos = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(factory)


def redactar_evento_sentry(event: dict[str, Any], _hint: Any = None) -> dict[str, Any]:
    """``before_send``: mensajes y valores de excepción sin secretos."""
    for exc in (event.get("exception") or {}).get("values") or []:
        if isinstance(exc, dict) and exc.get("value"):
            exc["value"] = redactar(exc["value"])
    le = event.get("logentry")
    if isinstance(le, dict):
        for k in ("message", "formatted"):
            if le.get(k):
                le[k] = redactar(le[k])
    if event.get("message"):
        event["message"] = redactar(event["message"])
    return event


def redactar_breadcrumb_sentry(crumb: dict[str, Any], _hint: Any = None) -> dict[str, Any]:
    """``before_breadcrumb``: la integración httpx de Sentry guarda la URL y su query."""
    if crumb.get("message"):
        crumb["message"] = redactar(crumb["message"])
    data = crumb.get("data")
    if isinstance(data, dict):
        for k in ("url", "http.query", "http.fragment"):
            if data.get(k):
                data[k] = redactar(data[k])
    return crumb
