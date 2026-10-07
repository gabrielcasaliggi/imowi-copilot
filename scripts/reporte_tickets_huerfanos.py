#!/usr/bin/env python3
"""Reporte de SOLO LECTURA: tickets abiertos creados por Eko sin conversación ligada (H26).

Un ticket «huérfano» está abierto (estado distinto de «Cerrado»), nació en un canal de Eko (origen Portal / App / Canal /
WhatsApp) y ninguna conversación de canal lo tiene en ``ticket_id``. El abonado sigue esperando, pero la consola solo muestra
«Sin conversación de canal» y nadie avisa al operador. Segunda sección (informativa): conversaciones en ``espera_agente`` /
``con_agente`` sin ``ticket_id`` (cola de visitantes anónimos o hilo desligado).

Solo SELECT: la sesión se abre en modo de solo lectura (``SET TRANSACTION READ ONLY`` en PostgreSQL, ``PRAGMA query_only`` en
SQLite), con ``statement_timeout`` y sin ``commit``. Sin datos personales: los teléfonos salen enmascarados (``***123``).

Uso (ver docs/REPORTE-TICKETS-HUERFANOS.md)::

    .venv/bin/python scripts/reporte_tickets_huerfanos.py [--org coop-batan] [--timeout 15] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import exists, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

ORIGENES_EKO = ("Portal", "App", "Canal", "WhatsApp")
ESTADOS_CONV_ACTIVOS = ("espera_agente", "con_agente")


def enmascarar(valor: str) -> str:
    """Deja solo los últimos 3 dígitos (``***123``); vacío si no hay dígitos."""
    digitos = "".join(c for c in (valor or "") if c.isdigit())
    return f"***{digitos[-3:]}" if digitos else ""


def _antiguedad(desde: datetime | None, ahora: datetime) -> str:
    if desde is None:
        return ""
    if desde.tzinfo is None:
        desde = desde.replace(tzinfo=UTC)
    seg = max(int((ahora - desde).total_seconds()), 0)
    d, resto = divmod(seg, 86400)
    h, resto = divmod(resto, 3600)
    return f"{d}d {h}h {resto // 60}m" if d else f"{h}h {resto // 60}m"


def preparar_solo_lectura(db: Session, timeout_s: int) -> None:
    """Sesión de solo lectura con tope de tiempo. Debe llamarse antes de la primera consulta."""
    dialecto = db.get_bind().dialect.name
    if dialecto == "postgresql":
        db.execute(text("SET TRANSACTION READ ONLY"))
        db.execute(text(f"SET LOCAL statement_timeout = {int(timeout_s) * 1000}"))
    elif dialecto == "sqlite":
        db.execute(text("PRAGMA query_only = ON"))


def generar_reporte(db: Session, *, org_slug: str = "", ahora: datetime | None = None) -> dict:
    from app.estate.models import ConversacionCanal, Organization, Ticket

    ahora = ahora or datetime.now(UTC)
    ligado = exists().where(ConversacionCanal.ticket_id == Ticket.id)
    q = select(Ticket).where(Ticket.estado != "Cerrado", Ticket.origen.in_(ORIGENES_EKO), ~ligado)
    qc = select(ConversacionCanal).where(
        ConversacionCanal.estado.in_(ESTADOS_CONV_ACTIVOS), ConversacionCanal.ticket_id == ""
    )
    if org_slug:
        org_id = db.scalar(select(Organization.id).where(Organization.slug == org_slug))
        if not org_id:
            raise SystemExit(f"Organización desconocida: {org_slug!r}")
        q = q.where(Ticket.organizacion_id == org_id)
        qc = qc.where(ConversacionCanal.organizacion_id == org_id)

    tickets = [
        {
            "id": t.id,
            "creado": t.created_at.isoformat() if t.created_at else "",
            "nivel": t.nivel,
            "destino": t.destino,
            "estado": t.estado,
            "origen": t.origen,
            "linea": enmascarar(t.linea),
            "antiguedad": _antiguedad(t.created_at, ahora),
        }
        for t in db.scalars(q.order_by(Ticket.created_at)).all()
    ]
    convs = [
        {
            "conversacion": c.id,
            "canal": c.canal,
            "estado": c.estado,
            "telefono": enmascarar(c.telefono),
            "creada": c.created_at.isoformat() if c.created_at else "",
            "antiguedad": _antiguedad(c.created_at, ahora),
        }
        for c in db.scalars(qc.order_by(ConversacionCanal.created_at)).all()
    ]
    return {"generado": ahora.isoformat(), "tickets_sin_conversacion": tickets, "conversaciones_activas_sin_ticket": convs}


def formatear(rep: dict) -> str:
    out = [f"Reporte de huérfanos — {rep['generado']}", ""]
    t = rep["tickets_sin_conversacion"]
    out.append(f"1) Tickets abiertos de Eko sin conversación ligada: {len(t)}")
    for x in t:
        out.append(
            f"  {x['id']:<14} creado={x['creado'][:19]} nivel={x['nivel']} destino={x['destino']} estado={x['estado']} "
            f"origen={x['origen']} linea={x['linea'] or '-'} antigüedad={x['antiguedad']}"
        )
    c = rep["conversaciones_activas_sin_ticket"]
    out += ["", f"2) Conversaciones en espera_agente/con_agente sin ticket (informativo): {len(c)}"]
    for x in c:
        out.append(
            f"  {x['conversacion']} canal={x['canal']} estado={x['estado']} tel={x['telefono'] or '-'} "
            f"creada={x['creada'][:19]} antigüedad={x['antiguedad']}"
        )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--org", default="", help="slug de la organización (por defecto, todas)")
    ap.add_argument("--timeout", type=int, default=15, help="tope en segundos por consulta (PostgreSQL)")
    ap.add_argument("--json", action="store_true", help="salida JSON")
    args = ap.parse_args(argv)

    from app.estate.database import get_session_factory

    with get_session_factory()() as db:
        preparar_solo_lectura(db, args.timeout)
        rep = generar_reporte(db, org_slug=args.org)
        db.rollback()  # nunca commit: la transacción es de solo lectura
    print(json.dumps(rep, ensure_ascii=False, indent=2) if args.json else formatear(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
