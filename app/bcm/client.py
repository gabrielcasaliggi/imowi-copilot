"""Cliente HTTP contra Sopnet BCM (OLT/ONU FTTH).

Auth: POST /auth/obtenerToken con usuario + password de aplicación (JWT en memoria).
Lookup: GET /cliente/obtenerPorNumeroCliente?numero= (BillTrack client_number).

Escritura Wi‑Fi (TR-069), ambas bandas cuando aplica:
  POST /tr/modificarWifiPasswordPorSerialNumber (wifi=2 → 2.4 GHz, wifi=5 → 5 GHz)
  POST /tr/modificarWifiSSIDPorSerialNumber
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from app.bcm.contract import (
    BandaWifiBcm,
    CalidadOptica,
    EstadoOnuBcm,
    OperacionWifiBcm,
    ResultadoCambioWifi,
)

logger = logging.getLogger("operations_hub")

DEFAULT_BASE_URL = "https://bcm.batan.coop:7117/api/v1"
# wifi=2 → 2.4 GHz; wifi=5 → 5 GHz (contrato TR BCM).
WIFI_BANDAS: tuple[BandaWifiBcm, BandaWifiBcm] = ("2", "5")
_SENSITIVE_QUERY_KEYS = frozenset({"password", "contrasena", "contraseña", "pass", "pwd"})
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
        "losi",
        "dying_gasp",
        "dyinggasp",
        "unregistered",
        "desconectado",
        "desconectada",
        "fuera",
        "fuera_de_linea",
        "fuera de linea",
        "fuera de rango",
        "fuera_de_rango",
        "no registrado",
        "no_registrado",
        "0",
        "false",
        "no",
    }
)

# Textos de potencia en BCM UI/API: no son un dBm usable.
_RX_INVALID_TEXT_MARKERS = (
    "fuera de rango",
    "fuera_de_rango",
    "sin señal",
    "sin senal",
    "sin potencia",
    "no disponible",
    "n/a",
    "na",
    "--",
    "---",
)


def _first_str(*vals: Any) -> str:
    for v in vals:
        if v is None:
            continue
        s = str(v).strip()
        if s and s.lower() not in ("none", "null", "undefined"):
            return s
    return ""


def _texto_potencia_invalido(val: Any) -> bool:
    """True si BCM manda etiqueta (p. ej. «Fuera de rango») en vez de dBm."""
    if val is None or isinstance(val, bool):
        return False
    if isinstance(val, (int, float)):
        return False
    s = str(val).strip().casefold().replace("−", "-")
    if not s:
        return False
    if s in ("null", "none", "undefined", "nan"):
        return True
    return any(m in s for m in _RX_INVALID_TEXT_MARKERS)


def _as_float(val: Any) -> float | None:
    if val is None or val is False:
        return None
    if isinstance(val, bool):
        return None
    if _texto_potencia_invalido(val):
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
    """BCM a veces entrega RX positiva (18.5 = -18.5 dBm).

    «Fuera de rango» y similares → None (no inventar dBm ni pintar zona verde).
    """
    if _texto_potencia_invalido(val):
        return None
    n = _as_float(val)
    if n is None:
        return None
    if 8.0 <= n <= 40.0:
        return -n
    return n


def _potencias_fuera_de_rango(*blobs: dict[str, Any]) -> bool:
    """True si Rx/Tx/Catv vienen como texto «Fuera de rango» (UI BCM)."""
    keys = (
        "rx",
        "rx_power",
        "rxpower",
        "potencia_rx",
        "potenciarx",
        "potencia",
        "potencia_optica",
        "potenciaoptica",
        "tx",
        "tx_power",
        "potencia_tx",
        "catv",
        "potencia_catv",
        "potenciacatv",
        "rx_status",
        "estado_rx",
        "estado_potencia",
    )
    for blob in blobs:
        if not isinstance(blob, dict):
            continue
        by = {str(k).casefold(): v for k, v in blob.items()}
        for key in keys:
            if key in by and _texto_potencia_invalido(by[key]):
                return True
        for k, v in blob.items():
            kl = str(k).casefold()
            if ("potencia" in kl or kl.startswith("rx") or "optica" in kl) and _texto_potencia_invalido(
                v
            ):
                return True
    return False


def _uptime_cero(blob: dict[str, Any]) -> bool:
    for key in ("uptime", "up_time", "tiempo_activo", "ont_uptime"):
        raw = _get_ci(blob, key)
        if raw is None:
            continue
        if isinstance(raw, (int, float)) and float(raw) == 0:
            return True
        s = str(raw).strip().casefold()
        if s in ("0", "00:00:00", "0:00:00", "0s", "0 segundos"):
            return True
    return False


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
    """Desanida data/cliente/result típicos de BCM.

    Si en este nivel ya hay ONU/ONT, no baja a `cliente` (la potencia suele
    venir como hermano, no como hijo de la ficha).
    """
    if isinstance(payload, list) and payload:
        return unwrap_payload(payload[0])
    if not isinstance(payload, dict):
        return {}
    if any(str(k).casefold() in ("onu", "ont", "onus", "onts") for k in payload):
        return payload
    by_key = {str(k).casefold(): v for k, v in payload.items()}
    for key in (
        "data",
        "datos",
        "cliente",
        "result",
        "resultado",
        "payload",
        "response",
        "objeto",
    ):
        nested = by_key.get(key)
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


def redactar_params_sensibles(params: dict[str, str]) -> dict[str, str]:
    """Copia de query params sin secretos (para logs)."""
    out: dict[str, str] = {}
    for k, v in (params or {}).items():
        if str(k).lower() in _SENSITIVE_QUERY_KEYS:
            out[str(k)] = "***"
        else:
            out[str(k)] = str(v)
    return out


def redactar_url_sensible(url: str) -> str:
    """Quita password/contraseña del query string de una URL."""
    try:
        parts = urlsplit(url or "")
        q = []
        for k, v in parse_qsl(parts.query, keep_blank_values=True):
            if k.lower() in _SENSITIVE_QUERY_KEYS:
                q.append((k, "***"))
            else:
                q.append((k, v))
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment)
        )
    except Exception:
        return "(url)"


def _error_en_cuerpo_tr_wifi(payload: Any, text: str = "") -> str:
    """BCM a veces responde HTTP 200 con error_id/mensaje de fallo en el body."""
    blobs: list[str] = []
    if isinstance(payload, dict):
        eid = str(
            payload.get("error_id")
            or payload.get("errorId")
            or payload.get("ErrorId")
            or ""
        ).strip()
        msg = _mensaje_api(payload) or str(payload.get("msg") or payload.get("mensaje") or "")
        if eid and eid not in ("0", "200", "ok", "OK"):
            return f"error_id={eid} {msg}".strip()[:160]
        if msg:
            blobs.append(msg)
    elif isinstance(payload, str) and payload.strip():
        blobs.append(payload.strip())
    if text and text.strip():
        blobs.append(text.strip())
    joined = " ".join(blobs).lower()
    if not joined:
        return ""
    if any(
        k in joined
        for k in (
            "datos incorrectos",
            "id no encontrado",
            "no encontrado",
            "error_id\":\"201",
            "error_id\": \"201",
            '"error_id":"201"',
        )
    ):
        return (blobs[0] if blobs else "error BCM")[:160]
    return ""


def _get_ci(blob: dict[str, Any], *keys: str) -> Any:
    by = {str(k).casefold(): v for k, v in blob.items()}
    for key in keys:
        if key.casefold() in by:
            return by[key.casefold()]
    return None


def _buscar_rx_en_arbol(blob: Any, *, depth: int = 0) -> Any:
    """Último recurso: RX en claves rx*/potencia* (no TX) hasta 5 niveles."""
    if depth > 5 or blob is None:
        return None
    if isinstance(blob, dict):
        by = {str(k).casefold(): v for k, v in blob.items()}
        for key in (
            "rx",
            "rx_power",
            "rxpower",
            "rx_optical",
            "rxopticalpower",
            "opticalrxpower",
            "potencia_rx",
            "potenciarx",
            "potenciaoptica",
            "potencia_optica",
        ):
            if key in by:
                n = normalizar_rx_dbm(by[key])
                if n is not None:
                    return by[key]
        for k, v in blob.items():
            kl = str(k).casefold()
            if "tx" in kl or "catv" in kl:
                continue
            if "rx" in kl or "potencia" in kl:
                n = normalizar_rx_dbm(v)
                if n is not None and -40.0 <= n <= 5.0:
                    return v
        for v in blob.values():
            found = _buscar_rx_en_arbol(v, depth=depth + 1)
            if found is not None:
                return found
    if isinstance(blob, list):
        for item in blob:
            found = _buscar_rx_en_arbol(item, depth=depth + 1)
            if found is not None:
                return found
    return None


def extraer_bloque_onu(cliente: dict[str, Any]) -> dict[str, Any]:
    """ONU/ONT puede venir anidada o aplanada en la ficha del cliente."""
    by = {str(k).casefold(): v for k, v in cliente.items()}
    for key in ("onu", "ont", "onus", "dispositivo", "equipo", "onts"):
        val = by.get(key)
        if isinstance(val, list) and val and isinstance(val[0], dict):
            return val[0]
        if isinstance(val, dict) and val:
            return val
    olt = by.get("olt")
    if isinstance(olt, dict) and any(
        by.get(k) for k in ("serial", "serial_onu", "sn", "estado_onu", "rx", "potencia_rx")
    ):
        return cliente
    if any(
        by.get(k)
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
        _get_ci(cliente, "numero", "numero_cliente", "nro_cliente", "client_number", "numeroCliente"),
        numero_cliente,
    ) or numero_cliente

    potencia_invalida = _potencias_fuera_de_rango(onu, cliente)
    rx = None
    if not potencia_invalida:
        rx = normalizar_rx_dbm(
            _get_ci(
                onu,
                "rx",
                "rx_power",
                "rxPower",
                "potencia_rx",
                "potenciaRx",
                "rxpower",
                "rxOpticalPower",
                "opticalRxPower",
            )
            or _get_ci(cliente, "rx", "potencia_rx", "potenciaRx", "rx_power")
        )
        if rx is None:
            rx = normalizar_rx_dbm(_get_ci(onu, "potencia") or _get_ci(cliente, "potencia"))
        if rx is None:
            rx = normalizar_rx_dbm(_buscar_rx_en_arbol(cliente) or _buscar_rx_en_arbol(onu))
        if rx is None and payload is not cliente:
            rx = normalizar_rx_dbm(_buscar_rx_en_arbol(payload))
    tx = None
    if not potencia_invalida:
        tx = normalizar_rx_dbm(
            onu.get("tx")
            or onu.get("tx_power")
            or onu.get("txPower")
            or onu.get("potencia_tx")
            or cliente.get("tx")
        )

    online = _status_online(onu) if _status_online(onu) is not None else _status_online(cliente)
    # BCM UI: Rx «Fuera de rango» + uptime 00:00:00 / LOS → no hay enlace óptico usable.
    if potencia_invalida or _uptime_cero(onu) or _uptime_cero(cliente):
        if online is not False:
            online = False

    calidad: CalidadOptica = "mala" if potencia_invalida else clasificar_optica(rx)

    return EstadoOnuBcm(
        numero_cliente=nro,
        encontrado=True,
        online=online,
        nombre=_first_str(cliente.get("nombre"), cliente.get("name")),
        apellido=_first_str(cliente.get("apellido"), cliente.get("lastname")),
        serial=_first_str(
            _get_ci(onu, "serial", "serial_onu", "serial_ont", "sn", "numero_serie"),
            _get_ci(cliente, "serial_onu", "serial", "sn"),
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
        calidad_optica=calidad,
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
            params = {**self._get_auth_params(), "numero": nro}
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

    def _request_post(
        self, path: str, params: dict[str, str], *, retry: bool = True
    ) -> httpx.Response:
        if not self.configured():
            raise RuntimeError("BCM no configurado")
        url = f"{self.base_url}{path if path.startswith('/') else '/' + path}"
        with self._client() as http:
            r = http.post(url, params=params)
        if r.status_code in (401, 403) and retry:
            self._token = ""
            self.authenticate()
            params = {**params, "usuario": self.user, "token": self._token}
            return self._request_post(path, params, retry=False)
        return r

    def _resultado_tr_wifi(
        self,
        r: httpx.Response,
        *,
        banda: BandaWifiBcm,
        operacion: OperacionWifiBcm,
    ) -> ResultadoCambioWifi:
        detail = ""
        payload: Any = None
        try:
            payload = r.json()
            detail = _mensaje_api(payload) or (
                payload if isinstance(payload, str) else _claves_payload(payload)
            )
        except Exception:
            detail = (r.text or "")[:160]
            payload = None
        # Nunca devolver el password en el error (puede venir echo'd por la API).
        detail_s = re.sub(
            r"(password|contrase[nñ]a|pass)\s*[=:]\s*\S+",
            r"\1=***",
            str(detail or ""),
            flags=re.IGNORECASE,
        )[:160]
        body_err = _error_en_cuerpo_tr_wifi(payload, r.text or "")
        if r.status_code == 200 and not body_err:
            return ResultadoCambioWifi(
                ok=True, banda=banda, operacion=operacion, http_status=200
            )
        if body_err:
            return ResultadoCambioWifi(
                ok=False,
                banda=banda,
                operacion=operacion,
                http_status=r.status_code,
                error=f"BCM: {body_err}"[:160],
            )
        return ResultadoCambioWifi(
            ok=False,
            banda=banda,
            operacion=operacion,
            http_status=r.status_code,
            error=f"BCM HTTP {r.status_code}: {detail_s}"[:160],
        )

    def modificar_wifi_password_por_serial(
        self, serial: str, password: str, wifi: BandaWifiBcm
    ) -> ResultadoCambioWifi:
        sn = (serial or "").strip()
        pwd = password or ""
        banda: BandaWifiBcm = "5" if str(wifi) == "5" else "2"
        if not sn:
            return ResultadoCambioWifi(
                ok=False, banda=banda, operacion="password", error="serial vacío"
            )
        if not pwd:
            return ResultadoCambioWifi(
                ok=False, banda=banda, operacion="password", error="password vacío"
            )
        params = {
            **self._get_auth_params(),
            "serialNumber": sn,
            "password": pwd,
            "wifi": banda,
        }
        try:
            r = self._request_post("/tr/modificarWifiPasswordPorSerialNumber", params)
        except Exception as exc:
            logger.warning(
                "BCM modificarWifiPassword falló serial=%s wifi=%s: %s",
                sn[:24],
                banda,
                type(exc).__name__,
            )
            return ResultadoCambioWifi(
                ok=False,
                banda=banda,
                operacion="password",
                error=f"BCM error: {type(exc).__name__}"[:160],
            )
        if not (200 <= r.status_code < 300):
            logger.info(
                "BCM modificarWifiPassword serial=%s wifi=%s status=%s params=%s",
                sn[:24],
                banda,
                r.status_code,
                redactar_params_sensibles(params),
            )
        return self._resultado_tr_wifi(r, banda=banda, operacion="password")

    def modificar_wifi_ssid_por_serial(
        self, serial: str, ssid: str, wifi: BandaWifiBcm
    ) -> ResultadoCambioWifi:
        sn = (serial or "").strip()
        nombre = (ssid or "").strip()
        banda: BandaWifiBcm = "5" if str(wifi) == "5" else "2"
        if not sn:
            return ResultadoCambioWifi(
                ok=False, banda=banda, operacion="ssid", error="serial vacío"
            )
        if not nombre:
            return ResultadoCambioWifi(
                ok=False, banda=banda, operacion="ssid", error="ssid vacío"
            )
        params = {
            **self._get_auth_params(),
            "serialNumber": sn,
            "ssid": nombre,
            "wifi": banda,
        }
        try:
            r = self._request_post("/tr/modificarWifiSSIDPorSerialNumber", params)
        except Exception as exc:
            logger.warning(
                "BCM modificarWifiSSID falló serial=%s wifi=%s: %s",
                sn[:24],
                banda,
                type(exc).__name__,
            )
            return ResultadoCambioWifi(
                ok=False,
                banda=banda,
                operacion="ssid",
                error=f"BCM error: {type(exc).__name__}"[:160],
            )
        if not (200 <= r.status_code < 300):
            logger.info(
                "BCM modificarWifiSSID serial=%s wifi=%s status=%s params=%s",
                sn[:24],
                banda,
                r.status_code,
                redactar_params_sensibles(params),
            )
        return self._resultado_tr_wifi(r, banda=banda, operacion="ssid")

    def modificar_wifi_password_ambas_bandas(
        self, serial: str, password: str
    ) -> list[ResultadoCambioWifi]:
        return [
            self.modificar_wifi_password_por_serial(serial, password, banda)
            for banda in WIFI_BANDAS
        ]

    def modificar_wifi_ssid_ambas_bandas(
        self, serial: str, ssid: str
    ) -> list[ResultadoCambioWifi]:
        return [
            self.modificar_wifi_ssid_por_serial(serial, ssid, banda)
            for banda in WIFI_BANDAS
        ]

    def modificar_wifi_password_por_user_radius(
        self, user_radius: str, password: str, wifi: BandaWifiBcm
    ) -> ResultadoCambioWifi:
        login = (user_radius or "").strip()
        pwd = password or ""
        banda: BandaWifiBcm = "5" if str(wifi) == "5" else "2"
        if not login:
            return ResultadoCambioWifi(
                ok=False, banda=banda, operacion="password", error="userRadius vacío"
            )
        if not pwd:
            return ResultadoCambioWifi(
                ok=False, banda=banda, operacion="password", error="password vacío"
            )
        params = {
            **self._get_auth_params(),
            "userRadius": login,
            "password": pwd,
            "wifi": banda,
        }
        try:
            r = self._request_post("/tr/modificarWifiPasswordPorUserRadius", params)
        except Exception as exc:
            logger.warning(
                "BCM modificarWifiPassword userRadius=%s wifi=%s: %s",
                login[:24],
                banda,
                type(exc).__name__,
            )
            return ResultadoCambioWifi(
                ok=False,
                banda=banda,
                operacion="password",
                error=f"BCM error: {type(exc).__name__}"[:160],
            )
        if not (200 <= r.status_code < 300):
            logger.info(
                "BCM modificarWifiPassword userRadius=%s wifi=%s status=%s params=%s",
                login[:24],
                banda,
                r.status_code,
                redactar_params_sensibles(params),
            )
        return self._resultado_tr_wifi(r, banda=banda, operacion="password")

    def modificar_wifi_ssid_por_user_radius(
        self, user_radius: str, ssid: str, wifi: BandaWifiBcm
    ) -> ResultadoCambioWifi:
        login = (user_radius or "").strip()
        nombre = (ssid or "").strip()
        banda: BandaWifiBcm = "5" if str(wifi) == "5" else "2"
        if not login:
            return ResultadoCambioWifi(
                ok=False, banda=banda, operacion="ssid", error="userRadius vacío"
            )
        if not nombre:
            return ResultadoCambioWifi(
                ok=False, banda=banda, operacion="ssid", error="ssid vacío"
            )
        params = {
            **self._get_auth_params(),
            "userRadius": login,
            "ssid": nombre,
            "wifi": banda,
        }
        try:
            r = self._request_post("/tr/modificarWifiSSIDPorUserRadius", params)
        except Exception as exc:
            logger.warning(
                "BCM modificarWifiSSID userRadius=%s wifi=%s: %s",
                login[:24],
                banda,
                type(exc).__name__,
            )
            return ResultadoCambioWifi(
                ok=False,
                banda=banda,
                operacion="ssid",
                error=f"BCM error: {type(exc).__name__}"[:160],
            )
        if not (200 <= r.status_code < 300):
            logger.info(
                "BCM modificarWifiSSID userRadius=%s wifi=%s status=%s params=%s",
                login[:24],
                banda,
                r.status_code,
                redactar_params_sensibles(params),
            )
        return self._resultado_tr_wifi(r, banda=banda, operacion="ssid")

    def modificar_wifi_password_ambas_bandas_por_user_radius(
        self, user_radius: str, password: str
    ) -> list[ResultadoCambioWifi]:
        return [
            self.modificar_wifi_password_por_user_radius(user_radius, password, banda)
            for banda in WIFI_BANDAS
        ]

    def modificar_wifi_ssid_ambas_bandas_por_user_radius(
        self, user_radius: str, ssid: str
    ) -> list[ResultadoCambioWifi]:
        return [
            self.modificar_wifi_ssid_por_user_radius(user_radius, ssid, banda)
            for banda in WIFI_BANDAS
        ]
