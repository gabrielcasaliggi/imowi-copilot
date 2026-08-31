"""BillTrack — Postgres externo de solo lectura (padrón de clientes para el bot).

Independiente del Data Estate. No persistir tickets ni config de plataforma ahí.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote_plus, urlparse

from sqlalchemy.orm import Session

logger = logging.getLogger("operations_hub")


def build_postgres_url(
    *,
    host: str,
    port: int | str = 5432,
    user: str,
    password: str,
    dbname: str,
) -> str:
    """Arma una URL postgresql+psycopg con user/password escapados."""
    host = (host or "").strip()
    user = (user or "").strip()
    dbname = (dbname or "").strip() or "postgres"
    if not host or not user:
        return ""
    try:
        port_n = int(port or 5432)
    except (TypeError, ValueError):
        port_n = 5432
    return (
        f"postgresql+psycopg://{quote_plus(user)}:{quote_plus(password or '')}"
        f"@{host}:{port_n}/{quote_plus(dbname)}"
    )


def parse_postgres_url(url: str) -> dict[str, str]:
    """Extrae host/port/user/dbname de una URL (password no se expone)."""
    raw = (url or "").strip()
    if not raw:
        return {}
    for prefix in ("postgresql+psycopg://", "postgres://"):
        if raw.startswith(prefix):
            raw = "postgresql://" + raw[len(prefix) :]
            break
    try:
        p = urlparse(raw)
    except Exception:
        return {}
    return {
        "host": p.hostname or "",
        "port": str(p.port or 5432),
        "user": p.username or "",
        "dbname": (p.path or "/").lstrip("/") or "postgres",
    }


def connection_params(cfg: dict[str, Any]) -> dict[str, Any]:
    """Resuelve URL + sslmode desde campos discretos o url completa."""
    host = str(cfg.get("host") or "").strip()
    user = str(cfg.get("user") or "").strip()
    password = str(cfg.get("password") or "")
    dbname = str(cfg.get("dbname") or "").strip() or "postgres"
    port = cfg.get("port") or 5432
    sslmode = str(cfg.get("sslmode") or "disable").strip() or "disable"
    url = str(cfg.get("url") or "").strip()

    if host and user and password and "***" not in password:
        url = build_postgres_url(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=dbname,
        )

    return {
        "url": url,
        "sslmode": sslmode,
        "host": host,
        "port": str(port),
        "user": user,
        "dbname": dbname,
    }


def preflight_tcp(host: str, port: int | str = 5432, *, timeout: float = 5.0) -> dict:
    """Comprueba si host:port es alcanzable a nivel TCP (antes de autenticar)."""
    import socket

    host = (host or "").strip()
    try:
        port_n = int(port or 5432)
    except (TypeError, ValueError):
        port_n = 5432
    out: dict = {"host": host, "port": port_n, "tcp_ok": False}
    if not host:
        out["error"] = "host vacío"
        return out
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port_n))
        out["tcp_ok"] = True
    except OSError as exc:
        out["error"] = str(exc)[:160]
        err = str(exc).lower()
        if "unreachable" in err or "timed out" in err or "timeout" in err:
            out["hint"] = (
                "El API no alcanza ese host:puerto. BillTrack suele estar solo en la red "
                "interna/VPN (p. ej. WireGuard). Corré el backend en una máquina con VPN "
                "conectada — un deploy en Render/cloud no puede llegar a esa IP."
            )
    finally:
        sock.close()
    return out


def resolve_connection(db: Session | None = None) -> dict[str, Any]:
    from app.services.platform_settings import resolve_billtrack

    cfg = resolve_billtrack(db)
    params = connection_params(cfg)
    params["enabled"] = bool(cfg.get("enabled"))
    return params


# Padrón BillTrack (Ecolan): api_person + email/phone.
# DNI del portal (7–8 dígitos) vs doc_cuit: igual exacto o CUIT AR (11 dígitos, DNI en posiciones 3–10).
DEFAULT_LOOKUP_SQL = """
SELECT
  p.id::text AS ref,
  TRIM(BOTH FROM CONCAT(COALESCE(p.first_name, ''), ' ', COALESCE(p.last_name, ''))) AS nombre,
  e.email AS email,
  ph.phone AS telefono,
  COALESCE(NULLIF(TRIM(p.client_state), ''), NULLIF(TRIM(p.billing_state), ''), '') AS activo,
  COALESCE(p.billing_balance::text, '0') AS deuda,
  p.doc_cuit AS doc_cuit,
  COALESCE(p.partner_number::text, '') AS partner_number,
  COALESCE(p.client_number::text, '') AS client_number
FROM public.api_person p
LEFT JOIN LATERAL (
  SELECT email
  FROM public.api_person_email
  WHERE person_id = p.id AND NULLIF(TRIM(email), '') IS NOT NULL
  ORDER BY id ASC
  LIMIT 1
) e ON TRUE
LEFT JOIN LATERAL (
  SELECT phone
  FROM public.api_person_phone
  WHERE person_id = p.id AND NULLIF(TRIM(phone), '') IS NOT NULL
  ORDER BY id ASC
  LIMIT 1
) ph ON TRUE
WHERE (
  regexp_replace(COALESCE(p.doc_cuit, ''), '[^0-9]', '', 'g') = :dni
  OR (
    length(regexp_replace(COALESCE(p.doc_cuit, ''), '[^0-9]', '', 'g')) = 11
    AND substring(
      regexp_replace(COALESCE(p.doc_cuit, ''), '[^0-9]', '', 'g') FROM 3 FOR 8
    ) = lpad(:dni, 8, '0')
  )
)
LIMIT 1
""".strip()

_ACTIVE_STATES = frozenset(
    {
        "1",
        "true",
        "yes",
        "si",
        "sí",
        "activo",
        "active",
        "habilitado",
        "a",
        "ok",
        "al dia",
        "al día",
        "enabled",
        "normal",
        "vigente",
    }
)
_INACTIVE_STATES = frozenset(
    {
        "0",
        "false",
        "no",
        "inactivo",
        "inactive",
        "baja",
        "de baja",
        "disabled",
        "suspendido",
        "suspended",
        "cancelled",
        "cancelado",
        "moroso",
        "corte",
        "bloqueado",
    }
)


def lookup_sql() -> str:
    from app.config import BILLTRACK_LOOKUP_SQL

    return (BILLTRACK_LOOKUP_SQL or DEFAULT_LOOKUP_SQL).strip()


def _lookup_forced_off() -> bool:
    import os

    raw = os.getenv("BILLTRACK_LOOKUP_READY", "").strip().lower()
    return raw in ("0", "false", "no", "off")


def _map_activo(raw: Any) -> bool:
    val = str(raw or "").strip().lower()
    if not val:
        return True  # sin estado → permitir intento de auth; el OTP valida contacto
    if val in _INACTIVE_STATES:
        return False
    if val in _ACTIVE_STATES:
        return True
    # Estados desconocidos: no bloquear (BillTrack puede usar códigos propios)
    return True


def map_lookup_row(row: dict[str, Any], *, dni_n: str) -> dict[str, Any]:
    """Normaliza una fila BillTrack al dict del portal/bot."""
    estado_raw = str(row.get("activo") if row.get("activo") is not None else row.get("estado") or "").strip()
    return {
        "ref": str(row.get("ref") or row.get("id") or dni_n),
        "email": str(row.get("email") or row.get("correo") or "").strip(),
        "telefono": str(row.get("telefono") or row.get("msisdn") or row.get("phone") or "").strip(),
        "nombre": str(row.get("nombre") or "").strip(),
        "activo": _map_activo(estado_raw),
        "estado_padron": estado_raw.lower(),
        "dni": dni_n,
        "deuda": str(row.get("deuda") or row.get("billing_balance") or "0").strip(),
        "doc_cuit": str(row.get("doc_cuit") or "").strip(),
        "partner_number": str(row.get("partner_number") or "").strip(),
        "client_number": str(row.get("client_number") or "").strip(),
        "fuente": "billtrack",
    }


def lookup_abonado_por_dni(
    dni: str,
    *,
    org_slug: str = "",
    linea: str = "",
    db: Session | None = None,
) -> dict[str, Any] | None:
    """Consulta padrón BillTrack (RO). Retorna dict o None.

    SQL: BILLTRACK_LOOKUP_SQL o DEFAULT_LOOKUP_SQL (api_person).
    Placeholders: :dni, :org_slug, :linea.
    """
    from app.config import BILLTRACK_ENABLED, es_produccion
    from app.estate.security import normalizar_dni, valid_dni_ar

    dni_n = normalizar_dni(dni)
    if not valid_dni_ar(dni_n):
        return None

    params = resolve_connection(db)
    enabled = bool(params.get("enabled")) or BILLTRACK_ENABLED
    url = str(params.get("url") or "").strip()
    sql = lookup_sql()
    use_real = enabled and bool(url) and bool(sql) and not _lookup_forced_off()

    if not use_real:
        if es_produccion():
            return None
        return _mock_lookup(dni_n, org_slug=org_slug, linea=linea, db=db)

    from sqlalchemy import create_engine, text

    sslmode = str(params.get("sslmode") or "disable")
    connect_args: dict[str, Any] = {"connect_timeout": 8, "sslmode": sslmode}

    engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
    try:
        with engine.connect() as conn:
            cleaned = sql.strip().rstrip(";")
            if not cleaned.lower().startswith("select") and not cleaned.lower().startswith("with"):
                raise ValueError("BILLTRACK_LOOKUP_SQL debe ser un SELECT (o WITH … SELECT)")
            row = (
                conn.execute(
                    text(cleaned),
                    {"dni": dni_n, "org_slug": org_slug or "", "linea": (linea or "").strip()},
                )
                .mappings()
                .first()
            )
            if not row:
                return None
            return map_lookup_row(dict(row), dni_n=dni_n)
    except Exception:
        logger.exception("BillTrack lookup falló (dni=***%s)", dni_n[-3:] if dni_n else "")
        # Nunca tumbar portal/auth: en prod devolver None; en dev/mock local.
        if es_produccion():
            return None
        return _mock_lookup(dni_n, org_slug=org_slug, linea=linea, db=db)
    finally:
        engine.dispose()


# Servicios de conectividad fijos (api_service.service_type_code)
SERVICE_TYPE_CONECTIVIDAD = frozenset({"INTFO", "INTBA", "INTINA"})
SERVICE_TYPE_MOVIL = frozenset(
    {"CEL", "CELU", "MOVIL", "MOVI", "IMOWI", "TELMOV", "TELM", "GSM", "LTE", "MVNO"}
)
_HINTS_INTERNET = (
    "internet",
    "fibra",
    "adsl",
    "ftth",
    "intfo",
    "intba",
    "intina",
    "wireless",
    "bai",
    "radio",
)
_HINTS_MOVIL = (
    "imowi",
    "imovi",
    "móvil",
    "movil",
    "celular",
    "gsm",
    "lte",
    "mvno",
    "telmov",
    "telefonia movil",
    "telefonía móvil",
)

DEFAULT_SERVICES_SQL = """
SELECT
  s.id::text AS id,
  COALESCE(NULLIF(TRIM(s.identifier), ''), '') AS login,
  COALESCE(NULLIF(TRIM(s.label), ''), '') AS label,
  COALESCE(NULLIF(TRIM(s.state), ''), '') AS state,
  COALESCE(NULLIF(TRIM(s.account_name), ''), '') AS account_name,
  COALESCE(NULLIF(TRIM(s.base_account_number), ''), '') AS base_account_number,
  COALESCE(NULLIF(TRIM(s.product_code), ''), '') AS product_code,
  COALESCE(NULLIF(TRIM(s.product), ''), '') AS product,
  COALESCE(s.service_on::text, '') AS service_on,
  COALESCE(NULLIF(TRIM(s.service_type_code), ''), '') AS service_type_code,
  COALESCE(NULLIF(TRIM(s.service_type_label), ''), '') AS service_type_label,
  COALESCE(NULLIF(TRIM(s.locality), ''), '') AS locality,
  s.last_state_date,
  s.effective_date_from,
  s.effective_date_to
FROM public.api_service s
WHERE regexp_replace(COALESCE(s.base_account_number, ''), '[^0-9A-Za-z]', '', 'g')
    = regexp_replace(CAST(:client_number AS text), '[^0-9A-Za-z]', '', 'g')
  AND UPPER(TRIM(COALESCE(s.service_type_code, ''))) IN ('INTFO', 'INTBA', 'INTINA')
ORDER BY
  CASE
    WHEN LOWER(COALESCE(s.service_on::text, '')) IN ('1', 't', 'true', 'yes', 'on', 'si', 'sí')
      THEN 0
    ELSE 1
  END,
  s.last_state_date DESC NULLS LAST,
  s.id DESC
""".strip()

DEFAULT_SERVICES_BY_DNI_SQL = """
SELECT
  s.id::text AS id,
  COALESCE(NULLIF(TRIM(s.identifier), ''), '') AS login,
  COALESCE(NULLIF(TRIM(s.label), ''), '') AS label,
  COALESCE(NULLIF(TRIM(s.state), ''), '') AS state,
  COALESCE(NULLIF(TRIM(s.account_name), ''), '') AS account_name,
  COALESCE(NULLIF(TRIM(s.base_account_number), ''), '') AS base_account_number,
  COALESCE(NULLIF(TRIM(s.product_code), ''), '') AS product_code,
  COALESCE(NULLIF(TRIM(s.product), ''), '') AS product,
  COALESCE(s.service_on::text, '') AS service_on,
  COALESCE(NULLIF(TRIM(s.service_type_code), ''), '') AS service_type_code,
  COALESCE(NULLIF(TRIM(s.service_type_label), ''), '') AS service_type_label,
  COALESCE(NULLIF(TRIM(s.locality), ''), '') AS locality,
  s.last_state_date,
  s.effective_date_from,
  s.effective_date_to
FROM public.api_person p
INNER JOIN public.api_service s
  ON regexp_replace(COALESCE(s.base_account_number, ''), '[^0-9A-Za-z]', '', 'g')
   = regexp_replace(COALESCE(p.client_number::text, ''), '[^0-9A-Za-z]', '', 'g')
WHERE (
  regexp_replace(COALESCE(p.doc_cuit, ''), '[^0-9]', '', 'g') = :dni
  OR (
    length(regexp_replace(COALESCE(p.doc_cuit, ''), '[^0-9]', '', 'g')) = 11
    AND substring(
      regexp_replace(COALESCE(p.doc_cuit, ''), '[^0-9]', '', 'g') FROM 3 FOR 8
    ) = lpad(:dni, 8, '0')
  )
)
  AND UPPER(TRIM(COALESCE(s.service_type_code, ''))) IN ('INTFO', 'INTBA', 'INTINA')
ORDER BY
  CASE
    WHEN LOWER(COALESCE(s.service_on::text, '')) IN ('1', 't', 'true', 'yes', 'on', 'si', 'sí')
      THEN 0
    ELSE 1
  END,
  s.last_state_date DESC NULLS LAST,
  s.id DESC
""".strip()

# Todos los productos de la cuenta (internet, móvil, TV, etc.) para armar el menú N1.
DEFAULT_SERVICES_CUENTA_BY_DNI_SQL = """
SELECT
  s.id::text AS id,
  COALESCE(NULLIF(TRIM(s.identifier), ''), '') AS login,
  COALESCE(NULLIF(TRIM(s.label), ''), '') AS label,
  COALESCE(NULLIF(TRIM(s.state), ''), '') AS state,
  COALESCE(NULLIF(TRIM(s.account_name), ''), '') AS account_name,
  COALESCE(NULLIF(TRIM(s.base_account_number), ''), '') AS base_account_number,
  COALESCE(NULLIF(TRIM(s.product_code), ''), '') AS product_code,
  COALESCE(NULLIF(TRIM(s.product), ''), '') AS product,
  COALESCE(s.service_on::text, '') AS service_on,
  COALESCE(NULLIF(TRIM(s.service_type_code), ''), '') AS service_type_code,
  COALESCE(NULLIF(TRIM(s.service_type_label), ''), '') AS service_type_label,
  COALESCE(NULLIF(TRIM(s.locality), ''), '') AS locality,
  s.last_state_date,
  s.effective_date_from,
  s.effective_date_to
FROM public.api_person p
INNER JOIN public.api_service s
  ON regexp_replace(COALESCE(s.base_account_number, ''), '[^0-9A-Za-z]', '', 'g')
   = regexp_replace(COALESCE(p.client_number::text, ''), '[^0-9A-Za-z]', '', 'g')
WHERE (
  regexp_replace(COALESCE(p.doc_cuit, ''), '[^0-9]', '', 'g') = :dni
  OR (
    length(regexp_replace(COALESCE(p.doc_cuit, ''), '[^0-9]', '', 'g')) = 11
    AND substring(
      regexp_replace(COALESCE(p.doc_cuit, ''), '[^0-9]', '', 'g') FROM 3 FOR 8
    ) = lpad(:dni, 8, '0')
  )
)
ORDER BY
  CASE
    WHEN LOWER(COALESCE(s.service_on::text, '')) IN ('1', 't', 'true', 'yes', 'on', 'si', 'sí')
      THEN 0
    ELSE 1
  END,
  s.last_state_date DESC NULLS LAST,
  s.id DESC
LIMIT 80
""".strip()


def _truthy_service_on(raw: Any) -> bool:
    val = str(raw or "").strip().lower()
    if not val:
        return True
    if val in ("0", "f", "false", "no", "off", "n"):
        return False
    return val in ("1", "t", "true", "yes", "on", "si", "sí", "y")


def map_service_row(row: dict[str, Any]) -> Any:
    """Normaliza fila api_service → ServicioConectividad."""
    from app.radius.contract import ServicioConectividad

    code = str(row.get("service_type_code") or "").strip().upper()
    login = str(row.get("login") or row.get("identifier") or "").strip()
    return ServicioConectividad(
        login=login,
        service_type_code=code,
        service_type_label=str(row.get("service_type_label") or "").strip(),
        product=str(row.get("product") or "").strip(),
        label=str(row.get("label") or "").strip(),
        state=str(row.get("state") or "").strip(),
        service_on=_truthy_service_on(row.get("service_on")),
        base_account_number=str(row.get("base_account_number") or "").strip(),
        id=str(row.get("id") or "").strip(),
        locality=str(row.get("locality") or "").strip(),
    )


def _blob_servicio(svc: Any) -> str:
    return " ".join(
        str(getattr(svc, k, "") or "")
        for k in ("service_type_code", "service_type_label", "product", "label")
    ).lower()


def es_servicio_internet_cuenta(svc: Any) -> bool:
    code = str(getattr(svc, "service_type_code", "") or "").strip().upper()
    if code in SERVICE_TYPE_CONECTIVIDAD:
        return True
    blob = _blob_servicio(svc)
    return any(k in blob for k in _HINTS_INTERNET)


def es_servicio_movil_cuenta(svc: Any) -> bool:
    code = str(getattr(svc, "service_type_code", "") or "").strip().upper()
    if code in SERVICE_TYPE_MOVIL:
        return True
    blob = _blob_servicio(svc)
    return any(k in blob for k in _HINTS_MOVIL)


def clasificar_servicios_cuenta(servicios: list[Any]) -> str:
    """internet | movil | ambos | '' (consultó y no hay match)."""
    has_inet = any(es_servicio_internet_cuenta(s) for s in (servicios or []))
    has_mov = any(es_servicio_movil_cuenta(s) for s in (servicios or []))
    if has_inet and has_mov:
        return "ambos"
    if has_inet:
        return "internet"
    if has_mov:
        return "movil"
    return ""


def elegir_servicio_principal(servicios: list[Any]) -> Any | None:
    """Prioriza service_on + login no vacío."""
    with_login = [s for s in servicios if getattr(s, "login", "")]
    if not with_login:
        return None
    on = [s for s in with_login if getattr(s, "service_on", True)]
    return (on or with_login)[0]


_RE_LOGIN_RADIUS = re.compile(r"\b([a-z0-9]{3,}(?:BAI|bai))\b")


def extraer_login_en_texto(texto: str, servicios: list[Any] | None = None) -> str:
    """Detecta username Radius en el mensaje (ej. tupaciretacuidaBAI)."""
    raw = (texto or "").strip()
    if not raw:
        return ""
    tl = raw.lower()
    for svc in servicios or []:
        login = str(getattr(svc, "login", "") or "").strip()
        if login and login.lower() in tl:
            return login
    m = _RE_LOGIN_RADIUS.search(raw)
    if m:
        return m.group(1)
    return ""


def resolver_login_consulta(
    texto: str,
    servicios: list[Any] | None,
    *,
    login_ctx: str = "",
) -> str:
    """Login activo: mensaje > contexto > único servicio del padrón."""
    login = extraer_login_en_texto(texto, servicios)
    if login:
        return login
    login_ctx = (login_ctx or "").strip()
    if login_ctx:
        return login_ctx
    svcs = [s for s in (servicios or []) if getattr(s, "login", "")]
    if len(svcs) == 1:
        return str(getattr(svcs[0], "login", "") or "").strip()
    return ""


def listar_logins_conectividad(servicios: list[Any] | None) -> list[str]:
    out: list[str] = []
    for svc in servicios or []:
        login = str(getattr(svc, "login", "") or "").strip()
        if login and login not in out:
            out.append(login)
    return out


def mensaje_seleccion_cuenta_internet(
    logins: list[str],
    *,
    repregunta: bool = False,
) -> str:
    cuentas = ", ".join(logins)
    if repregunta:
        return (
            f"¿Cuál de estas cuentas tiene el problema? {cuentas}. "
            "Decime el usuario (ej. tupaciretacuidaBAI)."
        )
    n = len(logins)
    return (
        f"Veo que tenés {n} cuentas de internet: {cuentas}. "
        "¿Con cuál tenés el problema? Decime el usuario (ej. tupaciretacuidaBAI)."
    )


def _billtrack_engine(db: Session | None = None):
    from app.config import BILLTRACK_ENABLED, es_produccion

    params = resolve_connection(db)
    enabled = bool(params.get("enabled")) or BILLTRACK_ENABLED
    url = str(params.get("url") or "").strip()
    if not (enabled and url) or _lookup_forced_off():
        return None, params, es_produccion()
    from sqlalchemy import create_engine

    sslmode = str(params.get("sslmode") or "disable")
    connect_args: dict[str, Any] = {"connect_timeout": 8, "sslmode": sslmode}
    engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
    return engine, params, es_produccion()


def _mock_servicios(client_number: str = "", dni: str = "") -> list[Any]:
    """Servicios demo cuando BillTrack no está configurado (dev/tests)."""
    from app.radius.contract import ServicioConectividad

    key = (client_number or dni or "").strip()
    catalog: dict[str, list[ServicioConectividad]] = {
        "200": [
            ServicioConectividad(
                login="4640854",
                service_type_code="INTFO",
                service_type_label="Fibra Optica",
                product="Fibra 100",
                label="Internet Fibra",
                service_on=True,
                base_account_number="200",
                id="svc-1",
            )
        ],
        "30111222": [
            ServicioConectividad(
                login="4640854",
                service_type_code="INTFO",
                service_type_label="Fibra Optica",
                product="Fibra 100",
                label="Internet Fibra",
                service_on=True,
                base_account_number="200",
                id="svc-1",
            ),
            ServicioConectividad(
                login="",
                service_type_code="IMOWI",
                service_type_label="Móvil IMOWI",
                product="Móvil 5GB",
                label="Telefonía móvil",
                service_on=True,
                base_account_number="200",
                id="svc-mov",
            ),
        ],
    }
    return list(catalog.get(key, []))


def lookup_servicios_conectividad(
    *,
    client_number: str,
    db: Session | None = None,
) -> list[Any]:
    """Lista servicios INTFO/INTBA/INTINA de api_service por base_account_number."""
    from sqlalchemy import text

    cn = str(client_number or "").strip()
    if not cn:
        return []

    engine, _params, prod = _billtrack_engine(db)
    if engine is None:
        if prod:
            return []
        return _mock_servicios(client_number=cn)

    try:
        with engine.connect() as conn:
            rows = (
                conn.execute(text(DEFAULT_SERVICES_SQL), {"client_number": cn})
                .mappings()
                .all()
            )
            out = []
            for row in rows:
                svc = map_service_row(dict(row))
                if svc.login and svc.service_type_code in SERVICE_TYPE_CONECTIVIDAD:
                    out.append(svc)
            return out
    except Exception:
        logger.exception("BillTrack api_service falló (client_number)")
        if prod:
            return []
        return _mock_servicios(client_number=cn)
    finally:
        engine.dispose()


def lookup_servicios_conectividad_por_dni(
    *,
    dni: str,
    db: Session | None = None,
) -> list[Any]:
    """Servicios de conectividad vía join api_person.doc_cuit → api_service."""
    from sqlalchemy import text

    from app.estate.security import normalizar_dni, valid_dni_ar

    dni_n = normalizar_dni(dni)
    if not valid_dni_ar(dni_n):
        return []

    engine, _params, prod = _billtrack_engine(db)
    if engine is None:
        if prod:
            return []
        return _mock_servicios(dni=dni_n)

    try:
        with engine.connect() as conn:
            rows = (
                conn.execute(text(DEFAULT_SERVICES_BY_DNI_SQL), {"dni": dni_n})
                .mappings()
                .all()
            )
            out = []
            for row in rows:
                svc = map_service_row(dict(row))
                if svc.login and svc.service_type_code in SERVICE_TYPE_CONECTIVIDAD:
                    out.append(svc)
            return out
    except Exception:
        logger.exception("BillTrack api_service por DNI falló (dni=***%s)", dni_n[-3:])
        if prod:
            return []
        return _mock_servicios(dni=dni_n)
    finally:
        engine.dispose()


def lookup_servicios_cuenta_por_dni(
    *,
    dni: str,
    db: Session | None = None,
) -> tuple[list[Any], bool]:
    """Todos los api_service del DNI. (lista, consulta_ok).

    consulta_ok=False si BillTrack no está disponible o falló: no inferir productos.
    lista vacía + ok=True = consultó y no hay productos (p. ej. sin internet fijo).
    """
    from sqlalchemy import text

    from app.estate.security import normalizar_dni, valid_dni_ar

    dni_n = normalizar_dni(dni)
    if not valid_dni_ar(dni_n):
        return [], False

    engine, _params, prod = _billtrack_engine(db)
    if engine is None:
        if prod:
            return [], False
        return _mock_servicios(dni=dni_n), True

    try:
        with engine.connect() as conn:
            rows = (
                conn.execute(text(DEFAULT_SERVICES_CUENTA_BY_DNI_SQL), {"dni": dni_n})
                .mappings()
                .all()
            )
            out = [map_service_row(dict(row)) for row in rows]
            return out, True
    except Exception:
        logger.exception("BillTrack api_service cuenta por DNI falló (dni=***%s)", dni_n[-3:])
        if prod:
            return [], False
        return _mock_servicios(dni=dni_n), True
    finally:
        engine.dispose()


def resolver_servicio_contratado(
    dni: str,
    *,
    db: Session | None = None,
) -> str | None:
    """internet|movil|ambos|'' si consultó; None si no se pudo leer el padrón."""
    svcs, ok = lookup_servicios_cuenta_por_dni(dni=dni, db=db)
    if not ok:
        return None
    return clasificar_servicios_cuenta(svcs)


def ensure_local_abonado(
    db: Session,
    org_id: str,
    hit: dict[str, Any],
) -> Any:
    """Crea/actualiza réplica mínima en Data Estate a partir del hit BillTrack."""
    from app.estate import canal_repo as crepo
    from app.estate.models import Abonado

    dni_n = str(hit.get("dni") or "").strip()
    abo = crepo.find_abonado_por_dni(db, org_id, dni_n) if dni_n else None
    estado_padron = str(hit.get("estado_padron") or "").strip().lower()
    if "baja" in estado_padron:
        estado = "baja"
    elif hit.get("activo", True):
        estado = "activo"
    elif any(k in estado_padron for k in ("corte", "suspend", "mora")):
        estado = "suspendido" if "suspend" in estado_padron else "corte"
    else:
        estado = "suspendido"
    nombre = str(hit.get("nombre") or "").strip()
    tel = str(hit.get("telefono") or "").strip()
    deuda = str(hit.get("deuda") or "0").strip() or "0"
    servicio_padron: str | None = None
    try:
        servicio_padron = resolver_servicio_contratado(dni_n, db=db)
    except Exception:
        logger.debug("No se pudo resolver servicios contratados", exc_info=True)
        servicio_padron = None

    if abo is None:
        if servicio_padron:
            servicio = servicio_padron
        elif servicio_padron == "":
            servicio = "movil" if tel else ""
        else:
            servicio = ""
        abo = Abonado(
            organizacion_id=org_id,
            dni=dni_n,
            nombre=nombre,
            telefono_e164=tel,
            linea_msisdn="".join(c for c in tel if c.isdigit())[-10:] if tel else "",
            estado=estado,
            deuda_monto=deuda,
            plan=str(hit.get("plan") or "").strip(),
            servicio=servicio,
        )
        db.add(abo)
    else:
        if nombre:
            abo.nombre = nombre
        if tel:
            abo.telefono_e164 = tel
            digits = "".join(c for c in tel if c.isdigit())
            if digits:
                abo.linea_msisdn = digits[-10:]
        abo.estado = estado
        abo.deuda_monto = deuda
        if servicio_padron:
            abo.servicio = servicio_padron
        elif servicio_padron == "":
            prev = (abo.servicio or "").strip().lower()
            if prev in ("movil", "ambos") or tel or abo.linea_msisdn:
                abo.servicio = "movil"
            else:
                abo.servicio = ""
    try:
        from app.services.velocidad_plan import extraer_mbps_plan

        inet = lookup_servicios_conectividad_por_dni(dni=dni_n, db=db)
        svc = elegir_servicio_principal(inet)
        if svc:
            blob = " ".join(
                x for x in (svc.product, svc.label) if str(x or "").strip()
            ).strip()
            if blob and (extraer_mbps_plan(blob) or not (abo.plan or "").strip()):
                abo.plan = blob
    except Exception:
        logger.debug("No se pudo completar plan desde api_service", exc_info=True)
    db.commit()
    db.refresh(abo)
    return abo


def _mock_lookup(
    dni_n: str,
    *,
    org_slug: str = "",
    linea: str = "",
    db: Session | None = None,
) -> dict[str, Any] | None:
    """Fallback desarrollo: padrón local abonados (NO es auth; solo simula BillTrack)."""
    if db is None:
        # Catálogo fijo para tests sin DB
        catalog = {
            "30111222": {
                "ref": "BT-30111222",
                "email": "maria.gonzalez@example.com",
                "telefono": "5492235551234",
                "nombre": "María González",
                "activo": True,
            },
            "28555666": {
                "ref": "BT-28555666",
                "email": "carlos.perez@example.com",
                "telefono": "5492235555678",
                "nombre": "Carlos Pérez",
                "activo": True,
            },
            "32123456": {
                "ref": "BT-32123456",
                "email": "ana.ruiz@example.com",
                "telefono": "5492235559012",
                "nombre": "Ana Ruiz",
                "activo": False,
            },
            "29888777": {
                "ref": "BT-29888777",
                "email": "laura.diaz@example.com",
                "telefono": "5492235560002",
                "nombre": "Laura Díaz",
                "activo": True,
            },
            "26444555": {
                "ref": "BT-26444555",
                "email": "pedro.ecolan@example.com",
                "telefono": "5492235560099",
                "nombre": "Pedro Ecolan",
                "activo": True,
            },
        }
        hit = catalog.get(dni_n)
        if not hit:
            return None
        if linea and hit.get("telefono") and linea not in str(hit["telefono"]):
            return None
        return {**hit, "dni": dni_n, "fuente": "mock"}

    from app.estate import canal_repo as crepo
    from app.estate import repository as repo

    slug = org_slug or "coop-batan"
    org = repo.get_org_by_slug(db, slug)
    if not org:
        return None
    abo = crepo.find_abonado_por_dni(db, org.id, dni_n)
    if not abo:
        return None
    if linea:
        lin = "".join(c for c in linea if c.isdigit())
        tel = "".join(c for c in (abo.telefono_e164 or "") if c.isdigit())
        msisdn = "".join(c for c in (abo.linea_msisdn or "") if c.isdigit())
        if lin and lin not in tel and lin not in msisdn:
            return None
    email = f"{(abo.nombre or 'abonado').split()[0].lower()}.portal@example.com"
    return {
        "ref": abo.id,
        "email": email,
        "telefono": abo.telefono_e164 or "",
        "nombre": abo.nombre or "",
        "activo": (abo.estado or "").lower() in ("activo", "al dia", "al día", ""),
        "dni": dni_n,
        "fuente": "mock_local",
    }