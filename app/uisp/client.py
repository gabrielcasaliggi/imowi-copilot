"""Cliente HTTP contra UISP NMS (dispositivos radio). Solo lectura.

Auth: header `x-auth-token` (Settings → Users → API tokens, rol Read Only).
El nombre del CPE (`identification.name`) coincide con el username Radius.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.uisp.contract import CalidadSenal, EstadoCpeUisp

logger = logging.getLogger("operations_hub")

DEFAULT_BASE_URL = "https://uisp.ecolan.com"
DEFAULT_API_PREFIX = "/nms/api/v2.1"
DEVICE_CACHE_TTL_SEC = 90.0

_ONLINE_STATUS = frozenset({"active", "online", "connected", "ok", "up"})
_OFFLINE_STATUS = frozenset(
    {
        "disconnected",
        "inactive",
        "offline",
        "down",
        "unauthorized",
        "unknown",
        "unreachable",
        "disabled",
    }
)

# Cache por proceso: {cache_key: {"ts": float, "by_name": dict[str, dict]}}
_DEVICE_CACHE: dict[str, dict[str, Any]] = {}


def _first_str(*vals: Any) -> str:
    for v in vals:
        if v is None:
            continue
        s = str(v).strip()
        if s and s.lower() not in ("none", "null", "undefined"):
            return s
    return ""


def normalizar_nombre_cpe(value: str) -> str:
    """Username Radius y nombre UISP: casefold, sin espacios extra."""
    return "".join((value or "").strip().casefold().split())


def clasificar_senal(dbm: float | None) -> CalidadSenal:
    if dbm is None:
        return ""
    if dbm >= -65:
        return "buena"
    if dbm >= -75:
        return "aceptable"
    return "mala"


def _as_float(val: Any) -> float | None:
    if val is None or val is False:
        return None
    if isinstance(val, bool):
        return None
    try:
        n = float(val)
    except (TypeError, ValueError):
        return None
    if n != n:  # NaN
        return None
    return n


def _as_int(val: Any) -> int | None:
    n = _as_float(val)
    if n is None:
        return None
    return int(n)


def api_root(base_url: str, api_prefix: str = DEFAULT_API_PREFIX) -> str:
    """Acepta host pelado o URL que ya incluye /nms/api/v2.1."""
    u = (base_url or "").strip().rstrip("/")
    if not u:
        return ""
    low = u.lower()
    if "/nms/api/" in low:
        return u
    prefix = (api_prefix or DEFAULT_API_PREFIX).strip() or DEFAULT_API_PREFIX
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    return u + prefix.rstrip("/")


def nombres_dispositivo(dev: dict[str, Any]) -> list[str]:
    ident = dev.get("identification") if isinstance(dev.get("identification"), dict) else {}
    out: list[str] = []
    for raw in (
        ident.get("name"),
        ident.get("hostname"),
        ident.get("displayName"),
        ident.get("nickname"),
        ident.get("nickName"),
        dev.get("name"),
        dev.get("hostname"),
    ):
        s = _first_str(raw)
        if s and s not in out:
            out.append(s)
    return out


def _status_online(dev: dict[str, Any]) -> bool | None:
    ident = dev.get("identification") if isinstance(dev.get("identification"), dict) else {}
    overview = dev.get("overview") if isinstance(dev.get("overview"), dict) else {}
    for raw in (overview.get("status"), ident.get("status"), dev.get("status")):
        s = _first_str(raw).casefold()
        if not s:
            continue
        if s in _ONLINE_STATUS:
            return True
        if s in _OFFLINE_STATUS:
            return False
    return None


def parse_device(dev: dict[str, Any], *, login: str) -> EstadoCpeUisp:
    ident = dev.get("identification") if isinstance(dev.get("identification"), dict) else {}
    overview = dev.get("overview") if isinstance(dev.get("overview"), dict) else {}
    attrs = dev.get("attributes") if isinstance(dev.get("attributes"), dict) else {}
    site = ident.get("site") if isinstance(ident.get("site"), dict) else {}
    ap = attrs.get("apDevice") if isinstance(attrs.get("apDevice"), dict) else {}

    nombres = nombres_dispositivo(dev)
    nombre = nombres[0] if nombres else login
    signal = _as_float(overview.get("signal"))
    if signal is None:
        signal = _as_float(dev.get("signal"))
    uptime = _as_int(overview.get("uptime"))
    if uptime is None:
        uptime = _as_int(dev.get("uptime"))

    return EstadoCpeUisp(
        login=login,
        encontrado=True,
        online=_status_online(dev),
        nombre=nombre,
        modelo=_first_str(ident.get("modelName"), ident.get("model"), ident.get("type")),
        mac=_first_str(ident.get("mac"), ident.get("macAddress")),
        sitio=_first_str(
            site.get("name"),
            site.get("parent", {}).get("name") if isinstance(site.get("parent"), dict) else "",
        ),
        ap_nombre=_first_str(ap.get("name")),
        signal_dbm=signal,
        calidad_senal=clasificar_senal(signal),
        uptime_seg=uptime,
        device_id=_first_str(ident.get("id"), dev.get("id")),
        raw={k: v for k, v in dev.items() if k != "overview"} | {"overview": overview},
    )


def extraer_lista_dispositivos(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("data", "items", "results", "devices"):
            nested = payload.get(key)
            if isinstance(nested, list):
                return [x for x in nested if isinstance(x, dict)]
        if isinstance(payload.get("identification"), dict) or payload.get("name"):
            return [payload]
    return []


def indexar_dispositivos(devices: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Mapa nombre normalizado → dispositivo (el primero gana; no pisa con vacío)."""
    by_name: dict[str, dict[str, Any]] = {}
    for dev in devices:
        for name in nombres_dispositivo(dev):
            key = normalizar_nombre_cpe(name)
            if key and key not in by_name:
                by_name[key] = dev
    return by_name


def buscar_en_indice(by_name: dict[str, dict[str, Any]], login: str) -> dict[str, Any] | None:
    key = normalizar_nombre_cpe(login)
    if not key:
        return None
    return by_name.get(key)


class UispNmsClient:
    """Cliente HTTP. Token solo por config/env — nunca hardcodear."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        token: str = "",
        timeout: float = 12.0,
        verify_ssl: bool = True,
        api_prefix: str = DEFAULT_API_PREFIX,
    ) -> None:
        self.base_url = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
        self.token = (token or "").strip()
        self.timeout = timeout
        self.verify_ssl = bool(verify_ssl)
        self.api_prefix = api_prefix or DEFAULT_API_PREFIX
        self.root = api_root(self.base_url, self.api_prefix)

    def configured(self) -> bool:
        return bool(self.root and self.token)

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-auth-token": self.token,
        }

    def _cache_key(self) -> str:
        return f"{self.root}|{self.token[-6:] if self.token else ''}"

    def _http_get(self, path: str) -> httpx.Response:
        if not self.configured():
            raise RuntimeError("UISP no configurado")
        url = f"{self.root}{path if path.startswith('/') else '/' + path}"
        with httpx.Client(
            timeout=self.timeout, verify=self.verify_ssl, follow_redirects=True
        ) as client:
            return client.get(url, headers=self._headers())

    def listar_dispositivos(self, *, force: bool = False) -> list[dict[str, Any]]:
        key = self._cache_key()
        now = time.monotonic()
        cached = _DEVICE_CACHE.get(key) or {}
        if (
            not force
            and cached.get("items")
            and (now - float(cached.get("ts") or 0)) < DEVICE_CACHE_TTL_SEC
        ):
            return list(cached["items"])

        r = self._http_get("/devices")
        if r.status_code == 401:
            raise RuntimeError("UISP 401: token inválido o sin permiso")
        if r.status_code == 403:
            raise RuntimeError("UISP 403: el token no tiene acceso NMS")
        if r.status_code >= 400:
            detail = (r.text or "")[:180]
            logger.warning("UISP devices HTTP %s: %s", r.status_code, detail)
            raise RuntimeError(f"UISP devices HTTP {r.status_code}")
        try:
            payload = r.json()
        except Exception as exc:
            raise RuntimeError("UISP devices: respuesta no JSON") from exc
        items = extraer_lista_dispositivos(payload)
        _DEVICE_CACHE[key] = {
            "ts": now,
            "items": items,
            "by_name": indexar_dispositivos(items),
        }
        return list(items)

    def _indice(self, *, force: bool = False) -> dict[str, dict[str, Any]]:
        key = self._cache_key()
        cached = _DEVICE_CACHE.get(key) or {}
        now = time.monotonic()
        if (
            not force
            and isinstance(cached.get("by_name"), dict)
            and cached.get("items")
            and (now - float(cached.get("ts") or 0)) < DEVICE_CACHE_TTL_SEC
        ):
            return cached["by_name"]
        self.listar_dispositivos(force=force)
        return (_DEVICE_CACHE.get(key) or {}).get("by_name") or {}

    def ping(self) -> dict[str, Any]:
        """Prueba de conexión: lista dispositivos y cuenta."""
        t0 = time.monotonic()
        items = self.listar_dispositivos(force=True)
        ms = int((time.monotonic() - t0) * 1000)
        modelos: dict[str, int] = {}
        online = 0
        for d in items:
            st = _status_online(d)
            if st is True:
                online += 1
            ident = d.get("identification") if isinstance(d.get("identification"), dict) else {}
            model = _first_str(ident.get("modelName"), ident.get("model"), ident.get("type")) or "?"
            modelos[model] = modelos.get(model, 0) + 1
        top = sorted(modelos.items(), key=lambda x: -x[1])[:5]
        return {
            "ok": True,
            "devices": len(items),
            "online": online,
            "latency_ms": ms,
            "modelos": [{"modelo": m, "n": n} for m, n in top],
        }

    def buscar_cpe_por_login(self, login: str) -> EstadoCpeUisp:
        user = (login or "").strip()
        if not user:
            return EstadoCpeUisp(login="", error="login vacío")
        if not self.configured():
            return EstadoCpeUisp(login=user, error="uisp no configurado")
        try:
            idx = self._indice()
        except Exception as exc:
            logger.exception("UISP listar dispositivos falló")
            return EstadoCpeUisp(login=user, error=str(exc)[:160])
        dev = buscar_en_indice(idx, user)
        if dev is None:
            return EstadoCpeUisp(login=user, encontrado=False)
        return parse_device(dev, login=user)


def clear_device_cache() -> None:
    _DEVICE_CACHE.clear()
