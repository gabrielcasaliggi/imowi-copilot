"""BillTrack invoice header reader — solo cabecera FC (Eko 2.0).

READ-ONLY. Ownership: client_number → api_invoice.account_number.
No líneas, no due_date, no period, no currency inventada, no PDF.
No usa SUM(api_billed_concept). amount = api_invoice.amount.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

logger = logging.getLogger("operations_hub")

InvoiceReadStatus = Literal[
    "ok",
    "empty",
    "invalid_input",
    "unavailable",
    "error",
]

DEFAULT_LIMIT = 5
MAX_LIMIT = 20

_INVOICE_SQL = """
SELECT
  id,
  number,
  full_type,
  type,
  account_number,
  amount,
  date,
  state
FROM public.api_invoice
WHERE account_number = :client_number
  AND type = 'FC'
ORDER BY date DESC, id DESC
LIMIT :limit
""".strip()


@dataclass(frozen=True)
class InvoiceHeader:
    """Cabecera de factura FC. Sin currency/period/due_date/line_items."""

    invoice_id: int
    invoice_number: str
    full_type: str
    type: str
    client_number: str
    account_number: str
    amount: str
    issued_at: datetime | None
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "invoice_id": self.invoice_id,
            "invoice_number": self.invoice_number,
            "full_type": self.full_type,
            "type": self.type,
            "client_number": self.client_number,
            "account_number": self.account_number,
            "amount": self.amount,
            "issued_at": self.issued_at.isoformat() if self.issued_at else None,
            "status": self.status,
            # Explícito: no hay moneda en BillTrack para api_invoice
            "currency": None,
            "period": None,
            "due_date": None,
        }


@dataclass
class InvoiceReadResult:
    status: InvoiceReadStatus
    invoices: list[InvoiceHeader] = field(default_factory=list)
    reason_code: str | None = None
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _clamp_limit(limit: int | None) -> int:
    try:
        n = int(limit if limit is not None else DEFAULT_LIMIT)
    except (TypeError, ValueError):
        n = DEFAULT_LIMIT
    if n < 1:
        n = 1
    if n > MAX_LIMIT:
        n = MAX_LIMIT
    return n


def _amount_str(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, Decimal):
        return format(raw, "f")
    try:
        return format(Decimal(str(raw)), "f")
    except (InvalidOperation, ValueError, TypeError):
        return None


def _as_datetime(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    return None


def _normalize_row(row: dict[str, Any], *, client_number: str) -> InvoiceHeader | None:
    """Normaliza una fila. None si faltan campos obligatorios (no fabricar)."""
    try:
        invoice_id = int(row["id"])
    except (KeyError, TypeError, ValueError):
        return None
    number = str(row.get("number") or "").strip()
    typ = str(row.get("type") or "").strip()
    account = str(row.get("account_number") or "").strip()
    amount = _amount_str(row.get("amount"))
    state = str(row.get("state") or "").strip()
    if not number or typ != "FC" or not account or amount is None or not state:
        return None
    if account != client_number:
        # Defensa en profundidad: nunca devolver fila de otra cuenta
        return None
    full_type = str(row.get("full_type") or "").strip()
    return InvoiceHeader(
        invoice_id=invoice_id,
        invoice_number=number,
        full_type=full_type,
        type=typ,
        client_number=client_number,
        account_number=account,
        amount=amount,
        issued_at=_as_datetime(row.get("date")),
        status=state,
    )


def read_invoices_fc(
    *,
    client_number: str,
    db: Any | None = None,
    limit: int | None = DEFAULT_LIMIT,
) -> InvoiceReadResult:
    """Lee cabeceras FC de BillTrack para un client_number ya resuelto.

    No acepta DNI. No selecciona cuenta. No consulta billed_concept.
    """
    cn = str(client_number or "").strip()
    if not cn:
        return InvoiceReadResult(
            status="invalid_input",
            reason_code="missing_client_number",
            message="Ownership no resuelto: falta client_number.",
        )

    lim = _clamp_limit(limit)

    from app.services.billtrack import _billtrack_engine

    engine, _params, prod = _billtrack_engine(db)
    if engine is None:
        return InvoiceReadResult(
            status="unavailable",
            reason_code="billtrack_unavailable",
            message="No puedo consultar facturas en este momento.",
        )

    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            rows = (
                conn.execute(
                    text(_INVOICE_SQL),
                    {"client_number": cn, "limit": lim},
                )
                .mappings()
                .all()
            )
    except Exception:
        logger.exception("invoice_reader: BillTrack query falló")
        return InvoiceReadResult(
            status="error",
            reason_code="billtrack_query_failed",
            message="No pude consultar las facturas por un error técnico.",
        )
    finally:
        engine.dispose()

    invoices: list[InvoiceHeader] = []
    for raw in rows:
        inv = _normalize_row(dict(raw), client_number=cn)
        if inv is not None:
            invoices.append(inv)

    if not invoices:
        return InvoiceReadResult(
            status="empty",
            reason_code="no_fc_invoices",
            message="No encuentro facturas (FC) para tu cuenta en este momento.",
        )

    return InvoiceReadResult(status="ok", invoices=invoices, reason_code=None)


def format_invoice_headers_message(invoices: list[InvoiceHeader]) -> str:
    """Texto determinístico para el abonado (sin LLM)."""
    from app.services.eco_voice import texto_monto_ars

    if not invoices:
        return "No encuentro facturas (FC) para tu cuenta en este momento."

    blocks: list[str] = []
    for inv in invoices:
        issued = ""
        if inv.issued_at is not None:
            try:
                issued = inv.issued_at.strftime("%d/%m/%Y")
            except Exception:
                issued = inv.issued_at.isoformat()
        lines = [
            f"Factura {inv.invoice_number}"
            + (f" ({inv.full_type})" if inv.full_type else ""),
            f"Importe: {texto_monto_ars(inv.amount)}",
        ]
        if issued:
            lines.append(f"Emitida: {issued}")
        lines.append(f"Estado: {inv.status}")
        blocks.append("\n".join(lines))

    header = (
        "Estas son tus facturas más recientes:"
        if len(invoices) > 1
        else "Esta es tu factura más reciente:"
    )
    return header + "\n\n" + "\n\n".join(blocks)
