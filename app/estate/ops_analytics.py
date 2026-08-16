"""Agregados operativos: canal (bandeja) + tickets + agentes, con ventana de fechas."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.estate.models import ConversacionCanal, MensajeCanal, Organization, Ticket, User


def _now() -> datetime:
    return datetime.now(UTC)


def _ensure_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _in_range(dt: datetime | None, desde: datetime | None, hasta: datetime | None) -> bool:
    d = _ensure_aware(dt)
    if not d:
        return False
    if desde and d < desde:
        return False
    if hasta and d > hasta:
        return False
    return True


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 1)
    k = (len(ordered) - 1) * p
    f = int(k)
    c = min(f + 1, len(ordered) - 1)
    if f == c:
        return round(ordered[f], 1)
    return round(ordered[f] + (ordered[c] - ordered[f]) * (k - f), 1)


def _parse_contexto(raw: str | None) -> dict:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _canal_display(canal: str) -> str:
    from app.domain.canales import canal_display

    return canal_display(canal)


def _match_agent(haystack: str, keys: set[str]) -> bool:
    v = (haystack or "").strip().lower()
    return bool(v) and v in keys


def agent_keys(email: str, nombre: str = "") -> set[str]:
    s: set[str] = set()
    e = (email or "").strip().lower()
    if e:
        s.add(e)
        if "@" in e:
            s.add(e.split("@", 1)[0])
    n = (nombre or "").strip().lower()
    if n:
        s.add(n)
    return s


def build_ops_analytics(
    db: Session,
    org_id: str,
    *,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    agent_filter: str | None = None,
    admin_global: bool = False,
) -> dict[str, Any]:
    """Agregados ops. Si agent_filter (email), reduce sección agentes/`me` a ese usuario.

    Con admin_global=True (plataforma imowi) agrega canal/tickets/agentes de todas las orgs,
    igual que /analytics/tickets.
    """
    now = _now()
    if not hasta:
        hasta = now
    if not desde:
        desde = hasta - timedelta(days=7)

    conv_q = select(ConversacionCanal)
    ticket_q = select(Ticket)
    user_q = select(User)
    msg_q = select(MensajeCanal).where(
        MensajeCanal.created_at >= desde,
        MensajeCanal.created_at <= hasta,
    )
    if not admin_global:
        conv_q = conv_q.where(ConversacionCanal.organizacion_id == org_id)
        ticket_q = ticket_q.where(Ticket.organizacion_id == org_id)
        user_q = user_q.where(User.organizacion_id == org_id)
        msg_q = msg_q.where(MensajeCanal.organizacion_id == org_id)

    convs = list(db.scalars(conv_q).all())
    tickets = list(db.scalars(ticket_q).all())
    users = [
        u
        for u in db.scalars(user_q).all()
        if (u.rol or "").lower() in ("agente", "supervisor") and (u.activo or "Sí") != "No"
    ]
    org_names: dict[str, str] = {}
    if admin_global:
        org_names = {
            o.id: (o.nombre or o.slug or "")
            for o in db.scalars(select(Organization)).all()
        }

    # ---- Canal snapshot ----
    abiertas = [c for c in convs if c.estado != "cerrado"]
    por_estado: dict[str, int] = {"bot": 0, "espera_agente": 0, "con_agente": 0}
    for c in abiertas:
        if c.estado in por_estado:
            por_estado[c.estado] += 1

    espera = [c for c in abiertas if c.estado == "espera_agente"]
    espera_mins: list[float] = []
    for c in espera:
        u = _ensure_aware(c.updated_at)
        if u:
            espera_mins.append(max(0.0, (now - u).total_seconds() / 60.0))

    por_canal: dict[str, int] = {}
    for c in abiertas:
        label = _canal_display(c.canal)
        por_canal[label] = por_canal.get(label, 0) + 1

    # Mensajes en rango (para claims / cierres / first response)
    msgs = list(db.scalars(msg_q.order_by(MensajeCanal.created_at.asc())).all())

    claims = 0
    cierres = 0
    cierres_con_nota = 0
    claims_by_agent: dict[str, int] = {}
    cierres_by_agent: dict[str, int] = {}

    def _resolve_agent_key(texto: str, conv: ConversacionCanal | None, *, cierre: bool = False) -> str:
        low = texto.lower()
        for u in users:
            nombre = (u.nombre or "").strip()
            if nombre and nombre.lower() in low:
                return (u.email or "").lower()
        if conv:
            cctx = _parse_contexto(conv.contexto_json)
            if cierre and cctx.get("cierre_por"):
                return str(cctx["cierre_por"]).lower()
            if conv.agente_id:
                return conv.agente_id.lower()
        return "sin_asignar"

    for m in msgs:
        texto = m.texto or ""
        low = texto.lower()
        conv = next((c for c in convs if c.id == m.conversacion_id), None)
        if m.autor == "agente" and "tomó el caso" in low:
            claims += 1
            key = _resolve_agent_key(texto, conv)
            claims_by_agent[key] = claims_by_agent.get(key, 0) + 1
        if "conversación cerrada" in low or "conversacion cerrada" in low:
            cierres += 1
            has_nota = "nota:" in low
            if not has_nota and conv:
                cctx = _parse_contexto(conv.contexto_json)
                has_nota = bool(cctx.get("cierre_nota"))
            if has_nota:
                cierres_con_nota += 1
            key = _resolve_agent_key(texto, conv, cierre=True)
            cierres_by_agent[key] = cierres_by_agent.get(key, 0) + 1

    # First response aproximada: primer msg agente en rango por conversación,
    # vs updated_at de convs que tienen agente (proxy rough: primer cliente vs primer agente
    # en mensajes históricos de esas convs).
    first_response_mins: list[float] = []
    conv_ids_with_agent_msg = {m.conversacion_id for m in msgs if m.autor == "agente" and "tomó el caso" not in (m.texto or "").lower() and not (m.texto or "").startswith("[Sistema]")}
    if conv_ids_with_agent_msg:
        hist = list(
            db.scalars(
                select(MensajeCanal)
                .where(MensajeCanal.conversacion_id.in_(list(conv_ids_with_agent_msg)))
                .order_by(MensajeCanal.created_at.asc())
            ).all()
        )
        by_conv: dict[str, list[MensajeCanal]] = {}
        for m in hist:
            by_conv.setdefault(m.conversacion_id, []).append(m)
        for _cid, thread in by_conv.items():
            first_cliente = next((m for m in thread if m.autor == "cliente"), None)
            first_agente = next(
                (
                    m
                    for m in thread
                    if m.autor == "agente"
                    and "tomó el caso" not in (m.texto or "").lower()
                    and not (m.texto or "").lower().startswith("[sistema]")
                ),
                None,
            )
            if first_cliente and first_agente:
                t0 = _ensure_aware(first_cliente.created_at)
                t1 = _ensure_aware(first_agente.created_at)
                if t0 and t1 and t1 >= t0:
                    first_response_mins.append((t1 - t0).total_seconds() / 60.0)

    canal_block = {
        "abiertas_por_estado": por_estado,
        "espera_count": len(espera),
        "espera_minutos_mediana": _percentile(espera_mins, 0.5),
        "espera_minutos_p95": _percentile(espera_mins, 0.95),
        "por_canal": [{"label": k, "count": v} for k, v in sorted(por_canal.items(), key=lambda x: -x[1])],
        "claims_en_rango": claims,
        "cierres_en_rango": cierres,
        "cierres_con_nota": cierres_con_nota,
        "pct_cierres_con_nota": round((cierres_con_nota / cierres) * 100, 1) if cierres else 0.0,
        "first_response_minutos_mediana": _percentile(first_response_mins, 0.5),
    }

    # ---- Tickets ----
    creados = [t for t in tickets if _in_range(t.created_at, desde, hasta)]
    cerrados = [
        t
        for t in tickets
        if t.estado == "Cerrado" and _in_range(t.updated_at, desde, hasta)
    ]
    con_resolucion = [t for t in cerrados if (t.resolucion_tecnica or "").strip()]
    abiertos_now = [t for t in tickets if t.estado != "Cerrado"]
    sla_vencidos = [
        t
        for t in abiertos_now
        if (t.estado_sla or "") == "Vencido"
        or (t.sla_breached_at is not None)
    ]
    breach_cerrados = [t for t in cerrados if t.sla_breached_at is not None]

    por_nivel: dict[str, int] = {}
    por_cat: dict[str, int] = {}
    for t in creados:
        por_nivel[t.nivel or "N1"] = por_nivel.get(t.nivel or "N1", 0) + 1
        cat = t.categoria or "General"
        por_cat[cat] = por_cat.get(cat, 0) + 1

    tickets_block = {
        "creados": len(creados),
        "cerrados": len(cerrados),
        "abiertos_ahora": len(abiertos_now),
        "con_resolucion": len(con_resolucion),
        "pct_resolucion_documentada": round(
            (len(con_resolucion) / len(cerrados)) * 100, 1
        )
        if cerrados
        else 0.0,
        "sla_vencidos_abiertos": len(sla_vencidos),
        "cerrados_con_breach": len(breach_cerrados),
        "por_nivel": [{"label": k, "count": v} for k, v in sorted(por_nivel.items())],
        "top_categorias": [
            {"label": k, "count": v}
            for k, v in sorted(por_cat.items(), key=lambda x: -x[1])[:8]
        ],
    }

    # ---- Agentes ----
    agentes_rows: list[dict[str, Any]] = []
    for u in users:
        email = (u.email or "").lower()
        keys = agent_keys(email, u.nombre or "")
        if agent_filter:
            af = agent_filter.lower()
            if af not in keys and email != af:
                continue

        t_asignados_abiertos = [
            t
            for t in abiertos_now
            if _match_agent(t.asignado_a, keys)
        ]
        t_cerrados = [
            t
            for t in cerrados
            if _match_agent(t.asignado_a, keys) or _match_agent(t.creado_por, keys)
        ]
        t_cerrados_doc = [t for t in t_cerrados if (t.resolucion_tecnica or "").strip()]
        chats_abiertos = [
            c
            for c in abiertas
            if c.estado == "con_agente" and _match_agent(c.agente_id, keys)
        ]
        claim_n = sum(claims_by_agent.get(k, 0) for k in keys) or claims_by_agent.get(email, 0)
        cierre_n = sum(cierres_by_agent.get(k, 0) for k in keys) or cierres_by_agent.get(email, 0)

        row: dict[str, Any] = {
            "email": u.email or "",
            "nombre": u.nombre or u.email or "",
            "disponibilidad": getattr(u, "disponibilidad", "") or "disponible",
            "tickets_abiertos": len(t_asignados_abiertos),
            "tickets_cerrados": len(t_cerrados),
            "tickets_con_resolucion": len(t_cerrados_doc),
            "pct_resolucion": round(
                (len(t_cerrados_doc) / len(t_cerrados)) * 100, 1
            )
            if t_cerrados
            else 0.0,
            "chats_activos": len(chats_abiertos),
            "claims": claim_n,
            "cierres_canal": cierre_n,
        }
        if admin_global:
            row["organizacion"] = org_names.get(u.organizacion_id, "")
        agentes_rows.append(row)

    agentes_rows.sort(key=lambda r: (-r["tickets_cerrados"], -r["claims"], r["email"]))

    me_block = None
    if agent_filter:
        me_block = agentes_rows[0] if agentes_rows else {
            "email": agent_filter,
            "nombre": agent_filter,
            "disponibilidad": "",
            "tickets_abiertos": 0,
            "tickets_cerrados": 0,
            "tickets_con_resolucion": 0,
            "pct_resolucion": 0.0,
            "chats_activos": 0,
            "claims": 0,
            "cierres_canal": 0,
        }

    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "alcance": "global" if admin_global else "organizacion",
        "canal": canal_block,
        "tickets": tickets_block,
        "agentes": agentes_rows,
        "me": me_block,
    }
