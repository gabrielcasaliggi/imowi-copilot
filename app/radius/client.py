"""Cliente HTTP contra radius.api.batan.coop (get_nas, get_all_nas, sessions, resources)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

from app.radius.contract import NasInfo, NasResourceStatus, SesionPPPoE

logger = logging.getLogger("operations_hub")

DEFAULT_BASE_URL = "https://radius.api.batan.coop"


def _dig(obj: Any, *keys: str) -> Any:
    cur = obj
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _first_str(*vals: Any) -> str:
    for v in vals:
        if v is None:
            continue
        s = str(v).strip()
        if s and s.lower() not in ("none", "null", "undefined"):
            return s
    return ""


def extract_nas_name(payload: Any) -> str:
    """Normaliza respuesta de get_nas a un identificador de NAS usable en la URL."""
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, list) and payload:
        return extract_nas_name(payload[0])
    if not isinstance(payload, dict):
        return str(payload).strip()

    direct = _first_str(
        payload.get("nas"),
        payload.get("nas_name"),
        payload.get("nasname"),
        payload.get("nasip"),
        payload.get("nas_ip"),
        payload.get("name"),
        payload.get("ip"),
        payload.get("host"),
        payload.get("hostname"),
        payload.get("result"),
        payload.get("value"),
    )
    if direct:
        return direct

    for nest_key in ("data", "result", "results", "nas", "payload", "response"):
        nested = payload.get(nest_key)
        if nested is not None and nested is not payload:
            found = extract_nas_name(nested)
            if found:
                return found
    return ""


def _session_from_dict(username: str, nas: str, item: dict[str, Any]) -> SesionPPPoE:
    # address/framed_ip = IP pública; caller-id suele ser MAC — no mezclar
    ip = _first_str(
        item.get("address"),
        item.get("framed_ip"),
        item.get("framed-ip-address"),
        item.get("framed_ip_address"),
        item.get("public_ip"),
        item.get("ip"),
        item.get("remote_address"),
    )

    uptime = _first_str(
        item.get("uptime"),
        item.get("session_time"),
        item.get("acctsessiontime"),
        item.get("duration"),
    )
    caller = _first_str(item.get("caller-id"), item.get("caller_id"), item.get("calling_station_id"))
    name = _first_str(item.get("name"), item.get("user"), item.get("username"), username)

    # Si hay dict de sesión, asumir online salvo flags explícitos
    offline_flags = (
        item.get("online") is False
        or str(item.get("state") or item.get("status") or "").strip().lower()
        in ("offline", "down", "disconnected", "inactive", "0", "false")
    )
    online = not offline_flags
    if item.get("online") is True:
        online = True

    return SesionPPPoE(
        username=name or username,
        online=online,
        nas=nas,
        public_ip=ip,
        uptime=uptime,
        caller_id=caller,
        raw=item,
    )


def parse_ppp_sessions(username: str, nas: str, payload: Any) -> SesionPPPoE:
    """Elige la mejor sesión PPP de la respuesta MikroTik/API."""
    if payload is None:
        return SesionPPPoE(username=username, online=False, nas=nas)

    if isinstance(payload, dict):
        # Errores explícitos
        err = _first_str(payload.get("error"), payload.get("detail"), payload.get("message"))
        if err and not any(
            k in payload for k in ("address", "name", "uptime", "data", "results", "sessions", "session")
        ):
            # Puede ser error real o mensaje vacío de "sin sesión"
            low = err.lower()
            if any(x in low for x in ("not found", "no session", "sin ses", "empty", "no active")):
                return SesionPPPoE(username=username, online=False, nas=nas, raw=payload)
            return SesionPPPoE(username=username, online=False, nas=nas, error=err[:160], raw=payload)

        for nest_key in ("data", "results", "sessions", "session", "ppp", "result"):
            nested = payload.get(nest_key)
            if nested is not None:
                return parse_ppp_sessions(username, nas, nested)

        # Dict plano = una sesión
        if any(k in payload for k in ("address", "name", "uptime", "caller-id", "caller_id")):
            return _session_from_dict(username, nas, payload)

        # online flag sin detalle
        if "online" in payload:
            return SesionPPPoE(
                username=username,
                online=bool(payload.get("online")),
                nas=nas,
                public_ip=_first_str(payload.get("public_ip"), payload.get("ip"), payload.get("address")),
                uptime=_first_str(payload.get("uptime")),
                raw=payload,
            )

        return SesionPPPoE(username=username, online=False, nas=nas, raw=payload)

    if isinstance(payload, list):
        if not payload:
            return SesionPPPoE(username=username, online=False, nas=nas)
        # Preferir sesión cuyo name coincida con login
        matched: list[dict[str, Any]] = []
        others: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            name = _first_str(item.get("name"), item.get("user"), item.get("username"))
            if name and name == username:
                matched.append(item)
            else:
                others.append(item)
        chosen = (matched or others or [None])[0]
        if not isinstance(chosen, dict):
            return SesionPPPoE(username=username, online=False, nas=nas, raw={"items": payload})
        return _session_from_dict(username, nas, chosen)

    return SesionPPPoE(username=username, online=False, nas=nas, raw={"value": str(payload)[:200]})


class RadiusNasClient:
    """Cliente HTTP. Credenciales solo por config/env — nunca hardcodear."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str = "",
        token: str = "",
        timeout: float = 8.0,
    ) -> None:
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = (api_key or "").strip()
        self.token = (token or "").strip()
        self.timeout = timeout

    def configured(self) -> bool:
        return bool(self.base_url and (self.token or self.api_key))

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if self.api_key:
            # Variantes comunes en APIs internas Batan
            h["X-API-KEY"] = self.api_key
            h["API_KEY"] = self.api_key
        return h

    def get_nas(self, username: str) -> str:
        user = (username or "").strip()
        if not user:
            return ""
        if not self.configured():
            raise RuntimeError("Radius API no configurada")

        url = f"{self.base_url}/radius/get_nas/"
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(url, headers=self._headers(), json={"username": user})
        if r.status_code >= 400:
            detail = (r.text or "")[:200]
            logger.warning("Radius get_nas HTTP %s: %s", r.status_code, detail)
            raise RuntimeError(f"get_nas HTTP {r.status_code}")
        try:
            data = r.json()
        except Exception:
            text = (r.text or "").strip()
            if text:
                return text.splitlines()[0].strip()
            return ""
        nas = extract_nas_name(data)
        if not nas:
            logger.info("Radius get_nas sin NAS para user=***%s", user[-3:] if len(user) >= 3 else "***")
        return nas

    def list_ppp_session(self, nas: str, login: str) -> SesionPPPoE:
        nas_s = (nas or "").strip()
        login_s = (login or "").strip()
        if not login_s:
            return SesionPPPoE(username="", online=False, error="login vacío")
        if not nas_s:
            return SesionPPPoE(username=login_s, online=False, error="NAS vacío")
        if not self.configured():
            raise RuntimeError("Radius API no configurada")

        path = (
            f"{self.base_url}/mikrotik_api_rest/sessions/list_ppp_session/"
            f"{quote(nas_s, safe='')}/{quote(login_s, safe='')}/"
        )
        with httpx.Client(timeout=self.timeout) as client:
            r = client.get(path, headers=self._headers())
        if r.status_code == 404:
            return SesionPPPoE(username=login_s, online=False, nas=nas_s, raw={"http": 404})
        if r.status_code >= 400:
            detail = (r.text or "")[:200]
            logger.warning("Radius list_ppp_session HTTP %s: %s", r.status_code, detail)
            return SesionPPPoE(
                username=login_s,
                online=False,
                nas=nas_s,
                error=f"HTTP {r.status_code}",
                raw={"detail": detail},
            )
        try:
            data = r.json()
        except Exception:
            return SesionPPPoE(
                username=login_s,
                online=False,
                nas=nas_s,
                error="respuesta no JSON",
                raw={"text": (r.text or "")[:200]},
            )
        return parse_ppp_sessions(login_s, nas_s, data)

    def sesion_para_login(self, login: str) -> SesionPPPoE:
        """Atajo: get_nas + list_ppp_session."""
        user = (login or "").strip()
        if not user:
            return SesionPPPoE(username="", online=False, error="login vacío")
        try:
            nas = self.get_nas(user)
        except Exception as exc:
            logger.exception("Radius get_nas falló")
            return SesionPPPoE(username=user, online=False, error=str(exc)[:160])
        if not nas:
            return SesionPPPoE(username=user, online=False, error="NAS no encontrado")
        try:
            return self.list_ppp_session(nas, user)
        except Exception as exc:
            logger.exception("Radius list_ppp_session falló")
            return SesionPPPoE(username=user, online=False, nas=nas, error=str(exc)[:160])

    def get_all_nas(self) -> list[NasInfo]:
        """Inventario completo de NAS desde la DB Radius."""
        if not self.configured():
            raise RuntimeError("Radius API no configurada")

        url = f"{self.base_url}/radius/get_all_nas/"
        with httpx.Client(timeout=self.timeout) as client:
            r = client.get(url, headers=self._headers())
            if r.status_code in (404, 405):
                r = client.post(url, headers=self._headers(), json={})
        if r.status_code >= 400:
            detail = (r.text or "")[:200]
            logger.warning("Radius get_all_nas HTTP %s: %s", r.status_code, detail)
            raise RuntimeError(f"get_all_nas HTTP {r.status_code}")
        try:
            data = r.json()
        except Exception as exc:
            raise RuntimeError("get_all_nas respuesta no JSON") from exc
        return parse_all_nas(data)

    def rest_list_resources(self, shortname: str) -> NasResourceStatus:
        """Chequea conectividad MikroTik del NAS vía shortname."""
        key = (shortname or "").strip()
        if not key:
            return NasResourceStatus(shortname="", reachable=False, error="shortname vacío")
        if not self.configured():
            raise RuntimeError("Radius API no configurada")

        path = (
            f"{self.base_url}/mikrotik_api_rest/rest_list_resources/"
            f"{quote(key, safe='')}/"
        )
        with httpx.Client(timeout=self.timeout) as client:
            r = client.get(path, headers=self._headers())
        try:
            data = r.json() if (r.text or "").strip() else {}
        except Exception:
            data = {"raw": (r.text or "")[:200]}

        if not isinstance(data, dict):
            data = {"value": data}

        err = _first_str(data.get("error"), data.get("detail"), data.get("message"))
        if r.status_code >= 400 or err:
            # "NAS not found" u otros errores de comunicación = no alcanzable
            return NasResourceStatus(
                shortname=key,
                reachable=False,
                error=(err or f"HTTP {r.status_code}")[:200],
                raw=data,
            )

        # Respuesta con métricas típicas MikroTik = alcanzable
        if any(
            k in data
            for k in ("uptime", "version", "platform", "board_name", "cpu_load", "free_memory")
        ):
            return NasResourceStatus(shortname=key, reachable=True, raw=data)

        if data:
            return NasResourceStatus(shortname=key, reachable=True, raw=data)
        return NasResourceStatus(
            shortname=key,
            reachable=False,
            error="respuesta vacía",
            raw=data,
        )


def parse_all_nas(payload: Any) -> list[NasInfo]:
    """Normaliza respuesta de get_all_nas a lista de NasInfo."""
    items: list[Any] = []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        for key in ("data", "results", "nas", "items"):
            nested = payload.get(key)
            if isinstance(nested, list):
                items = nested
                break
        if not items and _first_str(payload.get("shortname"), payload.get("nasname")):
            items = [payload]

    out: list[NasInfo] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        shortname = _first_str(
            item.get("shortname"),
            item.get("nas"),
            item.get("nas_name"),
            item.get("name"),
        )
        nasname = _first_str(
            item.get("nasname"),
            item.get("nas_ip"),
            item.get("ip"),
            item.get("address"),
        )
        if not shortname:
            continue
        key = shortname.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(NasInfo(shortname=shortname, nasname=nasname, raw=item))
    out.sort(key=lambda n: n.shortname.casefold())
    return out
