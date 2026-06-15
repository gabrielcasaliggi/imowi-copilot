"""Analytics ejecutivo — ranking de riesgo, tendencias y resumen para dirección."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.estate import repository as repo
from app.estate.ticket_intelligence import calcular_prioridad


def _as_aware(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.now(UTC)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def evolucion_semanal(tickets: list, semanas: int = 8) -> list[dict]:
    now = datetime.now(UTC)
    out = []
    for i in range(semanas - 1, -1, -1):
        fin = now - timedelta(days=i * 7)
        inicio = fin - timedelta(days=7)
        count = sum(
            1
            for t in tickets
            if t.created_at and inicio <= _as_aware(t.created_at) < fin
        )
        label = fin.strftime("%Y-%m-%d")[:10]
        out.append({"label": label, "count": count})
    return out


def ranking_riesgo_operativo(db: Session, tickets: list) -> list[dict]:
    orgs = {o.id: o.nombre for o in repo.list_organizations(db)}
    abiertos = [t for t in tickets if t.estado != "Cerrado"]
    by_org: dict[str, list] = {}
    for t in abiertos:
        by_org.setdefault(t.organizacion_id, []).append(t)

    ranking = []
    for org_id, grupo in by_org.items():
        scores = [calcular_prioridad(t, pool=tickets)["priority_score"] for t in grupo]
        n2 = sum(1 for t in grupo if t.nivel == "N2")
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0
        ranking.append({
            "label": orgs.get(org_id, "Sin org"),
            "org_id": org_id,
            "backlog": len(grupo),
            "n2": n2,
            "score_riesgo": avg_score,
            "score_max": max(scores) if scores else 0,
            "tickets_criticos": sum(1 for s in scores if s >= 75),
        })
    ranking.sort(key=lambda x: (-x["score_riesgo"], -x["backlog"]))
    return ranking


def ahorro_operativo_estimado(tickets: list) -> dict:
    cerrados_n1 = [t for t in tickets if t.estado == "Cerrado" and (t.nivel or "N1") == "N1"]
    n2 = sum(1 for t in tickets if t.nivel == "N2")
    total = len(tickets) or 1
    # Estimación demo: N1 resuelto ahorra ~45 min vs escalamiento; 30% N2 evitable
    horas_ahorradas = round(len(cerrados_n1) * 0.75, 1)
    escalaciones_evitadas = max(0, int(len(cerrados_n1) * 0.3))
    return {
        "casos_n1_resueltos": len(cerrados_n1),
        "escalaciones_evitadas_estimadas": escalaciones_evitadas,
        "horas_ahorradas_estimadas": horas_ahorradas,
        "porcentaje_n2": round((n2 / total) * 100, 1),
    }


def resumen_ejecutivo_nl(
    tickets: list,
    ranking: list[dict],
    ahorro: dict,
) -> str:
    total = len(tickets)
    abiertos = sum(1 for t in tickets if t.estado != "Cerrado")
    n2 = sum(1 for t in tickets if t.nivel == "N2")
    partes = [
        f"En el período analizado se registraron {total} reclamos, con {abiertos} abiertos y {n2} en N2.",
    ]
    if ranking:
        top = ranking[0]
        partes.append(
            f"La mayor presión operativa está en {top['label']}: "
            f"{top['backlog']} tickets abiertos, score de riesgo {top['score_riesgo']}/100."
        )
    if ahorro["casos_n1_resueltos"]:
        partes.append(
            f"Se resolvieron {ahorro['casos_n1_resueltos']} casos en N1, "
            f"estimando ~{ahorro['horas_ahorradas_estimadas']} hs de ahorro operativo."
        )
    criticos = sum(r.get("tickets_criticos", 0) for r in ranking)
    if criticos:
        partes.append(f"Hay {criticos} tickets en riesgo crítico que requieren acción inmediata del NOC.")
    else:
        partes.append("No hay tickets en riesgo crítico en este momento.")
    partes.append("Recomendación: priorizar backlog N2 y reforzar KB en categorías recurrentes.")
    return " ".join(partes)


def executive_analytics(db: Session, *, admin_global: bool = True, org_id: str = "") -> dict:
    tickets = repo.list_tickets_all(db) if admin_global else repo.list_tickets(db, org_id)
    ranking = ranking_riesgo_operativo(db, tickets)
    ahorro = ahorro_operativo_estimado(tickets)
    semanal = evolucion_semanal(tickets)
    resumen = resumen_ejecutivo_nl(tickets, ranking, ahorro)

    alertas = []
    for r in ranking[:3]:
        if r["score_riesgo"] >= 55:
            alertas.append({
                "tipo": "riesgo_cooperativa",
                "mensaje": f"{r['label']}: riesgo operativo elevado ({r['score_riesgo']}/100)",
                "severidad": "alta" if r["score_riesgo"] >= 75 else "media",
            })
    if len(semanal) >= 2 and semanal[-1]["count"] > semanal[-2]["count"] * 1.4:
        alertas.append({
            "tipo": "tendencia",
            "mensaje": "Incremento semanal de reclamos — posible degradación de servicio",
            "severidad": "media",
        })

    return {
        "resumen_ejecutivo": resumen,
        "ranking_riesgo": ranking,
        "evolucion_semanal": semanal,
        "ahorro_operativo": ahorro,
        "alertas": alertas,
    }
