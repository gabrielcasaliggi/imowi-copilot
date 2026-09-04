"""Cliente HTTP contra Sopnet BCM (OLT/ONU FTTH). Solo lectura.

Auth: POST /auth/obtenerToken con usuario + password de aplicación (JWT en memoria).
Lookup: GET /cliente/obtenerPorNumeroCliente (número de cliente del ERP / BillTrack).

No implementa editarPorNumeroCliente: N1 no escribe en BCM.
Endpoints extra de OLT/ONU se agregan cuando el contrato esté confirmado;
mientras tanto se parsean ONU/OLT anidados en la ficha del cliente.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx

from app.bcm.contract import CalidadOptica, EstadoOnuBcm

logger = logging.getLogger("operations_hub")

DEFAULT_BASE_URL = "https://la23.sopnet.com.ar:7117/api/v1"
_RE_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")
_TOKEN_KEYS = frozenset(
    {
        "token",
        "jwt",
        "access_token",
        "accesstoken",
        "access-token",
        "tokenusuario",
        "token_usuario",
        "tokenacceso",
        "token_acceso",
        "bearertoken",
        "bearer",
        "sesion",
        "session",
        "id_token",
        "idtoken",
        "apitoken",
        "api_token",
        "auth_token",
        "authtoken",
        "tokensesion",
        "token_sesion",
    }
)
_NEST_KEYS = frozenset(
    {
        "data",
        "result",
        "resultado",
        "datos",
        "dato",
        "objeto",
        "valor",
        "contenido",
        "payload",
        "response",
        "body",
        "item",
        "respuesta",
        "output",
    }
)

# GPON: RX típica -8 a -27 dBm. Por debajo de -27 → visita; por encima de -8 → saturación.
RX_BUENA_DBM = -24.0
RX_ACEPTABLE_DBM = -27.0
RX_SATURACION_DBM = -8.0

_ONLINE_STATUS = frozenset(
    {
        "active",
        "online",
        "on",
        "up",
        "ok",
        "conectado",
        "conectada",
        "en_linea",
        "en linea",
        "registrado",
        "registrada",
        "working",
        "operativo",
        "operativa",
        "1",
        "true",
        "si",
        "sí",
    }
)
_OFFLINE_STATUS = frozenset(
    {
        "disconnected",
        "inactive",
        "offline",
        "off",
        "down",
        "los",
        "dying_gasp",
        "dyinggasp",
        "unregistered",
        "desconectado",
        "desconectada",
        "fuera",
        "fuera_de_linea",
        "fuera de linea",
        "no registrado",
        "no_registrado",
        "0",
        "false",
        "no",
    }
)


def _first_str(*vals: Any) -> str:
    for v in vals:
        if v is None:
            continue
        s = str(v).strip()
        if s and s.lower() not in ("none", "null", "undefined"):
            return s
    return ""


def _as_float(val: Any) -> float | None:
    if val is None or val is False:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        n = float(val)
        if n != n:  # NaN
            return None
        return n
    s = str(val).strip().lower().replace("dbm", "").replace(",", ".").strip()
    if not s:
        return None
    try:
        n = float(s)
    except (TypeError, ValueError):
        return None
    if n != n:
        return None
    return n


def normalizar_rx_dbm(val: Any) -> float | None:
    """BCM a veces entrega RX positiva (18.5 = -18.5 dBm)."""
    n = _as_float(val)
    if n is None:
        return None
    if 8.0 <= n <= 40.0:
        return -n
    return n


def clasificar_optica(rx_dbm: float | None) -> CalidadOptica:
    if rx_dbm is None:
        return ""
    if rx_dbm > RX_SATURACION_DBM:
        return "mala"
    if rx_dbm >= RX_BUENA_DBM:
        return "buena"
    if rx_dbm >= RX_ACEPTABLE_DBM:
        return "aceptable"
    return "mala"


def unwrap_payload(payload: Any) -> dict[str, Any]:
    """Desanida data/cliente/result típicos de BCM."""
    if isinstance(payload, list) and payload:
        return unwrap_payload(payload[0])
    if not isinstance(payload, dict):
        return {}
    for key in ("data", "cliente", "result", "resultado", "payload", "response"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            return unwrap_payload(nested)
        if isinstance(nested, list) and nested:
            inner = unwrap_payload(nested[0])
            if inner:
                return inner
    return payload


def _parece_token(val: str) -> bool:
    s = (val or "").strip()
    if len(s) < 16:
        return False
    if _RE_JWT.search(s):
        return True
    # Token opaco (no JWT): sin espacios, largo razonable.
    if " " not in s and "\n" not in s and 16 <= len(s) <= 4096:
        return True
    return False


def extraer_token(payload: Any) -> str:
    """Acepta JWT u opaco en varias envelopes típicas de PHP/BCM."""
    if isinstance(payload, str):
        s = payload.strip().strip('"')
        if _parece_token(s):
            m = _RE_JWT.search(s)
            return m.group(0) if m else s
        return ""
    if isinstance(payload, list):
        for item in payload:
            found = extraer_token(item)
            if found:
                return found
        return ""
    if not isinstance(payload, dict):
        return ""

    by_key = {str(k).casefold(): v for k, v in payload.items()}
    for key in _TOKEN_KEYS:
        val = by_key.get(key)
        if isinstance(val, str) and _parece_token(val):
            m = _RE_JWT.search(val.strip())
            return (m.group(0) if m else val.strip())
        if val is not None and not isinstance(val, (dict, list, bool)):
            s = str(val).strip()
            if _parece_token(s):
                m = _RE_JWT.search(s)
                return m.group(0) if m else s

    for key in _NEST_KEYS:
        if key in by_key:
            found = extraer_token(by_key[key])
            if found:
                return found

    for val in payload.values():
        if isinstance(val, (dict, list)):
            found = extraer_token(val)
            if found:
                return found
        elif isinstance(val, str):
            m = _RE_JWT.search(val)
            if m:
                return m.group(0)
    return ""


def _mensaje_api(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    by_key = {str(k).casefold(): v for k, v in payload.items()}
    for key in ("mensaje", "message", "msg", "error", "detalle", "detail", "descripcion"):
        val = by_key.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()[:180]
        if isinstance(val, dict):
            nested = _mensaje_api(val)
            if nested:
                return nested
    for nest in ("data", "datos", "result", "resultado"):
        nested = _mensaje_api(by_key.get(nest))
        if nested:
            return nested
    return ""


def _claves_payload(payload: Any, *, limite: int = 12) -> str:
    if isinstance(payload, dict):
        keys = [str(k) for k in payload.keys()][:limite]
        return ",".join(keys) if keys else "(vacío)"
    if isinstance(payload, list):
        return f"lista[{len(payload)}]"
    if payload is None:
        return "(null)"
    return type(payload).__name__


def describir_auth_fallida(payload: Any, *, status_code: int, content_type: str = "") -> str:
    """Error usable en admin: claves y mensaje de BCM, sin el cuerpo crudo."""
    msg = _mensaje_api(payload)
    claves = _claves_payload(payload)
    ctype = (content_type or "").split(";")[0].strip() or "desconocido"
    parts = [f"HTTP {status_code}", f"tipo={ctype}", f"claves={claves}"]
    if msg:
        parts.append(f"mensaje={msg}")
    return "BCM auth: la respuesta no trajo token (" + "; ".join(parts) + ")"


def extraer_bloque_onu(cliente: dict[str, Any]) -> dict[str, Any]:
    """ONU/ONT puede venir anidada o aplanada en la ficha del cliente."""
    for key in ("onu", "ont", "onus", "dispositivo", "equipo", "onts"):
        val = cliente.get(key)
        if isinstance(val, list) and val and isinstance(val[0], dict):
            return val[0]
        if isinstance(val, dict) and val:
            return val
    olt = cliente.get("olt")
    if isinstance(olt, dict) and any(
        cliente.get(k) for k in ("serial", "serial_onu", "sn", "estado_onu", "rx", "potencia_rx")
    ):
        return cliente
    if any(
        cliente.get(k)
        for k in (
            "serial_onu",
            "serial_ont",
            "numero_serie",
            "estado_onu",
            "estado_ont",
            "potencia_rx",
            "rx_power",
            "nombre_olt",
            "olt_nombre",
        )
    ):
        return cliente
    return cliente


def _status_online(blob: dict[str, Any]) -> bool | None:
    for raw in (
        blob.get("online"),
        blob.get("conectado"),
        blob.get("registrado"),
        blob.get("estado"),
        blob.get("status"),
        blob.get("state"),
        blob.get("estado_onu"),
        blob.get("estado_ont"),
        blob.get("estadoOnu"),
        blob.get("operativo"),
    ):
        if isinstance(raw, bool):
            return raw
        s = _first_str(raw).casefold().replace("-", "_")
        if not s:
            continue
        if s in _ONLINE_STATUS:
            return True
        if s in _OFFLINE_STATUS:
            return False
    return None


def _dig_olt(onu: dict[str, Any], cliente: dict[str, Any]) -> str:
    olt = onu.get("olt") if isinstance(onu.get("olt"), dict) else {}
    if not isinstance(olt, dict):
        olt = {}
    return _first_str(
        onu.get("olt_nombre"),
        onu.get("nombre_olt"),
        onu.get("oltNombre"),
        onu.get("olt_name"),
        olt.get("nombre"),
        olt.get("name"),
        olt.get("descripcion"),
        cliente.get("olt_nombre"),
        cliente.get("nombre_olt"),
        onu.get("olt") if not isinstance(onu.get("olt"), dict) else "",
        cliente.get("olt") if not isinstance(cliente.get("olt"), dict) else "",
    )


def _dig_pon(onu: dict[str, Any], cliente: dict[str, Any]) -> str:
    return _first_str(
        onu.get("pon"),
        onu.get("puerto_pon"),
        onu.get("puertoPon"),
        onu.get("gpon"),
        onu.get("puerto"),
        onu.get("port"),
        onu.get("slot"),
        cliente.get("pon"),
        cliente.get("puerto_pon"),
    )


def parse_cliente(payload: Any, *, numero_cliente: str) -> EstadoOnuBcm:
    """Normaliza la ficha BCM a EstadoOnuBcm (ONU + OLT si vienen en el JSON)."""
    cliente = unwrap_payload(payload)
    if not cliente:
        return EstadoOnuBcm(numero_cliente=numero_cliente, encontrado=False)

    status_top = _first_str(
        payload.get("status") if isinstance(payload, dict) else "",
        payload.get("estado") if isinstance(payload, dict) else "",
    ).casefold()
    if status_top in ("error", "fail", "failed", "not_found", "notfound") and not extraer_bloque_onu(
        cliente
    ).get("serial"):
        err = _first_str(
            payload.get("mensaje") if isinstance(payload, dict) else "",
            payload.get("message") if isinstance(payload, dict) else "",
            payload.get("error") if isinstance(payload, dict) else "",
        )
        return EstadoOnuBcm(
            numero_cliente=numero_cliente,
            encontrado=False,
            error=err[:160],
        )

    onu = extraer_bloque_onu(cliente)
    nro = _first_str(
        cliente.get("numero_cliente"),
        cliente.get("nro_cliente"),
        cliente.get("client_number"),
        cliente.get("numeroCliente"),
        numero_cliente,
    ) or numero_cliente

    rx = normalizar_rx_dbm(
        _first_str(
            onu.get("rx"),
            onu.get("rx_power"),
            onu.get("rxPower"),
            onu.get("potencia_rx"),
            onu.get("potenciaRx"),
            onu.get("rxpower"),
            cliente.get("rx"),
            cliente.get("potencia_rx"),
        )
        or onu.get("rx")
        or cliente.get("rx")
    )
    if rx is None:
        rx = normalizar_rx_dbm(onu.get("potencia") or cliente.get("potencia"))
    tx = normalizar_rx_dbm(
        onu.get("tx")
        or onu.get("tx_power")
        or onu.get("txPower")
        or onu.get("potencia_tx")
        or cliente.get("tx")
    )

    return EstadoOnuBcm(
        numero_cliente=nro,
        encontrado=True,
        online=_status_online(onu) if _status_online(onu) is not None else _status_online(cliente),
        nombre=_first_str(cliente.get("nombre"), cliente.get("name")),
        apellido=_first_str(cliente.get("apellido"), cliente.get("lastname")),
        serial=_first_str(
            onu.get("serial"),
            onu.get("serial_onu"),
            onu.get("serial_ont"),
            onu.get("sn"),
            onu.get("numero_serie"),
            cliente.get("serial_onu"),
            cliente.get("serial"),
        ),
        modelo=_first_str(
            onu.get("modelo"),
            onu.get("model"),
            onu.get("modelo_onu"),
            cliente.get("modelo_onu"),
        ),
        mac=_first_str(onu.get("mac"), onu.get("mac_onu"), cliente.get("mac_onu")),
        olt_nombre=_dig_olt(onu, cliente),
        pon=_dig_pon(onu, cliente),
        rx_dbm=rx,
        tx_dbm=tx,
        calidad_optica=clasificar_optica(rx),
        raw=cliente if isinstance(cliente, dict) else {},
    )


class BcmClient:
    """Cliente HTTP. Credenciales solo por config/env — nunca hardcodear."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        user: str = "",
        app_pass: str = "",
        timeout: float = 12.0,
        verify_ssl: bool = True,
    ) -> None:
        self.base_url = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
        self.user = (user or "").strip()
        self.app_pass = (app_pass or "").strip()
        self.timeout = timeout
        self.verify_ssl = bool(verify_ssl)
        self._token = ""

    def configured(self) -> bool:
        return bool(self.base_url and self.user and self.app_pass)

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout,
            verify=self.verify_ssl,
            follow_redirects=True,
        )

    def _get_auth_params(self) -> dict[str, str]:
        if not self._token:
            self.authenticate()
        return {"usuario": self.user, "token": self._token}

    def authenticate(self) -> str:
        if not self.configured():
            raise RuntimeError("BCM no configurado")
        url = f"{self.base_url}/auth/obtenerToken"
        creds = {"usuario": self.user, "contrasenaapp": self.app_pass}
        last_fail = "BCM auth: sin respuesta"
        with self._client() as http:
            attempts: list[tuple[str, Any]] = [
                ("post_query_form", {"params": creds, "data": creds}),
                ("post_form", {"data": creds}),
                ("post_json", {"json": creds}),
                ("get_query", None),
            ]
            for name, kwargs in attempts:
                if name == "get_query":
                    r = http.get(url, params=creds)
                else:
                    r = http.post(url, **kwargs)
                if r.status_code in (401, 403):
                    raise RuntimeError("BCM 401/403: usuario o password de aplicación inválidos")
                if r.status_code >= 400:
                    last_fail = f"BCM auth HTTP {r.status_code} ({name})"
                    logger.warning("BCM auth %s HTTP %s: %s", name, r.status_code, (r.text or "")[:180])
                    continue
                payload: Any
                ctype = r.headers.get("content-type") or ""
                try:
                    payload = r.json()
                except Exception:
                    text = (r.text or "").strip()
                    token = extraer_token(text)
                    if token:
                        self._token = token
                        return token
                    last_fail = describir_auth_fallida(
                        {"raw": text[:80] or "(vacío)"},
                        status_code=r.status_code,
                        content_type=ctype,
                    )
                    continue
                token = extraer_token(payload)
                if token:
                    self._token = token
                    return token
                last_fail = describir_auth_fallida(
                    payload, status_code=r.status_code, content_type=ctype
                )
                msg = _mensaje_api(payload).lower()
                if any(k in msg for k in ("usuario", "password", "contraseña", "contrasena", "inválid", "invalid", "deneg")):
                    break
        raise RuntimeError(last_fail)

    def _request_get(self, path: str, params: dict[str, str], *, retry: bool = True) -> httpx.Response:
        if not self.configured():
            raise RuntimeError("BCM no configurado")
        url = f"{self.base_url}{path if path.startswith('/') else '/' + path}"
        with self._client() as http:
            r = http.get(url, params=params)
        if r.status_code in (401, 403) and retry:
            self._token = ""
            self.authenticate()
            params = {**params, "token": self._token}
            return self._request_get(path, params, retry=False)
        return r

    def ping(self) -> dict[str, Any]:
        """Prueba de conexión: obtiene JWT."""
        t0 = time.monotonic()
        self.authenticate()
        ms = int((time.monotonic() - t0) * 1000)
        return {"ok": True, "authenticated": True, "latency_ms": ms}

    def buscar_onu_por_cliente(self, numero_cliente: str) -> EstadoOnuBcm:
        nro = str(numero_cliente or "").strip()
        if not nro:
            return EstadoOnuBcm(numero_cliente="", error="numero_cliente vacío")
        if not self.configured():
            return EstadoOnuBcm(numero_cliente=nro, error="bcm no configurado")
        try:
            params = {**self._get_auth_params(), "numero_cliente": nro}
            r = self._request_get("/cliente/obtenerPorNumeroCliente", params)
        except Exception as exc:
            logger.exception("BCM obtenerPorNumeroCliente falló")
            return EstadoOnuBcm(numero_cliente=nro, error=str(exc)[:160])
        if r.status_code == 404:
            return EstadoOnuBcm(numero_cliente=nro, encontrado=False)
        if r.status_code >= 400:
            detail = (r.text or "")[:160]
            return EstadoOnuBcm(
                numero_cliente=nro,
                error=f"BCM HTTP {r.status_code}: {detail}"[:160],
            )
        try:
            payload = r.json()
        except Exception as exc:
            return EstadoOnuBcm(numero_cliente=nro, error=f"respuesta no JSON: {exc}"[:160])
        return parse_cliente(payload, numero_cliente=nro)
