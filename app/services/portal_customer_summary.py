"""Portal: facade de lectura Customer Summary (Fase 2D).

Compone lectores existentes. No materializa Customer 360, no sync, no probes
técnicos por defecto. Identidad solo desde el abonado del JWT.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.estate.models import Abonado

logger = logging.getLogger("operations_hub")

DomainStatus = Literal[
    "ok",
    "empty",
    "stale",
    "unavailable",
    "not_available",
    "omitted",
    "partial",
]

INCLUDE_DEFAULT = (
    "customer",
    "account",
    "services",
    "billing",
    "tickets",
    "ov",
)
INCLUDE_ALLOWED = frozenset(INCLUDE_DEFAULT)
REFRESH_ALLOWED = frozenset({"billing"})
ConnectivityMode = Literal["omit", "summary", "probe"]


def _now() -> datetime:
    return datetime.now(UTC)


def _domain(
    status: DomainStatus,
    data: Any = None,
    reason_code: str | None = None,
) -> dict[str, Any]:
    return {"status": status, "data": data, "reason_code": reason_code}


def parse_include(raw: str | None) -> list[str]:
    """Parsea CSV include. Default = INCLUDE_DEFAULT. Raise ValueError si inválido."""
    text = (raw or "").strip()
    if not text:
        return list(INCLUDE_DEFAULT)
    parts = [p.strip().lower() for p in text.split(",") if p.strip()]
    if not parts:
        return list(INCLUDE_DEFAULT)
    bad = [p for p in parts if p not in INCLUDE_ALLOWED]
    if bad:
        raise ValueError(f"include inválido: {', '.join(bad)}")
    # preservar orden de aparición, sin duplicados
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def parse_refresh(raw: str | None) -> list[str]:
    """Parsea CSV refresh. Solo 'billing' permitido. Raise ValueError si inválido."""
    text = (raw or "").strip()
    if not text:
        return []
    parts = [p.strip().lower() for p in text.split(",") if p.strip()]
    bad = [p for p in parts if p not in REFRESH_ALLOWED]
    if bad:
        raise ValueError(f"refresh inválido: {', '.join(bad)}")
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def parse_connectivity(raw: str | None) -> ConnectivityMode:
    text = (raw or "").strip().lower() or "omit"
    if text not in ("omit", "summary", "probe"):
        raise ValueError("connectivity debe ser omit|summary|probe")
    return text  # type: ignore[return-value]


def _build_customer(abonado: Abonado) -> dict[str, Any]:
    return _domain(
        "ok",
        {
            "id": str(abonado.id),
            "display_name": str(abonado.nombre or "").strip(),
            "organization_id": str(abonado.organizacion_id or ""),
        },
    )


def _account_data(abonado: Abonado) -> dict[str, Any]:
    return {
        "client_number": str(abonado.client_number or "").strip(),
        "status": str(abonado.estado or "").strip(),
        "plan": str(abonado.plan or "").strip(),
    }


def _balance_data(
    abonado: Abonado,
    *,
    as_of: str | None,
    freshness: str = "snapshot",
) -> dict[str, Any]:
    return {
        "amount": str(abonado.deuda_monto or "0").strip() or "0",
        "currency": "ARS",
        "as_of": as_of,
        "freshness": freshness,
    }


def _try_refresh_billing(
    db: Session,
    abonado: Abonado,
) -> tuple[Abonado, bool]:
    """Refresh vía lookup BillTrack + ensure_local_abonado. (abonado, ok)."""
    from app.services.billtrack import ensure_local_abonado, lookup_abonado_por_dni

    dni = str(abonado.dni or "").strip()
    if not dni:
        return abonado, False
    try:
        hit = lookup_abonado_por_dni(dni, db=db)
    except Exception:
        logger.exception("customer_summary: BillTrack lookup falló")
        return abonado, False
    if not hit:
        return abonado, False
    try:
        refreshed = ensure_local_abonado(
            db,
            str(abonado.organizacion_id),
            {**hit, "dni": dni},
        )
        return refreshed, True
    except Exception:
        logger.exception("customer_summary: ensure_local_abonado falló")
        return abonado, False


def _build_services(db: Session, abonado: Abonado) -> dict[str, Any]:
    from app.services.portal_services import evaluar_servicios_portal

    raw = evaluar_servicios_portal(db, abonado=abonado)
    status_raw = str(raw.get("status") or "")
    items = list(raw.get("services") or [])
    checked_at = str(raw.get("checked_at") or "")
    reason = raw.get("reason_code")
    reason_s = str(reason) if reason else None

    data = {"checked_at": checked_at, "items": items}
    if status_raw == "unavailable":
        return _domain("unavailable", data, reason_s or "source_unavailable")
    if not items:
        return _domain("empty", data, None)
    return _domain("ok", data, None)


def _build_tickets(
    db: Session,
    org_id: str,
    abonado: Abonado,
    *,
    ticket_out_fn,
    tickets_visibles_fn,
) -> dict[str, Any]:
    try:
        rows = tickets_visibles_fn(db, org_id, abonado)
        items = [
            ticket_out_fn(t, conversacion_id=cid) for t, cid in rows
        ]
    except Exception:
        logger.exception("customer_summary: tickets falló")
        return _domain("unavailable", {"items": []}, "source_unavailable")
    if not items:
        return _domain("empty", {"items": []}, None)
    return _domain("ok", {"items": items}, None)


def _build_connectivity_summary(db: Session, abonado: Abonado) -> dict[str, Any]:
    """Catálogo INT* sin probes BCM/UISP/Radius."""
    from app.services.portal_connectivity import _load_catalog, _service_option

    try:
        refs = _load_catalog(db, abonado)
    except Exception:
        logger.exception("customer_summary: connectivity summary catalog falló")
        return _domain("unavailable", None, "source_unavailable")

    options = [_service_option(r) for r in refs]
    needs = len(refs) > 1
    return _domain(
        "ok" if refs else "empty",
        {
            "needs_service_selection": needs,
            "services": options,
            "count": len(refs),
        },
        "service_selection_required" if needs else None,
    )


def _service_id_in_catalog(db: Session, abonado: Abonado, service_id: str) -> bool:
    from app.services.portal_connectivity import _load_catalog

    sid = (service_id or "").strip()
    if not sid:
        return True
    refs = _load_catalog(db, abonado)
    return any(r.id == sid for r in refs)


def _connectivity_probe_payload(
    raw: dict[str, Any],
) -> dict[str, Any]:
    """Proyección customer-safe (sin evidence/recommendation internos)."""
    return {
        "status": raw.get("status"),
        "freshness": raw.get("freshness"),
        "checked_at": raw.get("checked_at"),
        "message": raw.get("message"),
        "access_technology": raw.get("access_technology"),
        "service": raw.get("service"),
        "incident": raw.get("incident"),
        "actions": raw.get("actions"),
        "needs_service_selection": raw.get("needs_service_selection"),
        "services": raw.get("services"),
        "reason_code": raw.get("reason_code"),
    }


def evaluar_customer_summary(
    db: Session,
    *,
    abonado: Abonado,
    org_id: str,
    include: list[str],
    refresh: list[str],
    connectivity: ConnectivityMode,
    service_id: str | None = None,
    canal: str = "app",
    conversacion_id: str = "",
    ticket_out_fn=None,
    tickets_visibles_fn=None,
) -> dict[str, Any]:
    """Compone el contrato Customer Summary. No acepta identidad externa."""
    generated_at = _now().isoformat()
    refresh_applied: list[str] = []
    include_set = set(include)

    # --- billing refresh (actualiza abonado en memoria/DB) ---
    billing_refresh_ok: bool | None = None
    if "billing" in refresh:
        abonado, billing_refresh_ok = _try_refresh_billing(db, abonado)
        if billing_refresh_ok:
            refresh_applied.append("billing")

    # --- customer ---
    if "customer" in include_set:
        customer = _build_customer(abonado)
    else:
        customer = _domain("omitted")

    # --- account ---
    if "account" in include_set:
        if billing_refresh_ok is True:
            account = _domain("ok", _account_data(abonado), None)
        elif billing_refresh_ok is False:
            account = _domain(
                "stale",
                _account_data(abonado),
                "stale_snapshot",
            )
        else:
            account = _domain(
                "stale",
                _account_data(abonado),
                "stale_snapshot",
            )
    else:
        account = _domain("omitted")

    # --- services ---
    if "services" in include_set:
        services = _build_services(db, abonado)
    else:
        services = _domain("omitted")

    # --- billing (balance + ov) ---
    want_balance = "billing" in include_set
    want_ov = "ov" in include_set
    if want_balance or want_ov:
        billing_data: dict[str, Any] = {}
        outer_status: DomainStatus = "ok"
        outer_reason: str | None = None

        if want_balance:
            as_of: str | None = None
            if billing_refresh_ok is True:
                as_of = generated_at
                outer_status = "ok"
                outer_reason = None
            elif billing_refresh_ok is False:
                outer_status = "unavailable"
                outer_reason = "source_unavailable"
                as_of = None
            else:
                outer_status = "stale"
                outer_reason = "stale_snapshot"
                as_of = None
            billing_data["balance"] = _balance_data(
                abonado,
                as_of=as_of,
                freshness="snapshot",
            )

        if want_ov:
            from app.services.portal_ov_links import evaluar_ov_links_portal

            ov = evaluar_ov_links_portal(
                db,
                abonado=abonado,
                conversacion_id=conversacion_id,
                canal=canal,
            )
            billing_data["ov"] = ov
            if not want_balance:
                ov_st = str(ov.get("status") or "")
                if ov_st == "ready":
                    outer_status = "ok"
                elif ov_st == "partial":
                    outer_status = "partial"
                elif ov_st == "unavailable":
                    outer_status = "unavailable"
                else:
                    outer_status = "unavailable"
                outer_reason = ov.get("reason_code")
                if outer_reason is not None:
                    outer_reason = str(outer_reason)

        # MVP 2.1: metadata de capacidades (no inventa invoices/payments)
        from app.services.eko_context import billing_capabilities_hint

        ov_nav = True
        if want_ov and isinstance(billing_data.get("ov"), dict):
            ov_nav = str(billing_data["ov"].get("status") or "") in ("ready", "partial")
        billing_data["capabilities_hint"] = billing_capabilities_hint(ov_available=ov_nav)

        billing = _domain(outer_status, billing_data, outer_reason)
    else:
        billing = _domain("omitted")

    # --- tickets ---
    if "tickets" in include_set:
        if ticket_out_fn is None or tickets_visibles_fn is None:
            tickets = _domain("unavailable", {"items": []}, "source_unavailable")
        else:
            tickets = _build_tickets(
                db,
                org_id,
                abonado,
                ticket_out_fn=ticket_out_fn,
                tickets_visibles_fn=tickets_visibles_fn,
            )
    else:
        tickets = _domain("omitted")

    # --- connectivity ---
    if connectivity == "omit":
        conn = _domain("omitted")
    elif connectivity == "summary":
        conn = _build_connectivity_summary(db, abonado)
    else:
        from app.services.portal_connectivity import evaluar_conectividad_portal

        sid = (service_id or "").strip() or None
        if sid and not _service_id_in_catalog(db, abonado, sid):
            raise ValueError("service_id no pertenece al catálogo del abonado")
        raw = evaluar_conectividad_portal(
            db,
            org_id=org_id,
            abonado=abonado,
            service_id=sid,
            request_id=conversacion_id[:36] if conversacion_id else "",
        )
        payload = _connectivity_probe_payload(raw)
        st = str(payload.get("status") or "unknown")
        if st == "unknown" and payload.get("needs_service_selection"):
            conn = _domain("partial", payload, payload.get("reason_code"))
        else:
            conn = _domain("ok", payload, payload.get("reason_code"))

    return {
        "customer": customer,
        "account": account,
        "services": services,
        "billing": billing,
        "connectivity": conn,
        "tickets": tickets,
        "meta": {
            "generated_at": generated_at,
            "include": list(include),
            "refresh_applied": refresh_applied,
        },
    }
