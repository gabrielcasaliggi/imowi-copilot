"""Aprendizaje operativo — KB, similares y postmortem al cerrar tickets."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.estate import repository as repo
from app.estate.models import Ticket
from app.estate.ticket_intelligence import inferir_causa_probable


def sugerir_kb(db: Session, org_id: str, ticket: Ticket, *, limit: int = 3) -> list[dict]:
    articulos = repo.list_kb(db, org_id)
    cat = (ticket.categoria or "").lower()
    blob = f"{ticket.descripcion_falla or ''} {ticket.categoria or ''}".lower()
    scored: list[tuple[int, dict]] = []
    for a in articulos:
        score = 0
        if cat and cat in (a.categoria or "").lower():
            score += 5
        if cat and cat in (a.titulo or "").lower():
            score += 3
        tokens = [w for w in blob.split() if len(w) > 4][:8]
        texto = f"{a.titulo} {a.contenido}".lower()
        score += sum(1 for tok in tokens if tok in texto)
        if score > 0:
            scored.append((score, {
                "id": a.id,
                "titulo": a.titulo,
                "categoria": a.categoria,
                "fragmento": (a.contenido or "")[:160],
            }))
    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored[:limit]]


def similares_con_resolucion(
    db: Session,
    org_id: str,
    ticket: Ticket,
    *,
    limit: int = 5,
) -> list[dict]:
    base = repo.buscar_tickets_similares(
        db,
        org_id,
        ticket.linea or "",
        ticket.descripcion_falla or "",
        limit=limit + 3,
    )
    out = []
    for s in base:
        if s.get("id") == ticket.id:
            continue
        t = repo.get_ticket(db, org_id, s["id"], admin_global=True)
        item = dict(s)
        if t and t.estado == "Cerrado" and t.resolucion_tecnica:
            item["resolucion_tecnica"] = t.resolucion_tecnica[:200]
            item["cerrado"] = True
        out.append(item)
        if len(out) >= limit:
            break
    return out


def generar_postmortem(ticket: Ticket, org_name: str = "") -> str:
    causa = inferir_causa_probable(ticket)
    res = (ticket.resolucion_tecnica or "Sin resolución documentada.").strip()
    return (
        f"Postmortem {ticket.id} — {org_name or 'Cooperativa'}\n"
        f"Categoría: {ticket.categoria or 'General'} · Nivel: {ticket.nivel or 'N1'}\n"
        f"Causa probable: {causa}\n"
        f"Síntoma: {(ticket.descripcion_falla or '')[:180]}\n"
        f"Resolución: {res[:220]}\n"
        f"Lección: documentar en KB si el caso es recurrente en {ticket.categoria or 'esta categoría'}."
    )


def procesar_cierre_ticket(
    db: Session,
    org_id: str,
    ticket: Ticket,
    *,
    org_name: str = "",
) -> dict:
    kb = sugerir_kb(db, org_id, ticket)
    similares = similares_con_resolucion(db, org_id, ticket)
    postmortem = generar_postmortem(ticket, org_name)

    repo.add_ticket_event(
        db,
        org_id,
        ticket.id,
        tipo="aprendizaje",
        titulo="Aprendizaje operativo al cierre",
        detalle=postmortem[:500],
        nivel=ticket.nivel,
        estado=ticket.estado,
        actor="sistema-ia",
    )

    if kb:
        titulos = ", ".join(k["titulo"] for k in kb[:2])
        repo.add_ticket_notification(
            db,
            org_id,
            ticket.id,
            destinatario=ticket.creado_por,
            titulo="Sugerencia KB post-cierre",
            mensaje=f"Artículos recomendados para este tipo de caso: {titulos}.",
        )

    return {
        "kb_sugerencias": kb,
        "similares_resueltos": [s for s in similares if s.get("cerrado")],
        "postmortem": postmortem,
    }
