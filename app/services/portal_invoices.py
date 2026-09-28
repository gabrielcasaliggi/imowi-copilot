"""Portal: cabeceras FC del abonado ya identificado (EKO 2.8).

La identidad llega resuelta desde el JWT. Este módulo no acepta
selectores de cuenta ni abre otra conexión a BillTrack: delega en
``read_invoices_fc`` y recorta el DTO público.
"""

from __future__ import annotations

from typing import Any

from app.services.eko_invoice_reader import (
    InvoiceHeader,
    _clamp_limit,
    read_invoices_fc,
)

_PUBLIC_FIELDS = ("invoice_number", "full_type", "amount", "issued_at", "status")


def bounded_invoice_limit(raw: str | None) -> int:
    """Misma pinza que el reader (default 5, tope 20). Query inválido → default."""
    if raw is None:
        return _clamp_limit(None)
    text = str(raw).strip()
    if not text:
        return _clamp_limit(None)
    try:
        return _clamp_limit(int(text))
    except (TypeError, ValueError):
        return _clamp_limit(None)


def public_invoice_header(inv: InvoiceHeader) -> dict[str, Any]:
    """Solo los cinco campos del contrato. No usa ``to_dict`` (trae id y cuenta)."""
    issued = inv.issued_at.isoformat() if inv.issued_at is not None else None
    row = {
        "invoice_number": inv.invoice_number,
        "full_type": inv.full_type,
        "amount": inv.amount,
        "issued_at": issued,
        "status": inv.status,
    }
    return {key: row[key] for key in _PUBLIC_FIELDS}


def evaluar_facturas_portal(
    *,
    client_number: str,
    db: Any,
    limit: str | None,
) -> dict[str, Any]:
    """Lee cabeceras FC. Sin ``client_number`` no llama al reader."""
    cn = str(client_number or "").strip()
    if not cn:
        return {
            "status": "unavailable",
            "reason_code": "missing_client_number",
            "invoices": [],
        }

    result = read_invoices_fc(
        client_number=cn,
        db=db,
        limit=bounded_invoice_limit(limit),
    )
    if result.status == "ok":
        return {
            "status": "ok",
            "reason_code": None,
            "invoices": [public_invoice_header(inv) for inv in result.invoices],
        }
    if result.status == "empty":
        return {
            "status": "empty",
            "reason_code": result.reason_code or "no_fc_invoices",
            "invoices": [],
        }
    status = "error" if result.status == "error" else "unavailable"
    return {
        "status": status,
        "reason_code": result.reason_code,
        "invoices": [],
    }
