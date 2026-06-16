"""Agente 3 — Orquestación de servicios, clasificación N1/N2/Proveedor e intents OSS/BSS."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.taxonomia import AccionClasificacion, NivelTicket
from app.estate import repository as repo
from app.services import clasificador
from app.services import ticket_bridge


def ejecutar_orquestacion(
    db: Session,
    org_id: str,
    datos_triaje: dict,
    diagnostico: dict,
    historial: list[dict],
    *,
    forzar_escalamiento: bool = False,
    creado_por: str = "",
    crear_ticket: bool = True,
    clasificacion_precalculada: dict | None = None,
) -> dict:
    traces: list[str] = []
    acciones: list[dict] = []
    ticket = None

    traces.append("⚙️ [Agente Orquestación]: Evaluando clasificación N1/N2/Proveedor…")

    kb_resultado = diagnostico.get("kb_resultado") or {}
    if clasificacion_precalculada:
        clasif_dict = dict(clasificacion_precalculada)
        clasif = None
    else:
        clasif = clasificador.clasificar_caso(
            datos_triaje,
            diagnostico,
            kb_resultado,
            historial,
            forzar_escalamiento=forzar_escalamiento,
        )
        clasif_dict = clasificador.resultado_a_dict(clasif)

    accion_txt = clasif_dict.get("accion", "")
    traces.append(
        f"🎯 [Clasificador]: {accion_txt} | nivel={clasif_dict.get('nivel') or '-'} "
        f"| destino={clasif_dict.get('destino') or '-'} | regla={clasif_dict.get('regla_aplicada')}"
    )
    if clasif_dict.get("proveedor"):
        traces.append(f"🏭 [Clasificador]: Proveedor sugerido → {clasif_dict['proveedor']}")
    if clasif_dict.get("datos_faltantes"):
        traces.append(f"📋 [Clasificador]: Datos faltantes → {', '.join(clasif_dict['datos_faltantes'])}")
    if clasif_dict.get("pasos_n1"):
        traces.append(f"📖 [Clasificador]: {len(clasif_dict['pasos_n1'])} paso(s) N1 pendientes")

    acciones.append({
        "intent": "CLASIFICAR_CASO",
        "estado": "completado",
        "descripcion": f"Decisión: {accion_txt} ({clasif_dict.get('regla_aplicada')})",
        "clasificacion": clasif_dict,
    })

    sintoma = (datos_triaje.get("sintoma") or "").lower()
    intent = None
    descripcion_intent = ""

    accion = accion_txt
    if accion == AccionClasificacion.CREAR_TICKET_N2.value and diagnostico.get("anomalia_red"):
        intent = "ESCALAR_INCIDENTE_CORE"
        descripcion_intent = (
            f"Escalamiento automático por anomalía en {diagnostico.get('elemento_afectado')}."
        )
    elif "roaming" in sintoma or diagnostico.get("categoria") == "Roaming":
        intent = "PROVISIONAR_ROAMING_VISITADO"
        descripcion_intent = "Intent: validar perfil roaming y registro en red visitada."
    elif "apn" in sintoma or diagnostico.get("categoria") == "APN":
        intent = "PROVISIONAR_APN_NUEVO"
        descripcion_intent = "Intent: reprovisionar APN y refrescar sesión PDP."
    elif "esim" in sintoma or diagnostico.get("categoria") == "eSIM":
        intent = "REPROVISIONAR_ESIM"
        descripcion_intent = "Intent: reenvío OTA perfil eSIM."
    elif accion == AccionClasificacion.CREAR_TICKET_N1.value:
        intent = "CREAR_TICKET_N1"
        descripcion_intent = "Intent: registrar ticket N1 para seguimiento de la cooperativa."
    elif accion in (AccionClasificacion.CREAR_TICKET_N2.value, AccionClasificacion.DERIVAR_PROVEEDOR.value):
        intent = "ESCALAR_INCIDENTE_NOC"
        descripcion_intent = f"Intent: {clasif_dict.get('motivo_escalamiento') or 'registro de incidente'}"

    if intent and crear_ticket:
        traces.append(f"⚙️ [Agente Orquestación]: Ejecutando intent → {intent}")
        acciones.append({
            "intent": intent,
            "estado": "simulado_ok",
            "descripcion": descripcion_intent,
        })

    crear = accion in (
        AccionClasificacion.CREAR_TICKET_N1.value,
        AccionClasificacion.CREAR_TICKET_N2.value,
        AccionClasificacion.DERIVAR_PROVEEDOR.value,
    )

    ticket_previo = diagnostico.get("ticket_abierto_existente")
    if ticket_previo and crear and not crear_ticket:
        existente = repo.get_ticket(db, org_id, ticket_previo["id"])
        if existente:
            ticket = existente
            traces.append(
                f"⚙️ [Agente Orquestación]: Vinculado ticket existente {ticket.id} — sin duplicar."
            )
            acciones.append({
                "intent": "VINCULAR_TICKET_EXISTENTE",
                "estado": "completado",
                "descripcion": f"Ticket {ticket.id} ya abierto para la línea.",
                "ticket_id": ticket.id,
            })

    if crear and crear_ticket and (datos_triaje.get("linea") or diagnostico.get("anomalia_red_correlacionada")):
        proactivo = bool(diagnostico.get("anomalia_red_correlacionada"))
        origen = "Autónomo Predictivo" if proactivo else "Reporte Cliente"
        linea = datos_triaje.get("linea") or ("PROACTIVO-" + (diagnostico.get("elemento_afectado") or "RED")[:20])
        dispositivo = datos_triaje.get("dispositivo") or diagnostico.get("elemento_afectado") or "Infraestructura"
        desc = _armar_descripcion(datos_triaje, diagnostico, clasif_dict)
        nivel = clasif_dict.get("nivel") or NivelTicket.N2.value
        destino = clasif_dict.get("destino") or "imowi_noc"
        evidencia_txt = "\n".join(clasif_dict.get("evidencia") or [])
        acciones_n1 = clasif_dict.get("acciones_n1_realizadas") or ""

        ticket = ticket_bridge.crear_ticket(
            db,
            org_id,
            linea=linea,
            dispositivo=dispositivo,
            descripcion_falla=desc,
            origen=origen,
            categoria=clasif_dict.get("categoria") or diagnostico.get("categoria", "General"),
            intent_ejecutado=intent or "",
            creado_por=creado_por,
            nivel=nivel,
            destino=destino,
            proveedor=clasif_dict.get("proveedor") or "",
            motivo_escalamiento=clasif_dict.get("motivo_escalamiento") or "",
            evidencia=evidencia_txt,
            acciones_n1_realizadas=acciones_n1,
            regla_clasificacion=clasif_dict.get("regla_aplicada") or "",
            estado_sla="Abierto",
        )
        traces.append(f"✅ [Agente Orquestación]: Ticket {ticket.id} creado ({nivel} → {destino}).")
        acciones.append({
            "intent": "CREAR_TICKET_OSS",
            "estado": "completado",
            "descripcion": f"Ticket {ticket.id} ({nivel}/{destino}) registrado en Data Estate.",
            "ticket_id": ticket.id,
        })
    elif accion == AccionClasificacion.RESOLVER_N1.value:
        traces.append("⚙️ [Agente Orquestación]: Resolución N1 — sin ticket N2/proveedor por ahora.")
        pasos = clasif_dict.get("pasos_n1") or []
        if pasos:
            acciones.append({
                "intent": "GUIA_N1",
                "estado": "pendiente",
                "descripcion": pasos[0][:200],
                "pasos": pasos,
            })
    elif accion == AccionClasificacion.PEDIR_DATOS.value:
        traces.append("⚙️ [Agente Orquestación]: Faltan datos — solicitar al operador antes de automatizar.")
    elif crear and not crear_ticket:
        traces.append("⚙️ [Agente Orquestación]: Ticket pendiente de confirmación del operador.")
    else:
        traces.append("⚙️ [Agente Orquestación]: Sin ticket — decisión no requiere escalamiento.")

    return {
        "acciones": acciones,
        "ticket": ticket,
        "clasificacion": clasif_dict,
        "traces": traces,
    }


def _armar_descripcion(datos: dict, diag: dict, clasif: dict) -> str:
    partes = [
        f"CLASIFICACIÓN: {clasif.get('accion')} | Nivel {clasif.get('nivel')} | Destino {clasif.get('destino')}",
        f"PROBLEMA: {datos.get('sintoma', '')[:400]}",
        f"ALCANCE: {datos.get('geolocalizacion') or 'No especificado'}",
        f"DIAGNÓSTICO: {diag.get('diagnostico', '')}",
        f"MOTIVO ESCALAMIENTO: {clasif.get('motivo_escalamiento', '')}",
        f"DATOS: Línea {datos.get('linea')}, {datos.get('dispositivo')}, {datos.get('cooperativa')}",
    ]
    if clasif_dict.get("proveedor"):
        partes.append(f"PROVEEDOR: {clasif['proveedor']}")
    hechos = datos.get("hechos") or {}
    sms_ctx = []
    if hechos.get("sms_remitente_ejemplo"):
        sms_ctx.append(f"Remitente: {hechos['sms_remitente_ejemplo'][:200]}")
    if hechos.get("sms_horario_incidente"):
        sms_ctx.append(f"Horario: {hechos['sms_horario_incidente'][:200]}")
    if sms_ctx:
        partes.append("SMS/A2P: " + " | ".join(sms_ctx))
    pasos = hechos.get("pasos_realizados") or []
    if pasos:
        partes.append("ACCIONES N1: " + "; ".join(pasos[-6:]))
    if clasif.get("evidencia"):
        partes.append("EVIDENCIA: " + "; ".join(clasif["evidencia"]))
    return "\n".join(p for p in partes if p and not p.endswith(": "))
