"""Filtros de cola operativa — estilo helpdesk, criterio NOC telco."""

from __future__ import annotations

from app.estate.models import Ticket
from app.estate.sla_engine import compute_sla


def _match_q(t: Ticket, q: str) -> bool:
    blob = " ".join(
        filter(
            None,
            [
                t.id,
                t.linea,
                t.descripcion_falla,
                t.categoria,
                t.creado_por,
                t.proveedor,
                t.organizacion.nombre if getattr(t, "organizacion", None) else "",
            ],
        )
    ).lower()
    return q in blob


def filtrar_tickets(
    tickets: list[Ticket],
    *,
    estado: str = "",
    nivel: str = "",
    sla: str = "",
    categoria: str = "",
    q: str = "",
    solo_abiertos: bool = False,
) -> list[Ticket]:
    out = list(tickets)
    if solo_abiertos:
        out = [t for t in out if t.estado != "Cerrado"]
    if estado:
        out = [t for t in out if (t.estado or "").lower() == estado.lower()]
    if nivel:
        out = [t for t in out if (t.nivel or "N1").lower() == nivel.lower()]
    if categoria:
        cat = categoria.lower()
        out = [t for t in out if cat in (t.categoria or "").lower()]
    if sla:
        sla_l = sla.lower()
        filtrados = []
        for t in out:
            estado_sla = (compute_sla(t).get("estado_sla") or "").lower()
            if sla_l in estado_sla or (sla_l == "vencido" and compute_sla(t).get("vencido")):
                filtrados.append(t)
        out = filtrados
    if q:
        qn = q.strip().lower()
        if qn:
            out = [t for t in out if _match_q(t, qn)]
    return out
