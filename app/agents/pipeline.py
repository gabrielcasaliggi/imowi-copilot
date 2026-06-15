"""Pipeline multi-agente end-to-end."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents import diagnostico as ag_diag
from app.agents import orquestacion as ag_orch
from app.agents import triaje as ag_triaje
from app.estate import repository as repo
from app.services import clasificador
from app.domain.flujos_operativos import traza_flujo
from app.services.intenciones_seguimiento import construir_resumen
from app.services.motor_conversacional import ACCIONES_SEGUIMIENTO, procesar_turno_conversacional
from app.services.prefilter import analizar_relevancia
from app.services.seguimiento_ticket import _detectar_pasos_completados, registrar_avances_en_ticket, serializar_timeline
from app.services import piloto_metricas


def _historial_tecnico(historial: list[dict]) -> bool:
    for m in historial:
        if m.get("rol") != "usuario":
            continue
        r = analizar_relevancia(m.get("contenido", ""), False)
        if r.get("relevante"):
            return True
    return len(historial) > 2


def _cerrar_ticket_si_corresponde(
    db: Session,
    org_id: str,
    motor: dict,
    datos: dict,
    ticket_dict: dict | None,
    traces: list[str],
) -> tuple[dict | None, bool]:
    """Persiste cierre cuando el flujo conversacional resolvió un ticket existente."""
    if not ticket_dict or ticket_dict.get("estado") == "Cerrado":
        return ticket_dict, False

    tid = motor.get("cerrar_ticket_id") or ""
    if not tid and motor.get("estado_conversacion") == "caso_resuelto":
        tid = ticket_dict.get("id", "")
    if not tid:
        return ticket_dict, False

    hechos = datos.get("hechos") or motor.get("caso_conversacion", {}).get("datos_triaje", {}).get("hechos", {})
    resolucion = construir_resumen(hechos, datos, ticket_dict)
    ticket_obj = repo.update_ticket(
        db,
        org_id,
        tid,
        estado="Cerrado",
        resolucion_tecnica=resolucion[:2000],
        estado_sla="Cerrado",
    )
    if not ticket_obj:
        return ticket_dict, False

    traces.append(f"✅ [Motor]: Ticket {tid} cerrado por resolución del operador.")
    return _ticket_dict(ticket_obj), True


async def procesar_mensaje(
    db: Session,
    org_id: str,
    historial: list[dict],
    mensaje_usuario: str,
    *,
    creado_por: str = "",
    forzar_escalamiento: bool = False,
    admin_global: bool = False,
    session_id: str = "",
    usuario: str = "",
    accion_operador: str | None = None,
) -> dict:
    traces: list[str] = []
    hist = list(historial)

    pre = analizar_relevancia(mensaje_usuario, _historial_tecnico(hist))
    if not pre.get("relevante"):
        return _respuesta_vacia(pre)

    traces.append("🛡️ [Pre-LLM]: Consulta técnica — activando agentes…")

    hist_con_actual = hist + [{"rol": "usuario", "contenido": mensaje_usuario}]
    datos = ag_triaje.extraer_datos(hist_con_actual)
    caso_prev_snapshot = None
    if datos.get("linea"):
        caso_prev_snapshot = repo.get_caso_abierto_por_linea(db, org_id, datos["linea"])
    if not caso_prev_snapshot and session_id:
        caso_prev_snapshot = repo.get_caso_conversacion(db, org_id, session_id)
    hechos_prev_snapshot = (caso_prev_snapshot or {}).get("datos_triaje", {}).get("hechos", {})
    traces.append(
        f"⚙️ [Agente Triaje]: Extracción — línea={datos.get('linea') or 'pendiente'}, "
        f"equipo={datos.get('dispositivo') or 'pendiente'}"
    )

    diag = ag_diag.ejecutar_diagnostico(
        db, org_id, datos, mensaje_usuario, admin_global=admin_global
    )
    traces.extend(diag.pop("traces", []))

    alertas_red = diag.get("alertas_red") or []
    tickets_similares = diag.get("tickets_similares") or []
    ticket_existente = diag.get("ticket_abierto_existente")

    kb_resultado = diag.get("kb_resultado") or {}
    clasif = clasificador.clasificar_caso(
        datos,
        diag,
        kb_resultado,
        hist_con_actual,
        forzar_escalamiento=forzar_escalamiento,
    )
    clasif_dict = clasificador.resultado_a_dict(clasif)

    motor = procesar_turno_conversacional(
        db,
        org_id,
        session_id,
        usuario or creado_por,
        hist_con_actual,
        datos,
        clasif_dict,
        diag,
        ticket=None,
        accion_operador=accion_operador,
        ticket_existente=ticket_existente,
    )
    datos = (motor.get("caso_conversacion") or {}).get("datos_triaje") or datos

    if motor.get("linea_cambiada"):
        traces.append(
            f"💬 [Motor]: Cambio de línea detectado {motor['linea_cambiada']['anterior']} → "
            f"{motor['linea_cambiada']['nueva']}"
        )
        return _armar_respuesta(
            motor.get("respuesta_deterministica", ""),
            traces,
            diag,
            datos,
            motor,
            ticket=None,
            clasificacion=clasif_dict,
            alertas_red=alertas_red,
            tickets_similares=tickets_similares,
            ticket_existente=ticket_existente,
        )

    clasif_ajustada = motor["clasificacion_ajustada"]
    intencion_seg = motor.get("intencion_seguimiento") or {}
    crear_ticket_flag = bool(clasif_ajustada.get("crear_ticket"))
    if clasif_ajustada.get("accion") in ACCIONES_SEGUIMIENTO:
        crear_ticket_flag = False
    traces.append(
        f"💬 [Motor Conversacional]: estado={motor['estado_conversacion']} | "
        f"línea={motor.get('caso_conversacion', {}).get('linea_msisdn') or '-'} | "
        f"seguimiento={intencion_seg.get('tipo', '-')} | "
        f"IA={'sí' if motor['usar_ia'] else 'no'} | ticket={'sí' if crear_ticket_flag else 'pendiente'}"
    )
    hechos_flujo = datos.get("hechos") or {}
    traces.append(traza_flujo(hechos_flujo, datos.get("sintoma", "")))

    orch = ag_orch.ejecutar_orquestacion(
        db,
        org_id,
        datos,
        diag,
        hist_con_actual,
        forzar_escalamiento=forzar_escalamiento,
        creado_por=creado_por,
        crear_ticket=crear_ticket_flag,
        clasificacion_precalculada=clasif_ajustada,
    )
    traces.extend(orch.pop("traces", []))
    clasificacion = orch.get("clasificacion")

    ticket_obj = orch.get("ticket")
    ticket_nuevo = bool(ticket_obj and crear_ticket_flag)
    if not ticket_obj and ticket_existente and not clasif_ajustada.get("crear_ticket"):
        ticket_obj = repo.get_ticket(db, org_id, ticket_existente["id"])
    if not ticket_obj:
        caso_tid = (motor.get("caso_conversacion") or {}).get("ticket_id")
        if caso_tid:
            ticket_obj = repo.get_ticket(db, org_id, caso_tid)

    ticket_dict = _ticket_dict(ticket_obj) if ticket_obj else None

    ticket_dict, _ = _cerrar_ticket_si_corresponde(db, org_id, motor, datos, ticket_dict, traces)

    if ticket_dict and session_id:
        motor = procesar_turno_conversacional(
            db,
            org_id,
            session_id,
            usuario or creado_por,
            hist_con_actual,
            datos,
            clasif_ajustada,
            diag,
            ticket_dict,
            accion_operador=accion_operador,
            ticket_existente=ticket_existente,
        )
        ticket_dict, _ = _cerrar_ticket_si_corresponde(db, org_id, motor, datos, ticket_dict, traces)

    telemetria = repo.list_telemetry(db, org_id)
    ctx_red = "\n".join(
        f"{e.elemento_red}: {e.estado_actual} ({e.metrica}={e.valor_actual})"
        for e in telemetria[:8]
    )

    if motor.get("respuesta_deterministica"):
        respuesta = motor["respuesta_deterministica"]
        traces.append("💬 [Motor Conversacional]: Respuesta determinística (sin LLM).")
    elif motor.get("usar_ia"):
        flujo = motor.get("flujo_operativo") or {}
        kb_ctx = "" if flujo.get("paso_id") and not flujo.get("completado") else diag.get("kb_contexto", "")
        respuesta = await ag_triaje.generar_respuesta_chat(
            hist_con_actual,
            kb_ctx,
            ctx_red,
            diag,
            orch.get("acciones", []),
            clasificacion=clasificacion,
            estado_conversacion=motor.get("estado_conversacion"),
            caso_conversacion=motor.get("caso_conversacion"),
            ticket=ticket_dict,
            ticket_existente=ticket_existente,
            tickets_similares=tickets_similares,
            respuesta_sugerida=motor.get("respuesta_sugerida"),
            perfil_operador=motor.get("perfil_operador"),
        )
        traces.append("🤖 [Agente Triaje]: Respuesta generada con IA.")
    else:
        respuesta = motor.get("respuesta_sugerida") or (
            f"Registro el avance del ticket {ticket_dict.get('id')}."
            if ticket_dict
            else "Registro el avance del caso."
        )
        traces.append("💬 [Motor Conversacional]: Respuesta sin IA (seguimiento operativo).")

    ticket_timeline: list[dict] = []
    hechos_new = datos.get("hechos") or {}
    pasos_nuevos: list[str] = []
    if ticket_dict and ticket_dict.get("id"):
        pasos_nuevos = _detectar_pasos_completados(hechos_prev_snapshot, hechos_new)
        reg_traces, hechos_new = registrar_avances_en_ticket(
            db,
            org_id,
            ticket_dict["id"],
            hechos_prev=hechos_prev_snapshot,
            hechos_new=hechos_new,
            datos_triaje=datos,
            ultimo_operador=mensaje_usuario,
            actor=usuario or creado_por or "consola",
            flujo_operativo=motor.get("flujo_operativo"),
            ticket_nivel=ticket_dict.get("nivel", "N1"),
            ticket_estado=ticket_dict.get("estado", "Abierto"),
        )
        if reg_traces:
            traces.extend(reg_traces)
            datos = dict(datos)
            datos["hechos"] = hechos_new
            caso_id = motor.get("caso_id")
            if caso_id:
                repo.patch_caso_datos_triaje(db, org_id, caso_id, datos)
            ticket_obj = repo.get_ticket(db, org_id, ticket_dict["id"], admin_global=admin_global)
            if ticket_obj:
                ticket_dict = _ticket_dict(ticket_obj)
        ticket_timeline = serializar_timeline(db, org_id, ticket_dict["id"])
    elif session_id:
        pasos_nuevos = _detectar_pasos_completados(hechos_prev_snapshot, hechos_new)

    if session_id and (pasos_nuevos or ticket_nuevo):
            piloto_metricas.registrar_turno_piloto(
                db,
                org_id,
                session_id=session_id,
                actor=usuario or creado_por or "consola",
                pasos_nuevos=pasos_nuevos,
                flujo_operativo=motor.get("flujo_operativo"),
                ticket_id=(ticket_dict or {}).get("id", ""),
                ticket_nuevo=ticket_nuevo,
            )

    return _armar_respuesta(
        respuesta,
        traces,
        diag,
        datos,
        motor,
        ticket_dict,
        clasificacion,
        alertas_red=alertas_red,
        tickets_similares=tickets_similares,
        ticket_existente=ticket_existente,
        ticket_timeline=ticket_timeline,
    )


def _respuesta_vacia(pre: dict) -> dict:
    return {
        "respuesta": pre.get("respuesta_corta", ""),
        "relevante": False,
        "prefilter_motivo": pre.get("motivo"),
        "agent_traces": ["🛡️ [Pre-LLM]: Consulta filtrada — sin invocar LLM."],
        "informe_tecnico": {},
        "acciones_red": [],
        "ticket": None,
        "datos_triaje": {},
        "clasificacion": None,
        "estado_conversacion": None,
        "caso_conversacion": None,
        "usar_ia": False,
        "linea_cambiada": None,
        "tickets_similares": [],
        "ticket_existente": None,
        "alertas_red": [],
    }


def _armar_respuesta(
    respuesta: str,
    traces: list[str],
    diag: dict,
    datos: dict,
    motor: dict,
    ticket: dict | None,
    clasificacion: dict | None,
    *,
    alertas_red: list[dict],
    tickets_similares: list[dict],
    ticket_existente: dict | None,
    ticket_timeline: list[dict] | None = None,
) -> dict:
    return {
        "respuesta": respuesta,
        "relevante": True,
        "prefilter_motivo": "",
        "agent_traces": traces,
        "informe_tecnico": diag,
        "acciones_red": [],
        "ticket": ticket,
        "datos_triaje": datos,
        "ficha_jsc": diag.get("ficha_jsc"),
        "clasificacion": clasificacion,
        "estado_conversacion": motor.get("estado_conversacion"),
        "caso_conversacion": motor.get("caso_conversacion"),
        "usar_ia": motor.get("usar_ia", False),
        "linea_cambiada": motor.get("linea_cambiada"),
        "tickets_similares": tickets_similares,
        "ticket_existente": ticket_existente,
        "alertas_red": alertas_red,
        "intencion_pendiente": motor.get("intencion_pendiente"),
        "flujo_operativo": motor.get("flujo_operativo"),
        "ticket_timeline": ticket_timeline or [],
    }


def _ticket_dict(t) -> dict:
    return {
        "id": t.id,
        "linea": t.linea,
        "dispositivo": t.dispositivo,
        "descripcion_falla": t.descripcion_falla,
        "origen": t.origen,
        "estado": t.estado,
        "intent_ejecutado": t.intent_ejecutado,
        "categoria": t.categoria,
        "nivel": getattr(t, "nivel", "N1"),
        "destino": getattr(t, "destino", "cooperativa"),
        "proveedor": getattr(t, "proveedor", ""),
        "motivo_escalamiento": getattr(t, "motivo_escalamiento", ""),
        "evidencia": getattr(t, "evidencia", ""),
        "regla_clasificacion": getattr(t, "regla_clasificacion", ""),
        "estado_sla": getattr(t, "estado_sla", "Pendiente"),
    }
