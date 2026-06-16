"""Respuestas determinísticas — sin invocar IA cuando no hace falta."""

from __future__ import annotations

from app.domain.conversacion import EstadoConversacion
from app.domain.flujos_operativos import evaluar_flujo
from app.services.intenciones_seguimiento import construir_resumen, siguiente_paso_sugerido


def respuesta_por_estado(
    estado: EstadoConversacion,
    *,
    datos: dict,
    clasificacion: dict | None,
    diagnostico: dict | None,
    ticket: dict | None,
    paso_kb_idx: int = 0,
    ticket_existente: dict | None = None,
    hechos: dict | None = None,
    timeline: list[dict] | None = None,
    intencion_seguimiento: dict | None = None,
) -> str | None:
    """Retorna respuesta lista o None si conviene usar IA."""
    clasif = clasificacion or {}
    diag = diagnostico or {}
    accion = clasif.get("accion", "")
    hechos = hechos or {}
    ticket_ctx = ticket or ticket_existente
    tipo_seg = (intencion_seguimiento or {}).get("tipo", "")

    if intencion_seguimiento and intencion_seguimiento.get("aclaracion"):
        return str(intencion_seguimiento["aclaracion"])

    if accion == "estado_ticket" or tipo_seg == "estado_ticket":
        tid = (ticket_ctx or {}).get("id") or (intencion_seguimiento or {}).get("ticket_id")
        if tid:
            estado_ticket = (ticket_ctx or {}).get("estado") or "Abierto"
            nivel = (ticket_ctx or {}).get("nivel") or clasif.get("nivel") or ""
            sufijo_nivel = f" como {nivel}" if nivel else ""
            return (
                f"Sí, el ticket {tid} ya quedó registrado{sufijo_nivel} y está {estado_ticket}. "
                "Podés seguir trabajando el caso acá; las pruebas que confirmes quedan agregadas al historial."
            )
        if accion in ("crear_ticket_n1", "crear_ticket_n2") or clasif.get("crear_ticket"):
            nivel = clasif.get("nivel") or "N1"
            return (
                f"Todavía no quedó creado. El sistema ya determinó que corresponde registrar un ticket {nivel}; "
                "confirmame si el problema persiste y lo dejo cargado."
            )
        return (
            "Todavía no hay un ticket creado para este caso. "
            "Primero terminamos las verificaciones N1 o confirmamos persistencia para registrarlo con contexto."
        )

    if accion == "novedad_ticket" or tipo_seg == "novedad_ticket":
        tid = (ticket_ctx or {}).get("id") or (intencion_seguimiento or {}).get("ticket_id")
        if not tid:
            return "Todavía no hay un ticket vinculado a este caso."
        eventos = timeline or []
        if not eventos:
            return (
                f"El ticket {tid} sigue en estado {(ticket_ctx or {}).get('estado', 'Abierto')}. "
                "Por ahora no hay novedades nuevas en el timeline; el NOC aún no registró actualizaciones."
            )
        ultimos = eventos[-3:]
        lineas = [f"· {e.get('titulo', 'Actualización')}: {e.get('detalle', '')}" for e in ultimos]
        return (
            f"Novedades del ticket {tid} ({(ticket_ctx or {}).get('estado', 'Abierto')}):\n"
            + "\n".join(lineas)
        )

    if accion == "resumen_caso" or tipo_seg == "resumen_caso":
        return construir_resumen(hechos, datos, ticket_ctx)

    if accion == "cerrar_ticket" or tipo_seg == "cerrar_ticket":
        tid = (ticket_ctx or {}).get("id") or (intencion_seguimiento or {}).get("ticket_id")
        if tid:
            if (ticket_ctx or {}).get("estado") == "Cerrado":
                return f"El ticket {tid} ya figura cerrado. No hace falta otra acción."
            return (
                f"Listo. Cerré el ticket {tid} como resuelto y dejé la resolución registrada. "
                "El caso queda cerrado en consola."
            )
        return "Perfecto, cierro el caso como resuelto en N1. Si vuelve a aparecer, contame y lo retomamos."

    if accion == "correccion" or tipo_seg == "correccion":
        tid = (ticket_ctx or {}).get("id", "")
        flujo = evaluar_flujo(hechos, datos.get("sintoma", ""))
        if hechos.get("datos_ok") is False and tid and flujo.get("completado"):
            return (
                f"Tenés razón, me adelanté al cerrar. El cliente sigue con el inconveniente; "
                f"mantengo el ticket {tid} abierto para seguimiento NOC con las pruebas ya registradas."
            )
        paso = siguiente_paso_sugerido(hechos, datos.get("sintoma", ""))
        if paso:
            return (
                f"Tenés razón, no repito el paso anterior. "
                f"Siguiente acción concreta: {paso}"
            )
        return (
            "Tenés razón, me adelanté. Contame qué probó el cliente hasta ahora "
            "y te digo el siguiente paso concreto."
        )

    if accion == "agradecimiento" or tipo_seg == "agradecimiento":
        tid = (ticket_ctx or {}).get("id", "")
        if tid and hechos.get("datos_ok") is False:
            return (
                f"De nada. El ticket {tid} sigue abierto para seguimiento NOC; "
                "registré que el cliente aún reporta falla de datos."
            )
        if tid:
            return f"De nada. Seguimos con el ticket {tid} abierto por si surge alguna novedad."
        return "De nada. Seguimos atentos al caso."

    if accion == "recomendar_paso" or tipo_seg == "pregunta_recomendacion":
        paso = siguiente_paso_sugerido(hechos, datos.get("sintoma", ""))
        if paso:
            return f"Sí, para este caso te recomiendo: {paso} ¿Lo probamos con el cliente?"
        return (
            "Para avanzar sin adelantarnos: primero confirmemos qué ya se probó "
            "y después te digo el siguiente paso concreto."
        )

    if clasif.get("crear_ticket") and accion in ("crear_ticket_n1", "crear_ticket_n2"):
        return None

    if accion == "seguimiento_activo" or tipo_seg == "seguimiento_activo":
        tid = (ticket_ctx or {}).get("id", "")
        if hechos.get("resuelto"):
            if (ticket_ctx or {}).get("estado") == "Cerrado":
                return f"El caso ya quedó resuelto y el ticket {tid} está cerrado." if tid else "El caso ya quedó resuelto."
            extra = f" ¿Cerramos el ticket {tid}?" if tid else ""
            return f"Caso resuelto.{extra}"
        flujo = evaluar_flujo(hechos, datos.get("sintoma", ""))
        if flujo.get("paso_mensaje") and not flujo.get("completado"):
            return flujo["paso_mensaje"]
        paso = siguiente_paso_sugerido(hechos, datos.get("sintoma", ""))
        if paso and not hechos.get("datos_ok"):
            return paso
        if hechos.get("datos_ok") is True and hechos.get("resuelto") is not False:
            if (ticket_ctx or {}).get("estado") == "Cerrado":
                return f"El ticket {tid} ya está cerrado con la solución registrada." if tid else "La solución ya quedó registrada."
            return (
                f"Datos y llamadas quedaron OK; el caso parece resuelto."
                + (f" ¿Cerramos el ticket {tid}?" if tid else "")
            )
        if tid and flujo.get("completado"):
            return (
                f"Con las pruebas ya registradas, mantengo seguimiento del ticket {tid} en NOC. "
                "No sumo más pasos al cliente por ahora."
            )
        return "Registro el avance del caso. ¿Querés agregar alguna observación?"

    if estado == EstadoConversacion.RECOLECTANDO_DATOS:
        faltan = clasif.get("datos_faltantes") or []
        if "linea" in faltan:
            return "Entendido. Para avanzar necesito la línea completa del cliente. ¿Cuál es?"
        if "sintoma" in faltan:
            return "¿Podés contarme qué le está pasando al cliente? Un síntoma concreto alcanza."
        if not datos.get("dispositivo"):
            return f"Línea {datos.get('linea')} anotada. ¿Qué modelo de celular usa el cliente?"
        return "Gracias. ¿En qué zona ocurre y desde cuándo lo nota?"

    if estado == EstadoConversacion.GUIANDO_RESOLUCION and accion not in (
        "seguimiento_ticket",
        "seguimiento_activo",
        "novedad_ticket",
    ):
        flujo = evaluar_flujo(hechos, datos.get("sintoma", ""))
        if flujo.get("paso_mensaje") and not flujo.get("completado"):
            return flujo["paso_mensaje"]
        paso = siguiente_paso_sugerido(hechos, datos.get("sintoma", ""))
        if paso:
            return paso
        if ticket_ctx:
            return f"Continúo el seguimiento del ticket {ticket_ctx.get('id')} con lo que ya probamos."
        return "¿Qué probó el cliente hasta ahora?"

    if estado == EstadoConversacion.ESPERANDO_CONFIRMACION:
        if accion in ("crear_ticket_n1", "crear_ticket_n2"):
            nivel = clasif.get("nivel") or "N1"
            return (
                f"Con la información disponible voy a registrar un ticket {nivel}. "
                "¿Confirmás que el problema persiste y querés que lo deje cargado?"
            )
        return "¿El cliente sigue con el mismo inconveniente o ya quedó resuelto?"

    if ticket_existente and not ticket and accion not in ("seguimiento_activo", "novedad_ticket"):
        return (
            f"Esta línea ya tiene el ticket {ticket_existente.get('id')} abierto "
            f"({ticket_existente.get('estado')}). Podés seguir el caso desde seguimiento "
            "o confirmar si querés registrar una actualización."
        )

    if estado == EstadoConversacion.TICKET_CREADO and ticket:
        flujo = evaluar_flujo(hechos, datos.get("sintoma", ""))
        if accion in ("crear_ticket_n1", "crear_ticket_n2"):
            nivel = ticket.get("nivel") or clasif.get("nivel") or "N2"
            destino = ticket.get("destino") or clasif.get("destino") or "imowi_noc"
            return (
                f"Listo. Registré el ticket {ticket.get('id')} como {nivel} para {destino}. "
                "Quedó con las pruebas N1 en el historial para revisión del NOC."
            )
        if accion in ("seguimiento_activo", "novedad_ticket", "recomendar_paso", "correccion") or tipo_seg in (
            "seguimiento_activo",
            "novedad_ticket",
            "pregunta_recomendacion",
            "correccion",
        ):
            if flujo.get("paso_mensaje") and not flujo.get("completado"):
                return flujo["paso_mensaje"]
            paso = siguiente_paso_sugerido(hechos, datos.get("sintoma", ""))
            if paso:
                return paso
            return (
                f"El ticket {ticket.get('id')} sigue abierto. "
                "Registro las pruebas hechas y continúa el seguimiento NOC."
            )
        if flujo.get("paso_mensaje") and not flujo.get("completado"):
            return flujo["paso_mensaje"]
        paso = siguiente_paso_sugerido(hechos, datos.get("sintoma", ""))
        if paso:
            return paso
        if len((datos.get("hechos") or {}).get("pasos_realizados") or []) == 0:
            nivel = ticket.get("nivel") or clasif.get("nivel") or "N1"
            return (
                f"Listo. Registré el ticket {ticket.get('id')} como {nivel}. "
                "Vas a ver las novedades en seguimiento y notificaciones."
            )

    if estado == EstadoConversacion.CERRADO_RESUELTO:
        return "Perfecto, cierro el caso como resuelto. Si vuelve a aparecer, contame y lo retomamos."

    if accion == "pedir_datos":
        return respuesta_por_estado(
            EstadoConversacion.RECOLECTANDO_DATOS,
            datos=datos,
            clasificacion=clasificacion,
            diagnostico=diagnostico,
            ticket=ticket,
            paso_kb_idx=paso_kb_idx,
            hechos=hechos,
            intencion_seguimiento=intencion_seguimiento,
        )

    if accion == "resolver_n1" and estado != EstadoConversacion.TICKET_CREADO:
        return respuesta_por_estado(
            EstadoConversacion.GUIANDO_RESOLUCION,
            datos=datos,
            clasificacion=clasificacion,
            diagnostico=diagnostico,
            ticket=ticket,
            paso_kb_idx=paso_kb_idx,
            hechos=hechos,
            intencion_seguimiento=intencion_seguimiento,
        )

    return None
