"""Motor de inteligencia operativa por ticket — priorización, causa y acción."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from app.estate.models import Ticket
from app.estate.sla_engine import compute_sla

_CAUSA_REGLAS: list[tuple[tuple[str, ...], str]] = [
    (("roaming", "internacional", "brasil", "uruguay"), "Roaming / registro en red visitada"),
    (("esim", "e-sim", "qr", "eid"), "Activación o perfil eSIM"),
    (("apn", "datos", "internet", "sin navegación", "4g", "lte"), "Configuración APN / datos móviles"),
    (("fibra", "ftth", "ont", "olt", "potencia"), "Acceso fijo / fibra FTTH"),
    (("señal", "cobertura", "celda", "sin servicio"), "Cobertura / calidad de señal"),
    (("factura", "deuda", "suspend", "saldo", "corte"), "Estado de cuenta / facturación"),
    (("sim", "chip", "iccid"), "SIM física / identificación de línea"),
    (("proveedor", "escala", "core", "pgw"), "Escalamiento a proveedor / core"),
]

_ACCION_N1: dict[str, str] = {
    "Roaming": "Validar registro en red, reinicio de equipo y modo de red. Revisar perfil roaming en JSC.",
    "APN": "Confirmar APN, reiniciar datos móviles y probar conectividad con ping.",
    "eSIM": "Verificar EID, reenvío de QR OTA y estado del perfil activo.",
    "Fibra": "Revisar potencia ONT, estado OLT y reinicio remoto del equipo.",
    "General": "Ejecutar guía N1 de la KB, documentar acciones y confirmar resolución con el operador.",
}

_CATEGORIAS_CRITICAS = {"Roaming", "Fibra", "APN", "eSIM", "Red", "Core"}


def _as_aware(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.now(UTC)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _horas_abierto(t: Ticket, now: datetime | None = None) -> float:
    now = now or datetime.now(UTC)
    return max((_as_aware(now) - _as_aware(t.created_at)).total_seconds() / 3600, 0)


def _recurrence_count(t: Ticket, pool: list[Ticket]) -> int:
    if not t.linea:
        return 0
    digits = re.sub(r"\D", "", t.linea)
    if not digits:
        return 0
    count = 0
    for other in pool:
        if other.id == t.id:
            continue
        if digits in re.sub(r"\D", "", other.linea or ""):
            if (other.categoria or "General") == (t.categoria or "General"):
                count += 1
    return count


def inferir_causa_probable(t: Ticket) -> str:
    blob = f"{t.categoria or ''} {t.descripcion_falla or ''} {t.intent_ejecutado or ''}".lower()
    for keywords, causa in _CAUSA_REGLAS:
        if any(k in blob for k in keywords):
            return causa
    cat = t.categoria or "General"
    if cat in _CATEGORIAS_CRITICAS:
        return f"Incidente de {cat.lower()} — revisar procedimiento operativo"
    if t.nivel == "N2":
        return "Escalamiento técnico — requiere intervención NOC"
    if t.proveedor:
        return f"Incidente de infraestructura — proveedor {t.proveedor}"
    return "Reclamo operativo — triage inicial pendiente de confirmación"


def proxima_mejor_accion(t: Ticket) -> str:
    if t.estado == "Cerrado":
        return "Ticket cerrado. Revisar si aplica actualizar KB o postmortem."
    cat = t.categoria or "General"
    if t.nivel == "N2" and t.proveedor:
        return f"Coordinar con {t.proveedor}: adjuntar evidencia, SLA y referencia externa."
    if t.nivel == "N2":
        return "Asignar ingeniero NOC, revisar telemetría correlacionada y definir plan de acción."
    if t.estado_sla in ("Vencido", "Crítico", "Vencida"):
        return "Prioridad SLA: contactar operador, actualizar estado y escalar si no hay avance en 30 min."
    sla_info = compute_sla(t, now=datetime.now(UTC))
    if sla_info["estado_sla"] in ("Vencido", "Crítico"):
        return "Prioridad SLA: contactar operador, actualizar estado y escalar si no hay avance en 30 min."
    if cat in _ACCION_N1:
        return _ACCION_N1[cat]
    if t.destino == "proveedor":
        return "Preparar escalamiento: motivo técnico, línea, síntoma y acciones N1 ya realizadas."
    return _ACCION_N1["General"]


def calcular_prioridad(
    t: Ticket,
    *,
    pool: list[Ticket] | None = None,
    org_name: str = "",
) -> dict:
    now = datetime.now(UTC)
    pool = pool or []
    reasons: list[str] = []
    score = 0.0

    if t.estado == "Cerrado":
        return {
            "priority_score": 0,
            "risk_level": "cerrado",
            "risk_reasons": ["Ticket cerrado"],
            "probable_cause": inferir_causa_probable(t),
            "next_best_action": proxima_mejor_accion(t),
            "horas_abierto": round(_horas_abierto(t, now), 1),
            "recurrence_count": _recurrence_count(t, pool),
            "organizacion": org_name,
            "sla": compute_sla(t, now=now),
        }

    score += 15
    if t.nivel == "N2":
        score += 28
        reasons.append("Escalado a N2")
    if t.proveedor:
        score += 18
        reasons.append(f"Involucra proveedor ({t.proveedor})")
    sla_info = compute_sla(t, now=now)
    t.estado_sla = sla_info["estado_sla"]
    estado_sla = sla_info["estado_sla"].lower()
    if estado_sla == "vencido":
        score += 28
        reasons.append(sla_info["label"])
    elif estado_sla == "crítico" or estado_sla == "critico":
        score += 22
        reasons.append(sla_info["label"])
    elif estado_sla == "en riesgo":
        score += 14
        reasons.append(sla_info["label"])
    elif sla_info.get("horas_restantes", 99) <= 8:
        score += 8
        reasons.append(sla_info["label"])
    horas = _horas_abierto(t, now)
    if horas >= 4:
        ant_score = min(horas * 1.8, 35)
        score += ant_score
        reasons.append(f"Abierto {round(horas, 1)} hs")
    rec = _recurrence_count(t, pool)
    if rec >= 1:
        score += min(rec * 12, 24)
        reasons.append(f"Recurrencia x{rec + 1} misma línea/categoría")
    cat = t.categoria or "General"
    if cat in _CATEGORIAS_CRITICAS:
        score += 10
        reasons.append(f"Categoría crítica: {cat}")
    if t.destino == "proveedor":
        score += 8
        reasons.append("Destino proveedor")

    score = min(round(score), 100)
    if score >= 75:
        risk = "critico"
    elif score >= 55:
        risk = "alto"
    elif score >= 35:
        risk = "medio"
    else:
        risk = "bajo"

    if not reasons:
        reasons.append("Prioridad operativa estándar")

    return {
        "priority_score": score,
        "risk_level": risk,
        "risk_reasons": reasons,
        "probable_cause": inferir_causa_probable(t),
        "next_best_action": proxima_mejor_accion(t),
        "horas_abierto": round(horas, 1),
        "recurrence_count": rec,
        "organizacion": org_name,
        "sla": sla_info,
    }


def enriquecer_ticket(t: Ticket, *, pool: list[Ticket] | None = None, org_name: str = "") -> dict:
    intel = calcular_prioridad(t, pool=pool, org_name=org_name)
    return intel


def ordenar_por_riesgo(tickets: list[Ticket], pool: list[Ticket] | None = None) -> list[tuple[Ticket, dict]]:
    pool = pool or tickets
    scored = [(t, calcular_prioridad(t, pool=pool)) for t in tickets if t.estado != "Cerrado"]
    scored.sort(key=lambda x: (-x[1]["priority_score"], -x[1]["horas_abierto"]))
    return scored


def explicar_escalamiento(t: Ticket, org_name: str = "") -> str:
    intel = calcular_prioridad(t)
    partes = [
        f"Escalamiento técnico — Ticket {t.id}",
        f"Cooperativa: {org_name or 'N/A'}",
        f"Línea: {t.linea or 'sin línea'} · Categoría: {t.categoria or 'General'}",
        f"Nivel: {t.nivel or 'N1'} → Destino: {t.destino or 'cooperativa'}",
        f"Causa probable: {intel['probable_cause']}",
        f"Síntoma: {(t.descripcion_falla or '')[:200]}",
    ]
    if t.acciones_n1_realizadas:
        partes.append(f"Acciones N1: {t.acciones_n1_realizadas[:180]}")
    if t.evidencia:
        partes.append(f"Evidencia: {t.evidencia[:180]}")
    if t.proveedor:
        partes.append(f"Proveedor sugerido: {t.proveedor}")
    partes.append(f"Recomendación NOC: {intel['next_best_action']}")
    return "\n".join(partes)
