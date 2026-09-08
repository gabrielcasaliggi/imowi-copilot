"""Oficina Virtual Batán — deep-links autenticados (patrón jsat-get-link-ov).

Auth de servicio vía /session/login + /session/check; link abonado vía
GET /ov/link?celular=&path= con header sid.

Credenciales solo por env / platform settings — nunca hardcode.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

logger = logging.getLogger("operations_hub")


def _response_json(r: httpx.Response) -> Any:
    """Parsea JSON tolerando UTF-8 y Latin-1/CP1252 (OV a veces manda ó como 0xf3)."""
    raw = r.content or b""
    if not raw:
        return {}
    # Charset declarado (si viene) → utf-8 → latin-1 (nunca falla a nivel bytes).
    candidates: list[str] = []
    declared = (r.charset_encoding or r.encoding or "").strip().lower()
    for enc in (declared, "utf-8", "utf-8-sig", "latin-1", "cp1252"):
        if enc and enc not in candidates:
            candidates.append(enc)
    last_err: Exception | None = None
    for enc in candidates:
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError as exc:
            last_err = exc
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            last_err = exc
            continue
    if last_err:
        raise last_err
    return {}

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
    """Settings OV: Session dada, o una corta a DB (Admin), o solo env."""
    from app.services.platform_settings import resolve_ov_batan as _resolve

    if db is not None:
        return _resolve(db)
    session = None
    try:
        from app.estate.database import get_session_factory

        session = get_session_factory()()
        return _resolve(session)
    except Exception:
        logger.debug("OV settings: sin DB usable; solo env", exc_info=True)
        return _resolve(None)
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass


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
                data = _response_json(r) if r.content else {}
                if r.is_success and str(data.get("status") or "").upper() == "OK":
                    return sid
            except Exception:
                logger.debug("OV session/check falló; se renueva SID", exc_info=True)

        login_url = f"{api}/session/login?user={quote(user)}&password={quote(password)}"
        r = httpx.post(login_url, timeout=timeout)
        r.raise_for_status()
        data = _response_json(r) if r.content else {}
        result = data.get("result") if isinstance(data, dict) else None
        new_sid = ""
        if isinstance(result, dict):
            new_sid = str(result.get("sid") or "").strip()
        if not new_sid:
            raise RuntimeError("OV login sin sid")
        _cached_sid = new_sid
        return new_sid


def variantes_celular_ov(celular: str) -> list[str]:
    """Formatos a probar en /ov/link.

    Botmaker manda el MSISDN completo ``549…``. Probar primero sin ``54`` devolvía
    un tsid «OK» pero al abrir: «usuario NO TIENE asociado ningún cliente».
    Orden: E.164 completo (549) → nacional / local como fallback.
    """
    from app.estate.canal_repo import normalizar_telefono

    dig = normalizar_telefono(celular or "")
    if not dig or len(dig) < 8:
        return []

    out: list[str] = []

    def _add(raw: str) -> None:
        n = re.sub(r"\D", "", raw or "")
        if n and len(n) >= 8 and n not in out:
            out.append(n)

    # 1) Como Botmaker / WhatsApp Meta
    _add(dig)
    if dig.startswith("54") and len(dig) > 10:
        sin54 = dig[2:]
        _add(sin54)
        if sin54.startswith("9") and len(sin54) >= 11:
            _add(sin54[1:])
        elif len(sin54) == 10:
            _add("9" + sin54)
        if len(sin54) >= 10:
            _add("0" + (sin54[1:] if sin54.startswith("9") else sin54))
    return out


def _link_ov_usable(link: str, *, celular_pedido: str = "") -> bool:
    """Solo aceptamos tsid pedidos con MSISDN ``54…`` (estilo Botmaker).

    Pedir sin ``54`` a veces devuelve link con ``user=549…`` pero al abrir:
    «usuario NO TIENE asociado ningún cliente».
    """
    u = (link or "").strip()
    if not u or "tsid=" not in u.lower():
        return False
    ped = re.sub(r"\D", "", celular_pedido or "")
    if ped and not ped.startswith("54"):
        return False
    return True


def candidatos_celular_ov(
    abonado: Any | None = None,
    *,
    canal: str = "",
    wa_id: str = "",
    telefono_hilo: str = "",
) -> list[str]:
    """Celulares a probar en /ov/link (orden = prioridad).

    WhatsApp: MSISDN del hilo primero (Botmaker / PLATFORM_CONTACT_ID), luego padrón.
    Portal: padrón + celular del hilo post-login.
    """
    from app.estate.canal_repo import normalizar_telefono

    out: list[str] = []

    def _add(raw: Any) -> None:
        n = normalizar_telefono(str(raw or ""))
        if n and len(n) >= 8 and n not in out:
            if n.startswith("guest") or not n.isdigit():
                return
            out.append(n)

    canal_l = (canal or "").strip().lower()
    # WA: mismo criterio que Botmaker (el número del chat es el de OV).
    if canal_l == "whatsapp":
        _add(wa_id)
        _add(telefono_hilo)
    if abonado is not None:
        _add(getattr(abonado, "telefono_e164", None))
        _add(getattr(abonado, "linea_msisdn", None))
    if canal_l in ("web", "app", "simulate"):
        hilo = str(telefono_hilo or wa_id or "").strip()
        if hilo and not hilo.lower().startswith("guest"):
            _add(hilo)
            _add(wa_id)
    return out


def resolver_celular_ov(
    abonado: Any | None = None,
    *,
    canal: str = "",
    wa_id: str = "",
    telefono_hilo: str = "",
) -> str:
    """Primer celular candidato para /ov/link (compat)."""
    cands = candidatos_celular_ov(
        abonado, canal=canal, wa_id=wa_id, telefono_hilo=telefono_hilo
    )
    return cands[0] if cands else ""


def get_fast_link(
    path: str,
    celular: str,
    *,
    db: Session | None = None,
) -> str | None:
    """Deep-link autenticado o None si OV no está listo / falla.

    ``celular`` se usa tal cual (solo dígitos): no re-agregar ``54`` acá,
    porque OV a menudo exige formato nacional sin país.
    """
    cel = re.sub(r"\D", "", celular or "")
    path_n = (path or "").strip()
    if not cel or not path_n:
        return None
    if not ov_configurado(db):
        logger.info("OV get_fast_link: no configurado (enabled/user/pass)")
        return None

    cfg = resolve_ov_batan(db)
    api = str(cfg.get("api_url") or "").rstrip("/")
    timeout = float(cfg.get("timeout") or 20)
    try:
        sid = _ensure_sid(cfg)
        url = f"{api}/ov/link?celular={quote(cel)}&path={quote(path_n, safe='?=&')}"
        r = httpx.get(url, headers={"sid": sid}, timeout=timeout)
        data = _response_json(r) if r.content else {}
        if not r.is_success or str(data.get("status") or "").upper() != "OK":
            logger.info(
                "OV /ov/link no OK status_http=%s body_status=%s cel_len=%s pref=%s",
                r.status_code,
                data.get("status"),
                len(cel),
                cel[:3] if cel else "",
            )
            return None
        link = data.get("result")
        if isinstance(link, dict):
            link = link.get("url") or link.get("link") or link.get("href")
        if link is None:
            return None
        out = str(link).strip()
        if out and not _link_ov_usable(out, celular_pedido=cel):
            logger.info(
                "OV /ov/link descartado (user= huérfano?) cel_len=%s pref=%s",
                len(cel),
                cel[:3],
            )
            return None
        if out:
            logger.info(
                "OV /ov/link OK cel_len=%s pref=%s path=%s",
                len(cel),
                cel[:3],
                path_n[:24],
            )
        return out or None
    except Exception:
        logger.exception("OV get_fast_link falló (cel_len=%s)", len(cel))
        return None


def fast_or_public(
    path: str,
    celular: str = "",
    *,
    db: Session | None = None,
    celulares: list[str] | None = None,
) -> str:
    """Prefiere deep-link; prueba varios celulares/formatos; si no, hash público."""
    cfg = resolve_ov_batan(db)
    public_base = str(cfg.get("public_url") or "https://ov.batan.coop").rstrip("/")
    cands: list[str] = []
    for raw in list(celulares or []) + ([celular] if celular else []):
        for v in variantes_celular_ov(str(raw or "")):
            if v not in cands:
                cands.append(v)
    # Preferir respuesta pedida con 549… (Botmaker); si varias OK, la primera usable.
    for cel in cands:
        fast = get_fast_link(path, cel, db=db)
        if fast:
            return fast
    if cands:
        logger.info(
            "OV fast_or_public: fallback hash público path=%s cands=%s",
            (path or "")[:40],
            len(cands),
        )
    else:
        logger.info(
            "OV fast_or_public: sin celular → hash público path=%s", (path or "")[:40]
        )
    return public_url(path, public_base=public_base)


def urls_ov_gestiones(
    celular: str = "",
    *,
    db: Session | None = None,
    celulares: list[str] | None = None,
) -> dict[str, str]:
    """URLs de gestiones OV (fast-link si hay celular + API; si no, públicas)."""
    cfg = resolve_ov_batan(db)
    public_base = str(cfg.get("public_url") or "https://ov.batan.coop").rstrip("/")
    cands = [c for c in (celulares or []) if str(c or "").strip()]
    if celular and celular not in cands:
        cands = [celular, *cands]

    def _one(path: str) -> str:
        if cands:
            return fast_or_public(path, "", db=db, celulares=cands)
        return public_url(path, public_base=public_base)

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


def probe_ov_batan(
    *,
    api_url: str,
    user: str,
    password: str,
    timeout: float = 20,
    public_url: str = "https://ov.batan.coop",
    celular: str = "",
) -> dict[str, Any]:
    """Prueba login (+ opcional /ov/link). No usa settings de DB."""
    import time

    clear_sid_cache()
    cfg = {
        "enabled": True,
        "api_url": (api_url or "").rstrip("/"),
        "public_url": (public_url or "").rstrip("/") or "https://ov.batan.coop",
        "user": (user or "").strip(),
        "password": (password or "").strip(),
        "timeout": float(timeout or 20),
    }
    if not cfg["api_url"]:
        return {"ok": False, "error": "Falta la URL de la API OV", "hint": "Ej.: https://ov.batan.coop/api"}
    if not cfg["user"] or not cfg["password"]:
        return {
            "ok": False,
            "error": "Faltan usuario o password de servicio OV",
            "hint": "Pegá OV_BATAN_API_USER / PASSWORD o guardalos en esta sección.",
        }
    t0 = time.monotonic()
    try:
        sid = _ensure_sid(cfg)
    except Exception as exc:
        err = str(exc)[:240]
        hint = "Revisá usuario/clave y que el host OV sea alcanzable desde el API."
        low = err.lower()
        if "codec" in low or "decode" in low or "utf-8" in low:
            hint = (
                "La OV respondió con encoding no-UTF8; si sigue tras actualizar, "
                "revisá que la URL apunte a /api y no a una página HTML."
            )
        elif "401" in err or "403" in err or "password" in low:
            hint = "Credenciales rechazadas por /session/login."
        elif "timed out" in low or "timeout" in low:
            hint = "OV no respondió a tiempo."
        return {"ok": False, "error": err, "hint": hint, "api_url": cfg["api_url"]}
    latency_ms = int((time.monotonic() - t0) * 1000)
    fast = None
    cel_ok = ""
    cel = (celular or "").strip()
    if cel:
        last_err = ""
        for cel_n in variantes_celular_ov(cel):
            try:
                url = (
                    f"{cfg['api_url']}/ov/link"
                    f"?celular={quote(cel_n)}&path={quote(PATH_PAGAR, safe='?=&')}"
                )
                r = httpx.get(url, headers={"sid": sid}, timeout=cfg["timeout"])
                data = _response_json(r) if r.content else {}
                if r.is_success and str(data.get("status") or "").upper() == "OK":
                    link = data.get("result")
                    if isinstance(link, dict):
                        link = link.get("url") or link.get("link") or link.get("href")
                    fast = str(link or "").strip() or None
                    if fast:
                        cel_ok = cel_n
                        break
                last_err = f"/ov/link no OK ({data.get('status') or r.status_code}) cel_len={len(cel_n)}"
            except Exception as exc:
                last_err = str(exc)[:240]
        if not fast:
            return {
                "ok": False,
                "authenticated": True,
                "latency_ms": latency_ms,
                "api_url": cfg["api_url"],
                "error": last_err or "/ov/link sin link",
                "hint": (
                    "Sesión OK; probamos formatos sin 54 / local. "
                    "Revisá que el celular exista en OV."
                ),
                "variantes_probadas": variantes_celular_ov(cel),
            }
    return {
        "ok": True,
        "authenticated": True,
        "latency_ms": latency_ms,
        "api_url": cfg["api_url"],
        "fast_link": fast,
        "celular_ok": cel_ok or None,
    }
