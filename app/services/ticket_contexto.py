"""Contexto operativo para tickets — SMS/A2P y respuestas proactivas."""

from __future__ import annotations

from app.estate import repository as repo


def lineas_contexto_sms(hechos: dict) -> list[str]:
    lineas: list[str] = []
    rem = (hechos.get("sms_remitente_ejemplo") or "").strip()
    hor = (hechos.get("sms_horario_incidente") or "").strip()
    if rem:
        lineas.append(f"Remitente/ejemplo: {rem}")
    if hor:
        lineas.append(f"Horario incidente: {hor}")
    return lineas


def texto_contexto_sms(hechos: dict) -> str:
    return "\n".join(lineas_contexto_sms(hechos))


def enriquecer_clasificacion_con_hechos(clasif: dict, datos_triaje: dict) -> dict:
    """Inyecta evidencia SMS y acciones N1 en la clasificación antes de crear ticket."""
    out = dict(clasif)
    hechos = datos_triaje.get("hechos") or {}
    evidencia = list(out.get("evidencia") or [])
    for linea in lineas_contexto_sms(hechos):
        if linea not in evidencia:
            evidencia.append(linea)
    if evidencia:
        out["evidencia"] = evidencia
    pasos = hechos.get("pasos_realizados") or []
    if pasos:
        out["acciones_n1_realizadas"] = "; ".join(pasos[-6:])
    return out


def _resumir_sintoma(sintoma: str) -> str:
    t = (sintoma or "").strip()
    if not t:
        return "el inconveniente reportado"
    tl = t.lower()
    if "sms" in tl or "a2p" in tl or "mensaje" in tl:
        if "confirmacion" in tl or "confirmación" in tl:
            return "no recibir SMS de confirmación"
        if any(p in tl for p in ("apple", "netflix", "membresia", "membresía")):
            return "problemas con SMS/A2P de plataformas (membresías)"
        return "problemas con SMS/A2P"
    return t[:120] + ("…" if len(t) > 120 else "")


def respuesta_ticket_creado_proactivo(
    ticket: dict,
    datos: dict,
    clasif: dict | None = None,
) -> str:
    """Anuncia ticket recién creado — sin esperar que el operador pregunte."""
    clasif = clasif or {}
    tid = ticket.get("id", "")
    linea = ticket.get("linea") or datos.get("linea") or ""
    nivel = ticket.get("nivel") or clasif.get("nivel") or "N2"
    destino = ticket.get("destino") or clasif.get("destino") or "carrier"
    estado = ticket.get("estado") or ticket.get("estado_sla") or "Abierto"
    hechos = datos.get("hechos") or {}
    problema = _resumir_sintoma(datos.get("sintoma", ""))
    sms_ctx = lineas_contexto_sms(hechos)

    destino_label = "carrier" if destino == "carrier" else destino.replace("_", " ")
    msg = (
        f"Listo. Creé el ticket {tid} para la línea {linea} "
        f"con el problema de {problema}. "
        f"Estado actual: {estado}, nivel {nivel}, destino {destino_label}."
    )
    if sms_ctx:
        msg += " Datos cargados para escalamiento: " + "; ".join(sms_ctx) + "."
    elif (hechos.get("categoria_flujo") or "") == "sms":
        msg += (
            " Si tenés remitente u horario del incidente, pasámelos "
            "y los sumo al ticket para el carrier."
        )
    return msg


def persistir_datos_sms_en_ticket(
    db,
    org_id: str,
    ticket_id: str,
    *,
    hechos_prev: dict,
    hechos_new: dict,
    actor: str = "consola",
) -> list[str]:
    """Agrega remitente/horario SMS al ticket cuando el operador los aporta después."""
    traces: list[str] = []
    nuevos = lineas_contexto_sms(hechos_new)
    previos = set(lineas_contexto_sms(hechos_prev))
    agregados = [l for l in nuevos if l not in previos]
    if not agregados:
        return traces

    t = repo.get_ticket(db, org_id, ticket_id)
    if not t:
        return traces

    bloque = "\n".join(agregados)
    evidencia = (t.evidencia or "").strip()
    if bloque not in evidencia:
        evidencia = f"{evidencia}\n{bloque}".strip() if evidencia else bloque
        t.evidencia = evidencia[:4000]
        db.commit()
        db.refresh(t)

    detalle = "; ".join(agregados)
    repo.add_ticket_event(
        db,
        org_id,
        ticket_id,
        tipo="contexto_sms",
        titulo="Datos SMS para carrier",
        detalle=detalle[:1800],
        nivel=t.nivel,
        estado=t.estado,
        actor=actor,
    )
    traces.append(f"📬 [Ticket]: Contexto SMS actualizado en {ticket_id}")
    return traces
