"""Portal: catálogo tipado de servicios del abonado (administrativo).

No consulta BCM, Radius, UISP, JSC, Sensa ni PBX.
Fuente: BillTrack api_service vía lookup_servicios_cuenta_por_dni.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.estate.models import Abonado
from app.services import billtrack as bt

logger = logging.getLogger("operations_hub")

CanonicalType = Literal["internet", "tv", "movil", "telefonia", "other"]

# Códigos BillTrack estables → tipo canónico (G0/G1).
# No mapear por label solo; los hints de billtrack son respaldo tras el código.
SERVICE_TYPE_TELEFONIA = frozenset(
    {
        # G0: sin códigos de telefonía fija documentados en el repo.
        # Reservado para cuando BillTrack exponga códigos estables.
    }
)

# Hints secundarios solo para fija (no solapan con _HINTS_MOVIL de billtrack).
_HINTS_TELEFONIA = (
    "telefono fijo",
    "telefonía fija",
    "telefonia fija",
    "tel fija",
    "linea fija",
    "línea fija",
)

_TYPE_ORDER = ("internet", "tv", "movil", "telefonia", "other")

# Históricos que no deben listarse en Home (sí se muestran corte/suspendido).
_ESTADOS_HISTORICOS = frozenset(
    {
        "baja",
        "cancelado",
        "cancelada",
        "inactivo",
        "inactiva",
        "de baja",
        "dado de baja",
        "dada de baja",
    }
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _blob(svc: Any) -> str:
    return " ".join(
        str(getattr(svc, k, "") or "")
        for k in ("service_type_code", "service_type_label", "product", "label")
    ).lower()


def canonical_service_type(svc: Any) -> CanonicalType:
    """Mapea un api_service a tipo canónico. Prioriza service_type_code."""
    code = str(getattr(svc, "service_type_code", "") or "").strip().upper()
    if code in bt.SERVICE_TYPE_CONECTIVIDAD:
        return "internet"
    if code in bt.SERVICE_TYPE_TV:
        return "tv"
    if code in bt.SERVICE_TYPE_MOVIL:
        return "movil"
    if code in SERVICE_TYPE_TELEFONIA:
        return "telefonia"

    # Respaldo: clasificadores existentes (código vacío / legado).
    if bt.es_servicio_internet_cuenta(svc):
        return "internet"
    if bt.es_servicio_tv_cuenta(svc):
        return "tv"
    if bt.es_servicio_movil_cuenta(svc):
        return "movil"

    blob = _blob(svc)
    if any(h in blob for h in _HINTS_TELEFONIA):
        return "telefonia"
    return "other"


def _source_label(svc: Any) -> str:
    """Texto de la fuente. No inventar nombre de producto ni tipo."""
    for key in ("label", "service_type_label"):
        val = str(getattr(svc, key, "") or "").strip()
        if val:
            return val
    return ""


def _source_product(svc: Any) -> str | None:
    val = str(getattr(svc, "product", "") or "").strip()
    return val or None


def es_historico_catalogo(svc: Any) -> bool:
    """True si es baja/cancelado: no mostrar en catálogo Home."""
    st = str(getattr(svc, "state", "") or "").strip().lower()
    if st in _ESTADOS_HISTORICOS or st.startswith("baja") or "baja" in st:
        return True
    # service_on falsy + sin estado vivo → réplica histórica típica en BillTrack
    if st not in ("habilitado", "activo", "activa", "enabled", "suspendido", "suspendida", "corte", "cortado"):
        on_raw = getattr(svc, "service_on", True)
        if isinstance(on_raw, bool):
            on = on_raw
        else:
            on = str(on_raw or "").strip().lower() in (
                "1",
                "t",
                "true",
                "yes",
                "on",
                "si",
                "sí",
                "y",
                "",
            )
        if not on:
            return True
    return False


def _collapse_key(row: dict[str, Any]) -> tuple[str, str]:
    """Clave de colapso: internet/móvil por línea (login); TV/otros por producto."""
    tip = str(row.get("type") or "")
    if tip == "internet":
        login = (row.get("_login") or "").strip()
        if login:
            return tip, f"login:{login}"
        name = (row.get("product") or row.get("label") or "").strip().lower()
        return tip, f"name:{name}" if name else f"id:{row.get('id') or ''}"
    if tip in ("movil", "telefonia"):
        line = (row.get("msisdn") or row.get("_login") or row.get("id") or "").strip().lower()
        return tip, line
    name = (row.get("product") or row.get("label") or "").strip().lower()
    if tip == "tv":
        return tip, name
    return tip, name or str(row.get("id") or "")


def _conn_eligible(svc: Any) -> bool:
    """Verificable en Connectivity: login + código INT* (vigente)."""
    code = str(getattr(svc, "service_type_code", "") or "").strip().upper()
    login = str(getattr(svc, "login", "") or "").strip()
    return bool(login) and code in bt.SERVICE_TYPE_CONECTIVIDAD and bt.servicio_habilitado(svc)


def _msisdn_from_svc(svc: Any) -> str | None:
    """MSISDN desde identifier/login cuando parece teléfono (IMOWI)."""
    login = str(getattr(svc, "login", "") or "").strip()
    digits = "".join(c for c in login if c.isdigit())
    if len(digits) < 8:
        return None
    return digits[-10:] if len(digits) >= 10 else digits


def _prefer_row(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Prefiere activo; en internet, el id usable por Connectivity (login+INT*)."""
    if a.get("active") and not b.get("active"):
        return a
    if b.get("active") and not a.get("active"):
        return b
    if a.get("type") == "internet" or b.get("type") == "internet":
        if a.get("_conn") and not b.get("_conn"):
            return a
        if b.get("_conn") and not a.get("_conn"):
            return b
    return a


def _dto(svc: Any) -> dict[str, Any] | None:
    sid = str(getattr(svc, "id", "") or "").strip()
    if not sid:
        return None
    tip = canonical_service_type(svc)
    login = str(getattr(svc, "login", "") or "").strip()
    msisdn = _msisdn_from_svc(svc) if tip in ("movil", "telefonia") else None
    return {
        "id": sid,
        "type": tip,
        "label": _source_label(svc),
        "product": _source_product(svc),
        "active": bool(bt.servicio_habilitado(svc)),
        "msisdn": msisdn,
        # Solo para dedupe/prune; se elimina antes de responder.
        "_conn": _conn_eligible(svc),
        "_login": login.lower() if login else "",
    }


def _prune_internet_admin_replicas(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Si hay Internet verificable (login+INT*), oculta réplicas admin sin login."""
    has_conn = any(r.get("type") == "internet" and r.get("_conn") for r in items)
    if not has_conn:
        return items
    return [r for r in items if r.get("type") != "internet" or r.get("_conn")]


def _dedupe_catalog(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Colapsa réplicas; conserva varios Internet/móvil con login distinto."""
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for row in items:
        key = _collapse_key(row)
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = row
            order.append(key)
        else:
            by_key[key] = _prefer_row(prev, row)
    merged = [by_key[k] for k in order]
    merged = _prune_internet_admin_replicas(merged)
    out: list[dict[str, Any]] = []
    for row in merged:
        clean = {kk: vv for kk, vv in row.items() if not kk.startswith("_")}
        out.append(clean)
    return out


def evaluar_servicios_portal(
    db: Session,
    *,
    abonado: Abonado,
) -> dict[str, Any]:
    """Catálogo administrativo del abonado del JWT. Sin IDOR ni probes operativos."""
    dni = str(getattr(abonado, "dni", "") or "").strip()
    checked_at = _now_iso()

    if not dni:
        logger.info("portal_services: abonado sin DNI")
        return {
            "status": "unavailable",
            "checked_at": checked_at,
            "services": [],
            "reason_code": "missing_dni",
        }

    try:
        raw, ok = bt.lookup_servicios_cuenta_por_dni(dni=dni, db=db)
    except Exception:
        logger.exception("portal_services: BillTrack falló")
        return {
            "status": "unavailable",
            "checked_at": checked_at,
            "services": [],
            "reason_code": "source_error",
        }

    if not ok:
        return {
            "status": "unavailable",
            "checked_at": checked_at,
            "services": [],
            "reason_code": "source_unavailable",
        }

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for svc in raw or []:
        if es_historico_catalogo(svc):
            continue
        row = _dto(svc)
        if row is None or row["id"] in seen:
            continue
        seen.add(row["id"])
        items.append(row)

    items = _dedupe_catalog(items)

    items.sort(
        key=lambda r: (
            _TYPE_ORDER.index(r["type"]) if r["type"] in _TYPE_ORDER else 99,
            0 if r["active"] else 1,
            (r.get("label") or "").lower(),
            r["id"],
        )
    )

    return {
        "status": "ok",
        "checked_at": checked_at,
        "services": items,
        "reason_code": None,
    }
