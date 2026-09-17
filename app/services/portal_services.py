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


def _dto(svc: Any) -> dict[str, Any] | None:
    sid = str(getattr(svc, "id", "") or "").strip()
    if not sid:
        return None
    return {
        "id": sid,
        "type": canonical_service_type(svc),
        "label": _source_label(svc),
        "product": _source_product(svc),
        "active": bool(bt.servicio_habilitado(svc)),
    }


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
        row = _dto(svc)
        if row is None or row["id"] in seen:
            continue
        seen.add(row["id"])
        items.append(row)

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
