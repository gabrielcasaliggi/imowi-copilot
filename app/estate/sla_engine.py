"""Motor SLA operativo — plazos por nivel y categoría."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.estate.models import Ticket

_POLICIES: dict[str, int] = {
    "n1_standard": 24,
    "n2_standard": 8,
    "critico_proveedor": 4,
    "critico_categoria": 4,
}


def resolve_policy(t: Ticket) -> tuple[str, int]:
    if t.proveedor or (t.destino or "") == "proveedor":
        return "critico_proveedor", _POLICIES["critico_proveedor"]
    if (t.nivel or "N1") == "N2":
        return "n2_standard", _POLICIES["n2_standard"]
    cat = (t.categoria or "").lower()
    if cat in ("fibra", "core", "red", "roaming"):
        return "critico_categoria", _POLICIES["critico_categoria"]
    return "n1_standard", _POLICIES["n1_standard"]


def compute_sla(t: Ticket, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    if t.estado == "Cerrado":
        return {
            "sla_policy": t.sla_policy or "",
            "sla_due_at": t.sla_due_at.isoformat() if t.sla_due_at else None,
            "sla_breached_at": t.sla_breached_at.isoformat() if t.sla_breached_at else None,
            "estado_sla": "Cumplido" if not t.sla_breached_at else "Incumplido",
            "horas_restantes": 0,
            "vencido": False,
            "label": "Cerrado",
        }

    policy_name, hours = resolve_policy(t)
    created = t.created_at
    if created and created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    due = t.sla_due_at
    if not due and created:
        due = created + timedelta(hours=hours)
    if due and due.tzinfo is None:
        due = due.replace(tzinfo=UTC)

    vencido = bool(due and now > due)
    horas_restantes = round((due - now).total_seconds() / 3600, 1) if due else hours

    if vencido:
        estado = "Vencido"
        label = f"Vencido hace {abs(horas_restantes):.1f} hs"
    elif horas_restantes <= 2:
        estado = "Crítico"
        label = f"Vence en {horas_restantes:.1f} hs"
    elif horas_restantes <= 4:
        estado = "En riesgo"
        label = f"Vence en {horas_restantes:.1f} hs"
    else:
        estado = "En plazo"
        label = f"Vence en {horas_restantes:.1f} hs"

    return {
        "sla_policy": policy_name,
        "sla_due_at": due.isoformat() if due else None,
        "sla_breached_at": (due.isoformat() if vencido and due else None),
        "estado_sla": estado,
        "horas_restantes": horas_restantes,
        "vencido": vencido,
        "label": label,
    }


def apply_sla_to_ticket(t: Ticket, *, now: datetime | None = None) -> Ticket:
    now = now or datetime.now(UTC)
    if t.estado == "Cerrado":
        return t
    policy_name, hours = resolve_policy(t)
    created = t.created_at
    if created and created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    if not t.sla_due_at and created:
        t.sla_due_at = created + timedelta(hours=hours)
    t.sla_policy = policy_name
    due = t.sla_due_at
    if due and due.tzinfo is None:
        due = due.replace(tzinfo=UTC)
    if due and now > due and not t.sla_breached_at:
        t.sla_breached_at = due
    sla = compute_sla(t, now=now)
    t.estado_sla = sla["estado_sla"]
    return t
