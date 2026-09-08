"""Oficina Virtual Batán — deep-links autenticados (patrón jsat-get-link-ov).

Auth de servicio vía /session/login + /session/check; link abonado vía
GET /ov/link?celular=&path= con header sid.

Credenciales solo por env / platform settings — nunca hardcode.
"""

from __future__ import annotations

import logging
import threading
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

logger = logging.getLogger("operations_hub")

# Paths de Client Action jsat-get-link-ov (Botmaker).
PATH_MY = "my?useCustomer=true"
PATH_TALON = "talon-de-pago?useCustomer=true"
PATH_PAGAR = "pagar?useCustomer=true"
# Typo histórico en Botmaker: userCustomer (no useCustomer).
PATH_COMPRAR_PACK = "comprar-pack?userCustomer=true"
PATH_PORTABILIDAD = "portabilidad?useCustomer=true"

PUBLIC_HASH = {
    PATH_MY: "my",
    PATH_TALON: "talon-de-pago",
    PATH_PAGAR: "pagar",
    PATH_COMPRAR_PACK: "comprar-pack",
    PATH_PORTABILIDAD: "portabilidad",
}

_sid_lock = threading.Lock()
_cached_sid: str = ""


def public_url(path: str, *, public_base: str = "") -> str:
    """Fallback sin sesión: hash público de la OV."""
    base = (public_base or "https://ov.batan.coop").rstrip("/")
    raw = (path or "").strip()
    hash_part = PUBLIC_HASH.get(raw)
    if not hash_part:
        # path tipo "pagar?useCustomer=true" → "pagar"
        hash_part = raw.split("?", 1)[0].strip() or "pagar"
    return f"{base}/#/{hash_part}"


def resolve_ov_batan(db: Session | None = None) -> dict[str, Any]:
    from app.services.platform_settings import resolve_ov_batan as _resolve

    return _resolve(db)


def ov_configurado(db: Session | None = None) -> bool:
    cfg = resolve_ov_batan(db)
    return bool(
        cfg.get("enabled")
        and str(cfg.get("api_url") or "").strip()
        and str(cfg.get("user") or "").strip()
        and str(cfg.get("password") or "").strip()
    )


def _ensure_sid(cfg: dict[str, Any]) -> str:
    """SID de servicio (proceso); renueva si check falla."""
    global _cached_sid
    api = str(cfg.get("api_url") or "").rstrip("/")
    timeout = float(cfg.get("timeout") or 20)
    user = str(cfg.get("user") or "")
    password = str(cfg.get("password") or "")

    with _sid_lock:
        sid = _cached_sid
        if sid:
            try:
                r = httpx.get(
                    f"{api}/session/check",
                    headers={"sid": sid},
                    timeout=timeout,
                )
                data = r.json() if r.content else {}
                if r.is_success and str(data.get("status") or "").upper() == "OK":
                    return sid
            except Exception:
                logger.debug("OV session/check falló; se renueva SID", exc_info=True)

        login_url = f"{api}/session/login?user={quote(user)}&password={quote(password)}"
        r = httpx.post(login_url, timeout=timeout)
        r.raise_for_status()
        data = r.json() if r.content else {}
        result = data.get("result") if isinstance(data, dict) else None
        new_sid = ""
        if isinstance(result, dict):
            new_sid = str(result.get("sid") or "").strip()
        if not new_sid:
            raise RuntimeError("OV login sin sid")
        _cached_sid = new_sid
        return new_sid


def get_fast_link(
    path: str,
    celular: str,
    *,
    db: Session | None = None,
) -> str | None:
    """Deep-link autenticado o None si OV no está listo / falla."""
    from app.estate.canal_repo import normalizar_telefono

    cel = normalizar_telefono(celular or "")
    path_n = (path or "").strip()
    if not cel or not path_n:
        return None
    if not ov_configurado(db):
        return None

    cfg = resolve_ov_batan(db)
    api = str(cfg.get("api_url") or "").rstrip("/")
    timeout = float(cfg.get("timeout") or 20)
    try:
        sid = _ensure_sid(cfg)
        url = f"{api}/ov/link?celular={quote(cel)}&path={quote(path_n, safe='?=&')}"
        r = httpx.get(url, headers={"sid": sid}, timeout=timeout)
        data = r.json() if r.content else {}
        if not r.is_success or str(data.get("status") or "").upper() != "OK":
            logger.info(
                "OV /ov/link no OK status_http=%s body_status=%s",
                r.status_code,
                data.get("status"),
            )
            return None
        link = data.get("result")
        if link is None:
            return None
        out = str(link).strip()
        return out or None
    except Exception:
        logger.exception("OV get_fast_link falló (cel=***%s)", cel[-4:] if cel else "")
        return None


def fast_or_public(
    path: str,
    celular: str,
    *,
    db: Session | None = None,
) -> str:
    """Prefiere deep-link; si no, hash público."""
    cfg = resolve_ov_batan(db)
    public_base = str(cfg.get("public_url") or "https://ov.batan.coop").rstrip("/")
    cel = (celular or "").strip()
    if cel:
        fast = get_fast_link(path, cel, db=db)
        if fast:
            return fast
    return public_url(path, public_base=public_base)


def resolver_celular_ov(
    abonado: Any | None = None,
    *,
    canal: str = "",
    wa_id: str = "",
    telefono_hilo: str = "",
) -> str:
    """Celular para /ov/link: padrón del abonado; en WA sin padrón, MSISDN del hilo.

    Multi-canal: web/app/telegram usan el teléfono BillTrack de la cuenta identificada.
    """
    from app.estate.canal_repo import normalizar_telefono

    if abonado is not None:
        for raw in (
            getattr(abonado, "telefono_e164", None),
            getattr(abonado, "linea_msisdn", None),
        ):
            n = normalizar_telefono(str(raw or ""))
            if n and len(n) >= 8:
                return n
    if (canal or "").strip().lower() == "whatsapp":
        for raw in (wa_id, telefono_hilo):
            n = normalizar_telefono(str(raw or ""))
            if n and len(n) >= 8:
                return n
    return ""


def urls_ov_gestiones(
    celular: str = "",
    *,
    db: Session | None = None,
) -> dict[str, str]:
    """URLs de gestiones OV (fast-link si hay celular + API; si no, públicas)."""
    cfg = resolve_ov_batan(db)
    public_base = str(cfg.get("public_url") or "https://ov.batan.coop").rstrip("/")
    cel = (celular or "").strip()

    def _one(path: str) -> str:
        return fast_or_public(path, cel, db=db) if cel else public_url(
            path, public_base=public_base
        )

    return {
        "pagar": _one(PATH_PAGAR),
        "talon": _one(PATH_TALON),
        "my": _one(PATH_MY),
        "pack": _one(PATH_COMPRAR_PACK),
        "portabilidad": _one(PATH_PORTABILIDAD),
        "home": public_base,
    }


def clear_sid_cache() -> None:
    """Tests / rotación forzada."""
    global _cached_sid
    with _sid_lock:
        _cached_sid = ""
