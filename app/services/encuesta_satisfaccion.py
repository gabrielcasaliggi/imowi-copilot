"""Encuesta CSAT 1–5 tras cierre N1 (bot) o atención humana."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.estate import canal_repo as crepo
from app.estate.models import ConversacionCanal, EncuestaSatisfaccion, Ticket, User

logger = logging.getLogger("operations_hub")

ORIGEN_BOT = "[BOT]"
ORIGEN_TECNICO = "[TECNICO]"
TAG_CSAT_BAJO = "[CSAT_BAJO]"

PREGUNTA = "¿Cómo calificarías la atención recibida hoy?"

OPCIONES: list[tuple[int, str, str]] = [
    (1, "⭐", "Muy mala"),
    (2, "⭐⭐", "Mala"),
    (3, "⭐⭐⭐", "Regular"),
    (4, "⭐⭐⭐⭐", "Buena"),
    (5, "⭐⭐⭐⭐⭐", "Excelente"),
]

_MENSAJE_GRACIAS = "¡Gracias por tu calificación! Nos ayuda a mejorar."
_VENTANA_ENCUESTA = timedelta(hours=48)


def estrellas_visual(n: int) -> str:
    """★ encendidas + ☆ apagadas (1–5)."""
    k = max(0, min(5, int(n)))
    return ("★" * k) + ("☆" * (5 - k))


def texto_encuesta_corto() -> str:
    """Solo la pregunta — la UI de estrellas va en botones / widget."""
    return PREGUNTA


def texto_encuesta_plano() -> str:
    """Fallback texto (web/simulate sin widget)."""
    return (
        f"{PREGUNTA}\n\n"
        f"{estrellas_visual(0)}\n"
        "Tocá o respondé con un número del 1 al 5."
    )


def texto_encuesta_confirmacion(puntuacion: int) -> str:
    return f"{PREGUNTA}\n\n{estrellas_visual(puntuacion)}\n\n{_MENSAJE_GRACIAS}"


def parse_puntuacion(texto: str) -> int | None:
    """Extrae puntuación 1–5 desde texto libre, botón o callback."""
    raw = (texto or "").strip()
    if not raw:
        return None
    low = raw.lower()

    m = re.match(r"^csat[:_\-]?([1-5])$", low)
    if m:
        return int(m.group(1))

    if re.fullmatch(r"[1-5]", raw):
        return int(raw)

    # ReplyKeyboard CSAT: "☆ 1", "☆ 4", "★ 5"
    m = re.fullmatch(r"[☆★⭐]\s*([1-5])", raw)
    if m:
        return int(m.group(1))

    # Solo estrellas: ★★★☆☆ o ☆☆☆☆☆ (Telegram/web)
    if re.fullmatch(r"[★☆⭐]+", raw):
        filled = raw.count("★") + raw.count("⭐")
        if 1 <= filled <= 5:
            return filled

    m = re.match(r"^([1-5])\s*[\.)\-]?\s", raw)
    if m:
        return int(m.group(1))

    # Títulos de lista WA / labels: "1 · Muy mala", "⭐ (1) Muy mala"
    m = re.search(r"(?:^|[^\d])([1-5])(?:\s*[·\-)|]|\s*$)", raw)
    if m and any(lab.lower() in low for _, _, lab in OPCIONES):
        return int(m.group(1))

    for n, estrellas, label in OPCIONES:
        if low == label.lower() or low == f"{n} {label.lower()}":
            return n
        if estrellas in raw and str(n) in raw:
            return n

    return None


def _now() -> datetime:
    return datetime.now(UTC)


def _ensure_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def ya_tiene_voto(db: Session, conversacion_id: str) -> bool:
    if not conversacion_id:
        return False
    return (
        db.scalar(
            select(EncuestaSatisfaccion.id).where(
                EncuestaSatisfaccion.conversacion_id == conversacion_id
            )
        )
        is not None
    )


def find_conversacion_encuesta_pendiente(
    db: Session,
    org_id: str,
    *,
    telefono: str,
    canal: str,
    wa_id: str = "",
) -> ConversacionCanal | None:
    """Última conversación con encuesta pendiente para ese chat (ventana 48h)."""
    canal_norm = (canal or "whatsapp").strip() or "whatsapp"
    tel = crepo.normalizar_identidad(canal_norm, telefono)
    wa = (wa_id or "").strip()
    if canal_norm == "telegram" and wa:
        wa = crepo.normalizar_identidad("telegram", wa)
    identities = {x for x in (tel, wa) if x}

    q = (
        select(ConversacionCanal)
        .where(
            ConversacionCanal.organizacion_id == org_id,
            ConversacionCanal.canal == canal_norm,
        )
        .order_by(ConversacionCanal.updated_at.desc())
        .limit(40)
    )
    candidates = list(db.scalars(q).all())
    cutoff = _now() - _VENTANA_ENCUESTA
    for conv in candidates:
        conv_ids = {x for x in ((conv.telefono or "").strip(), (conv.wa_id or "").strip()) if x}
        if identities and conv_ids.isdisjoint(identities):
            continue
        ctx = crepo.get_contexto(conv)
        pendiente = bool(ctx.get("encuesta_pendiente")) or (
            bool(ctx.get("encuesta_enviada")) and not bool(ctx.get("encuesta_respondida"))
        )
        if not pendiente:
            continue
        if ya_tiene_voto(db, conv.id):
            continue
        updated = _ensure_aware(conv.updated_at) or cutoff
        if updated < cutoff:
            continue
        return conv
    return None


def _dispatch_encuesta(conv: ConversacionCanal, texto: str) -> dict:
    canal = conv.canal or ""
    dest = (conv.wa_id or conv.telefono or "").strip()
    if canal == "whatsapp":
        from app.services.whatsapp_client import enviar_encuesta_csat as enviar_wa

        return enviar_wa(dest, texto)
    if canal == "telegram":
        from app.services.telegram_client import enviar_encuesta_csat as enviar_tg

        return enviar_tg(dest, texto)
    # web / simulate: solo texto en inbox
    return {"ok": True, "simulated": True}


def enviar_encuesta_cierre(
    db: Session,
    conv: ConversacionCanal,
    *,
    origen: str,
    agente_id: str = "",
    enviar_externo: bool = True,
) -> dict[str, Any]:
    """Marca encuesta pendiente y la envía al abonado (idempotente por conversación)."""
    origen_n = ORIGEN_BOT if origen == ORIGEN_BOT else ORIGEN_TECNICO
    if ya_tiene_voto(db, conv.id):
        return {"ok": False, "reason": "ya_respondida"}

    ctx = crepo.get_contexto(conv)
    if ctx.get("encuesta_pendiente") or ctx.get("encuesta_enviada"):
        return {"ok": False, "reason": "ya_enviada"}

    agente = (agente_id or "").strip()
    if origen_n == ORIGEN_TECNICO and not agente:
        agente = (conv.agente_id or ctx.get("cierre_por") or "").strip()

    ctx["encuesta_pendiente"] = True
    ctx["encuesta_enviada"] = True
    ctx["encuesta_origen"] = origen_n
    ctx["encuesta_agente_id"] = agente
    ctx["encuesta_enviada_at"] = _now().isoformat()
    crepo.set_contexto(conv, ctx)
    db.commit()

    texto = texto_encuesta_corto() if (conv.canal or "") in ("whatsapp", "telegram", "web") else texto_encuesta_plano()
    crepo.add_mensaje(
        db,
        conv.organizacion_id,
        conv.id,
        direccion="out",
        autor="bot" if origen_n == ORIGEN_BOT else "sistema",
        texto=texto,
    )

    delivery: dict[str, Any] = {"ok": True, "simulated": True}
    if enviar_externo and (conv.canal or "") in ("whatsapp", "telegram"):
        delivery = _dispatch_encuesta(conv, texto)
        mid = str(delivery.get("meta_message_id") or "").strip()
        if mid:
            ctx2 = crepo.get_contexto(conv)
            ctx2["encuesta_message_id"] = mid
            crepo.set_contexto(conv, ctx2)
            db.commit()
        if not delivery.get("ok") or delivery.get("simulated"):
            logger.warning(
                "Encuesta CSAT canal=%s conv=%s ok=%s simulated=%s detail=%s",
                conv.canal,
                conv.id,
                delivery.get("ok"),
                delivery.get("simulated"),
                (delivery.get("detail") or delivery.get("reason") or "")[:200],
            )

    return {"ok": True, "delivery": delivery, "origen": origen_n}


def _aplicar_tag_csat_bajo(db: Session, conv: ConversacionCanal, puntuacion: int) -> None:
    if puntuacion > 2:
        return
    ctx = crepo.get_contexto(conv)
    ctx["csat_bajo"] = True
    ctx["csat_puntuacion"] = puntuacion
    crepo.set_contexto(conv, ctx)

    origen = str(ctx.get("encuesta_origen") or ORIGEN_BOT)
    agente = str(ctx.get("encuesta_agente_id") or conv.agente_id or "").strip()
    tid = (conv.ticket_id or "").strip() or None

    from app.estate import repository as repo

    t = db.get(Ticket, tid) if tid else None
    if t:
        desc = t.descripcion_falla or ""
        if TAG_CSAT_BAJO not in desc:
            t.descripcion_falla = f"{TAG_CSAT_BAJO} {desc}".strip()
        motivo = (t.motivo_escalamiento or "").strip()
        nota = f"{TAG_CSAT_BAJO} calificación {puntuacion}/5 — revisar por supervisor"
        if TAG_CSAT_BAJO not in motivo:
            t.motivo_escalamiento = f"{nota}. {motivo}".strip() if motivo else nota
        try:
            repo.add_ticket_event(
                db,
                t.organizacion_id,
                t.id,
                tipo="csat_bajo",
                titulo=f"{TAG_CSAT_BAJO} Calificación baja",
                detalle=f"Abonado calificó {puntuacion}/5. Revisar por supervisor.",
                actor="sistema",
                estado=t.estado or "",
                nivel=t.nivel or "",
            )
        except Exception:
            db.rollback()
            logger.warning("No se pudo registrar evento CSAT_BAJO en ticket %s", tid, exc_info=True)

    # Notificar supervisores/admins de la org + admins plataforma
    titulo = f"{TAG_CSAT_BAJO} Atención calificada {puntuacion}/5"
    ref = f"Ticket {tid}" if tid else f"Conversación {conv.id[:8]}"
    quien = f"Agente: {agente}" if agente else "Origen: bot N1"
    mensaje = (
        f"{ref} recibió calificación baja ({puntuacion}/5). "
        f"{quien}. Origen {origen}. Revisá el caso."
    )
    destinatarios: set[str] = set()
    try:
        for email in repo.destinatarios_alerta_csat(db, conv.organizacion_id):
            destinatarios.add(email)
    except Exception:
        logger.warning("No se pudieron listar destinatarios CSAT_BAJO", exc_info=True)
    if agente and "@" in agente:
        destinatarios.add(agente.strip().lower())

    if not destinatarios:
        logger.error(
            "CSAT_BAJO sin destinatarios org=%s conv=%s — no hay supervisores/admins activos",
            conv.organizacion_id,
            conv.id,
        )

    creadas = 0
    for dest in destinatarios:
        try:
            repo.add_ticket_notification(
                db,
                conv.organizacion_id,
                tid,
                destinatario=dest,
                titulo=titulo[:160],
                mensaje=mensaje,
                canal="csat_bajo",
            )
            creadas += 1
        except Exception:
            db.rollback()
            logger.warning("No se pudo notificar CSAT_BAJO a %s", dest, exc_info=True)

    logger.info(
        "CSAT_BAJO notifs creadas=%s/%s org=%s conv=%s score=%s",
        creadas,
        len(destinatarios),
        conv.organizacion_id,
        conv.id,
        puntuacion,
    )

    try:
        from app.estate.audit import log_audit

        log_audit(
            db,
            org_id=conv.organizacion_id,
            actor="sistema",
            accion="csat_bajo",
            recurso=tid or conv.id,
            detalle=f"puntuacion={puntuacion} origen={origen} notifs={creadas}",
        )
    except Exception:
        logger.debug("Audit CSAT_BAJO omitido", exc_info=True)


def registrar_voto(
    db: Session,
    conv: ConversacionCanal,
    puntuacion: int,
    *,
    enviar_externo: bool = True,
    enviar_gracias_externo: bool = True,
) -> dict[str, Any]:
    """Persiste el voto y limpia la encuesta pendiente."""
    if puntuacion < 1 or puntuacion > 5:
        return {"ok": False, "reason": "puntuacion_invalida"}
    if ya_tiene_voto(db, conv.id):
        return {"ok": False, "reason": "ya_respondida", "puntuacion": int(puntuacion)}

    ctx = crepo.get_contexto(conv)
    origen = str(ctx.get("encuesta_origen") or ORIGEN_BOT)
    if origen not in (ORIGEN_BOT, ORIGEN_TECNICO):
        origen = ORIGEN_BOT if origen.upper().find("BOT") >= 0 else ORIGEN_TECNICO
    agente = str(ctx.get("encuesta_agente_id") or conv.agente_id or "").strip()

    row = EncuestaSatisfaccion(
        organizacion_id=conv.organizacion_id,
        abonado_id=(conv.abonado_id or "").strip(),
        conversacion_id=conv.id,
        ticket_id=(conv.ticket_id or "").strip(),
        origen=origen,
        puntuacion=int(puntuacion),
        canal=(conv.canal or "").strip(),
        agente_id=agente,
    )
    db.add(row)
    ctx["encuesta_pendiente"] = False
    ctx["encuesta_respondida"] = True
    ctx["encuesta_puntuacion"] = int(puntuacion)
    crepo.set_contexto(conv, ctx)
    # Commit del voto ANTES de side-effects (notifs) para no perder la calificación
    db.commit()
    db.refresh(row)

    try:
        _aplicar_tag_csat_bajo(db, conv, int(puntuacion))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Side-effect CSAT_BAJO falló conv=%s (voto ya guardado)", conv.id)

    crepo.add_mensaje(
        db,
        conv.organizacion_id,
        conv.id,
        direccion="out",
        autor="bot",
        texto=texto_encuesta_confirmacion(int(puntuacion))
        if (conv.canal or "") == "telegram"
        else _MENSAJE_GRACIAS,
    )
    if (
        enviar_externo
        and enviar_gracias_externo
        and (conv.canal or "") in ("whatsapp", "telegram")
    ):
        try:
            dest = (conv.wa_id or conv.telefono or "").strip()
            if conv.canal == "whatsapp":
                from app.services.whatsapp_client import enviar_texto as enviar_wa

                enviar_wa(dest, _MENSAJE_GRACIAS)
            elif conv.canal == "telegram":
                from app.services.telegram_client import quitar_teclado

                # Confirmación con ★ encendidas + saca el teclado ☆ 1…5
                quitar_teclado(dest, texto_encuesta_confirmacion(int(puntuacion)))
        except Exception:
            logger.warning("No se pudo enviar gracias CSAT conv=%s", conv.id, exc_info=True)

    return {
        "ok": True,
        "encuesta_id": row.id,
        "puntuacion": int(puntuacion),
        "origen": origen,
        "csat_bajo": int(puntuacion) <= 2,
    }


def capturar_voto_telegram(
    db: Session,
    org_id: str,
    *,
    chat_id: str,
    puntuacion: int,
    meta_message_id: str = "",
) -> dict[str, Any]:
    """Registra voto CSAT desde callback_query (sin abrir hilo nuevo)."""
    conv = find_conversacion_encuesta_pendiente(
        db,
        org_id,
        telefono=str(chat_id),
        canal="telegram",
        wa_id=str(chat_id),
    )
    if not conv:
        logger.warning(
            "CSAT Telegram: sin encuesta pendiente org=%s chat=%s score=%s",
            org_id,
            chat_id,
            puntuacion,
        )
        return {"ok": False, "reason": "sin_pendiente", "puntuacion": int(puntuacion)}

    crepo.add_mensaje(
        db,
        org_id,
        conv.id,
        direccion="in",
        autor="cliente",
        texto=f"csat:{puntuacion}",
        meta_message_id=meta_message_id,
    )
    # En TG el mensaje de encuesta se edita en el webhook (no mandar otro "gracias")
    result = registrar_voto(
        db,
        conv,
        int(puntuacion),
        enviar_externo=False,
        enviar_gracias_externo=False,
    )
    result["modo"] = "encuesta"
    result["conversacion_id"] = conv.id
    result["estado"] = conv.estado
    return result


def intentar_capturar_voto(
    db: Session,
    org_id: str,
    *,
    telefono: str,
    texto: str,
    canal: str,
    wa_id: str = "",
    meta_message_id: str = "",
    enviar_externo: bool = True,
) -> dict[str, Any] | None:
    """Si el texto es un voto y hay encuesta pendiente, lo registra. None = no aplica."""
    puntuacion = parse_puntuacion(texto)
    if not puntuacion:
        return None
    conv = find_conversacion_encuesta_pendiente(
        db, org_id, telefono=telefono, canal=canal, wa_id=wa_id
    )
    if not conv:
        return None

    crepo.add_mensaje(
        db,
        org_id,
        conv.id,
        direccion="in",
        autor="cliente",
        texto=texto,
        meta_message_id=meta_message_id,
    )
    result = registrar_voto(db, conv, puntuacion, enviar_externo=enviar_externo)
    result["modo"] = "encuesta"
    result["conversacion_id"] = conv.id
    result["respuesta"] = _MENSAJE_GRACIAS if result.get("ok") else ""
    result["estado"] = conv.estado
    return result


def _agg_bloque(rows: list[EncuestaSatisfaccion]) -> dict[str, Any]:
    dist = {str(i): 0 for i in range(1, 6)}
    for r in rows:
        k = str(int(r.puntuacion))
        if k in dist:
            dist[k] += 1
    total = len(rows)
    promedio = round(sum(r.puntuacion for r in rows) / total, 2) if total else None
    bajas = sum(1 for r in rows if r.puntuacion <= 2)
    return {
        "total": total,
        "promedio": promedio,
        "distribucion": dist,
        "bajas": bajas,
        "pct_bajas": round((bajas / total) * 100, 1) if total else 0.0,
    }


def build_csat_analytics(
    db: Session,
    org_id: str,
    *,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    agent_filter: str | None = None,
    admin_global: bool = False,
) -> dict[str, Any]:
    now = _now()
    if not hasta:
        hasta = now
    if not desde:
        desde = hasta - timedelta(days=7)

    q = select(EncuestaSatisfaccion).where(
        EncuestaSatisfaccion.created_at >= desde,
        EncuestaSatisfaccion.created_at <= hasta,
    )
    if not admin_global:
        q = q.where(EncuestaSatisfaccion.organizacion_id == org_id)

    rows = list(db.scalars(q).all())
    agent_f = (agent_filter or "").strip().lower()

    if agent_f:
        rows_me = [
            r
            for r in rows
            if (r.agente_id or "").strip().lower() == agent_f
            or (
                "@" in agent_f
                and (r.agente_id or "").strip().lower().split("@", 1)[0]
                == agent_f.split("@", 1)[0]
            )
        ]
        return {
            "desde": desde.isoformat(),
            "hasta": hasta.isoformat(),
            "alcance": "agente",
            "me": _agg_bloque(rows_me),
            "bot": None,
            "agentes": [],
            "resumen": _agg_bloque(rows_me),
        }

    bot_rows = [r for r in rows if r.origen == ORIGEN_BOT]
    tec_rows = [r for r in rows if r.origen == ORIGEN_TECNICO]

    user_q = select(User)
    if not admin_global:
        user_q = user_q.where(User.organizacion_id == org_id)
    users = list(db.scalars(user_q).all())
    nombre_por_email = {
        (u.email or "").strip().lower(): (u.nombre or u.email or "").strip()
        for u in users
        if (u.email or "").strip()
    }

    by_agent: dict[str, list[EncuestaSatisfaccion]] = {}
    for r in tec_rows:
        key = (r.agente_id or "").strip().lower() or "sin_asignar"
        by_agent.setdefault(key, []).append(r)

    agentes = []
    for key, arows in sorted(by_agent.items(), key=lambda x: -len(x[1])):
        bloque = _agg_bloque(arows)
        agentes.append(
            {
                "agente_id": key,
                "nombre": nombre_por_email.get(key) or key,
                **bloque,
            }
        )

    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "alcance": "global" if admin_global else "organizacion",
        "resumen": _agg_bloque(rows),
        "bot": _agg_bloque(bot_rows),
        "tecnicos": _agg_bloque(tec_rows),
        "agentes": agentes,
        "me": None,
    }
