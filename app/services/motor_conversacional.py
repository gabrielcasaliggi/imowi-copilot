"""Motor conversacional N1 — estados, persistencia por línea y decisión de cuándo usar IA."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.conversacion import (
    AccionOperador,
    EstadoConversacion,
    IntencionPendiente,
    PolaridadMensaje,
    clasificar_polaridad,
    interpretar_accion_operador,
    usuario_confirmo_resolucion,
    usuario_confirmo_ticket,
)
from app.domain.escalamiento import detectar_escalamiento
from app.estate import repository as repo
from app.services.intenciones_seguimiento import (
    _es_confirmacion_paso,
    _es_persistencia_post_paso,
    _es_respuesta_prueba_llamada,
    _ultimo_asistente,
    detectar_intencion_seguimiento,
    es_pregunta,
    extraer_hechos_conversacion,
)
from app.services.interprete_conversacional import (
    aplicar_interpretacion,
    interpretar_mensaje_estructurado,
    necesita_interpretacion_ia,
    perfil_operador,
)
from app.domain.flujos_operativos import evaluar_flujo, sintoma_cambio_categoria
from app.services.respuestas_conversacion import respuesta_por_estado

ACCIONES_SEGUIMIENTO = frozenset({
    "estado_ticket",
    "agradecimiento",
    "novedad_ticket",
    "resumen_caso",
    "cerrar_ticket",
    "correccion",
    "recomendar_paso",
    "seguimiento_activo",
    "caso_resuelto",
})

# Intenciones donde la IA redacta en tono natural pero respeta la respuesta sugerida.
ACCIONES_IA_CONVERSACIONAL = frozenset({
    "estado_ticket",
    "agradecimiento",
    "novedad_ticket",
    "resumen_caso",
    "correccion",
    "recomendar_paso",
})


def _ultimo_mensaje_operador(historial: list[dict]) -> str:
    for m in reversed(historial):
        if m.get("rol") == "usuario":
            return (m.get("contenido") or "").strip()
    return ""


def _es_respuesta_operativa_playbook(msg: str) -> bool:
    """Confirmaciones cortas del playbook N1 — sin redacción IA."""
    if not msg:
        return False
    if _es_confirmacion_paso(msg) or _es_persistencia_post_paso(msg) or _es_respuesta_prueba_llamada(msg):
        return True
    t = msg.lower()
    return any(
        p in t
        for p in (
            "no navega",
            "sin datos",
            "datos no",
            "habilitados",
            "habilitado",
            "no estaba activado",
            "roaming habilitado",
        )
    )


def detectar_linea_cambiada(
    caso_prev: dict | None,
    datos_triaje: dict,
    accion_operador: str | None,
) -> dict | None:
    """Detecta cambio de MSISDN dentro de la misma sesión UI."""
    if interpretar_accion_operador(accion_operador) == AccionOperador.NUEVO_RECLAMO:
        return None
    nueva = (datos_triaje.get("linea") or "").strip()
    if not nueva or not caso_prev:
        return None
    anterior = (caso_prev.get("linea_msisdn") or caso_prev.get("datos_triaje", {}).get("linea") or "").strip()
    if not anterior:
        return None
    import re

    if re.sub(r"\D", "", anterior) != re.sub(r"\D", "", nueva):
        return {"anterior": anterior, "nueva": nueva, "caso_id": caso_prev.get("id")}
    return None


def _resolver_caso_previo(
    db: Session,
    org_id: str,
    session_id: str,
    datos_triaje: dict,
) -> dict | None:
    linea = datos_triaje.get("linea") or ""
    if linea:
        caso_linea = repo.get_caso_abierto_por_linea(db, org_id, linea)
        if caso_linea:
            return caso_linea
    return repo.get_caso_conversacion(db, org_id, session_id)


def _intencion_pendiente_para_estado(estado: EstadoConversacion, clasificacion: dict) -> str:
    accion = clasificacion.get("accion", "")
    if estado == EstadoConversacion.ESPERANDO_CONFIRMACION:
        if accion in ("crear_ticket_n1", "crear_ticket_n2"):
            return IntencionPendiente.CONFIRMAR_TICKET.value
        return IntencionPendiente.CONFIRMAR_RESOLUCION.value
    if estado == EstadoConversacion.GUIANDO_RESOLUCION:
        return IntencionPendiente.CONTINUAR_KB.value
    return IntencionPendiente.NINGUNA.value


def _aplicar_intencion_seguimiento(
    clasificacion: dict,
    historial: list[dict],
    *,
    caso_prev: dict | None,
    ticket: dict | None,
    datos_triaje: dict,
) -> tuple[dict, dict, dict]:
    hechos_prev = (caso_prev or {}).get("datos_triaje", {}).get("hechos", {})
    sintoma_prev = (caso_prev or {}).get("datos_triaje", {}).get("sintoma", "")
    sintoma_nuevo = datos_triaje.get("sintoma", "")
    if sintoma_cambio_categoria(sintoma_prev, sintoma_nuevo):
        hechos_prev = {}
        hechos_prev.pop("categoria_flujo", None)
    hechos = extraer_hechos_conversacion(historial, hechos_prev)
    datos_triaje = dict(datos_triaje)
    datos_triaje["hechos"] = hechos

    intencion = detectar_intencion_seguimiento(
        historial,
        caso=caso_prev,
        ticket=ticket,
        hechos=hechos,
    )
    ultimo_msg = _ultimo_mensaje_operador(historial)
    ultimo_bot = _ultimo_asistente(historial)
    if necesita_interpretacion_ia(ultimo_msg, intencion, hechos, ultimo_bot=ultimo_bot):
        interp = interpretar_mensaje_estructurado(
            historial,
            ultimo_bot=ultimo_bot,
            hechos_prev=hechos,
        )
        if interp:
            hechos, intencion = aplicar_interpretacion(hechos, intencion, interp)
            datos_triaje["hechos"] = hechos

    out = dict(clasificacion)
    tipo = intencion.get("tipo", "continuar")
    ticket_id = (ticket or {}).get("id") or (caso_prev or {}).get("ticket_id") or ""

    if tipo == "estado_ticket":
        out.update({"accion": "estado_ticket", "crear_ticket": False})
    elif tipo == "agradecimiento":
        out.update({"accion": "agradecimiento", "crear_ticket": False})
    elif tipo == "novedad_ticket":
        out.update({"accion": "novedad_ticket", "crear_ticket": False})
    elif tipo == "resumen_caso":
        out.update({"accion": "resumen_caso", "crear_ticket": False})
    elif tipo in ("cerrar_ticket", "confirmar_cierre", "caso_resuelto"):
        out.update({"accion": "cerrar_ticket", "crear_ticket": False})
        intencion["cerrar"] = True
    elif tipo == "correccion":
        out.update({"accion": "correccion", "crear_ticket": False})
    elif tipo == "pregunta_recomendacion":
        out.update({"accion": "recomendar_paso", "crear_ticket": False})
    elif tipo in ("persistencia", "informe_prueba", "informe_alcance", "confirmacion_paso"):
        accion_seg = "seguimiento_activo" if ticket_id else "resolver_n1"
        out.update({"accion": accion_seg, "crear_ticket": False})
        if tipo == "persistencia":
            hechos["resuelto"] = False
            datos_triaje["hechos"] = hechos
    elif tipo == "seguimiento_activo" and ticket_id:
        out.update({"accion": "seguimiento_activo", "crear_ticket": False})
    elif (
        ticket_id
        and len(historial) > 2
        and out.get("accion") == "resolver_n1"
        and intencion.get("tipo") != "continuar"
    ):
        out.update({"accion": "seguimiento_activo", "crear_ticket": False})

    return out, datos_triaje, intencion


def _map_estado(
    clasificacion: dict,
    historial: list[dict],
    caso_prev: dict | None,
    accion_operador: str | None,
    intencion: str,
) -> EstadoConversacion:
    accion_op = interpretar_accion_operador(accion_operador)
    if accion_op == AccionOperador.CASO_RESUELTO:
        return EstadoConversacion.CERRADO_RESUELTO
    if accion_op == AccionOperador.CONFIRMAR_TICKET:
        return EstadoConversacion.ESPERANDO_CONFIRMACION

    accion = clasificacion.get("accion", "")
    if accion in ACCIONES_SEGUIMIENTO:
        if accion == "cerrar_ticket":
            return EstadoConversacion.CERRADO_RESUELTO
        if caso_prev and caso_prev.get("ticket_id"):
            return EstadoConversacion.TICKET_CREADO
        return EstadoConversacion.GUIANDO_RESOLUCION
    if usuario_confirmo_resolucion(historial, intencion) and accion == "resolver_n1":
        return EstadoConversacion.CERRADO_RESUELTO
    if accion == "pedir_datos":
        return EstadoConversacion.RECOLECTANDO_DATOS
    if accion == "resolver_n1":
        return EstadoConversacion.GUIANDO_RESOLUCION
    if accion in ("crear_ticket_n1", "crear_ticket_n2"):
        if clasificacion.get("regla_aplicada") in ("anomalia_red", "anomalia_red_correlacionada"):
            return EstadoConversacion.TICKET_CREADO
        return EstadoConversacion.ESPERANDO_CONFIRMACION
    if len(historial) <= 2:
        return EstadoConversacion.NUEVO_RECLAMO
    return EstadoConversacion.BUSCANDO_KB


def debe_usar_ia(
    estado: EstadoConversacion,
    clasificacion: dict,
    historial: list[dict],
    flujo_operativo: dict | None = None,
) -> bool:
    """Playbook N1 determinístico en confirmaciones; IA para preguntas y seguimiento libre."""
    accion = clasificacion.get("accion", "")
    ultimo = _ultimo_mensaje_operador(historial)
    flujo = flujo_operativo or {}
    flujo_activo = bool(flujo.get("paso_mensaje") and not flujo.get("completado"))

    if accion in ACCIONES_IA_CONVERSACIONAL:
        return True

    if estado == EstadoConversacion.CERRADO_RESUELTO:
        return False

    if accion == "pedir_datos":
        return False

    if flujo_activo and not es_pregunta(ultimo) and _es_respuesta_operativa_playbook(ultimo):
        return False

    if es_pregunta(ultimo):
        return True

    if estado in (
        EstadoConversacion.ESPERANDO_CONFIRMACION,
        EstadoConversacion.BUSCANDO_KB,
    ):
        return True

    if flujo_activo:
        return False

    if len(historial) <= 1 and not clasificacion.get("datos_faltantes"):
        return True

    if estado == EstadoConversacion.TICKET_CREADO and accion in (
        "seguimiento_activo",
        "crear_ticket_n1",
        "crear_ticket_n2",
    ):
        return True

    if estado == EstadoConversacion.GUIANDO_RESOLUCION and not flujo_activo:
        return True

    if detectar_escalamiento(historial):
        return False

    return False


def ajustar_clasificacion_por_estado(
    clasificacion: dict,
    caso: dict,
    historial: list[dict],
    *,
    accion_operador: str | None = None,
    ticket_existente: dict | None = None,
) -> dict:
    out = dict(clasificacion)
    estado = caso.get("estado", "")
    accion = out.get("accion", "")
    intencion = caso.get("intencion_pendiente", "")

    accion_op = interpretar_accion_operador(accion_operador)
    if accion_op == AccionOperador.CASO_RESUELTO:
        out["accion"] = "resolver_n1"
        out["crear_ticket"] = False
        return out
    if accion_op == AccionOperador.CONFIRMAR_TICKET:
        out["crear_ticket"] = True
        return out
    if accion_op == AccionOperador.CONTINUAR_KB:
        out["accion"] = "resolver_n1"
        out["crear_ticket"] = False
        return out

    if ticket_existente and accion in ("crear_ticket_n1", "crear_ticket_n2"):
        out["crear_ticket"] = False
        out["ticket_existente_id"] = ticket_existente.get("id")
        out["accion"] = "resolver_n1"
        return out

    if usuario_confirmo_resolucion(historial, intencion):
        out["accion"] = "resolver_n1"
        out["crear_ticket"] = False
        return out

    if estado == EstadoConversacion.GUIANDO_RESOLUCION.value and accion in (
        "crear_ticket_n1",
        "crear_ticket_n2",
    ):
        polaridad = clasificar_polaridad(historial, intencion)
        if polaridad != PolaridadMensaje.PERSISTENCIA and not detectar_escalamiento(historial):
            if not usuario_confirmo_ticket(historial, intencion):
                out["accion"] = "resolver_n1"
                out["crear_ticket"] = False
                return out

    if out.get("regla_aplicada") in ("anomalia_red", "anomalia_red_correlacionada"):
        out["crear_ticket"] = True
        return out

    if accion in ("crear_ticket_n1", "crear_ticket_n2"):
        polaridad = clasificar_polaridad(historial, intencion)
        out["crear_ticket"] = (
            detectar_escalamiento(historial)
            or usuario_confirmo_ticket(historial, intencion)
            or accion_op == AccionOperador.CONFIRMAR_TICKET
            or caso.get("kb_agotada", False)
            or polaridad == PolaridadMensaje.PERSISTENCIA
        )
    else:
        out["crear_ticket"] = False
    return out


def _debe_crear_ticket_por_persistencia(
    historial: list[dict],
    flujo_operativo: dict | None,
    hechos: dict,
    *,
    ticket: dict | None = None,
    ticket_existente: dict | None = None,
) -> bool:
    """Escala a NOC cuando el playbook N1 ya llegó al punto de seguimiento y persiste."""
    if ticket or ticket_existente:
        return False
    polaridad = clasificar_polaridad(historial, "")
    if polaridad != PolaridadMensaje.PERSISTENCIA and not detectar_escalamiento(historial):
        return False

    flujo = flujo_operativo or {}
    paso_id = flujo.get("paso_id", "")
    if flujo.get("completado"):
        return True
    if paso_id in {
        "roaming_cerrar_seguimiento",
        "datos_cerrar_seguimiento",
        "senal_ticket_noc",
        "senal_cerrar_seguimiento",
    }:
        return True

    # Fallback: si ya quedaron varias acciones N1 registradas y el usuario insiste,
    # no seguir cerrando en N1; preparar ticket para revisión NOC.
    pasos_realizados = hechos.get("pasos_realizados") or []
    return len(pasos_realizados) >= 4 and hechos.get("resuelto") is False


def procesar_turno_conversacional(
    db: Session,
    org_id: str,
    session_id: str,
    usuario: str,
    historial: list[dict],
    datos_triaje: dict,
    clasificacion: dict,
    diagnostico: dict,
    ticket: dict | None,
    *,
    accion_operador: str | None = None,
    ticket_existente: dict | None = None,
) -> dict:
    caso_prev = _resolver_caso_previo(db, org_id, session_id, datos_triaje)
    linea_cambiada = detectar_linea_cambiada(caso_prev, datos_triaje, accion_operador)

    if linea_cambiada and interpretar_accion_operador(accion_operador) != AccionOperador.NUEVO_RECLAMO:
        return {
            "estado_conversacion": caso_prev.get("estado") if caso_prev else "nuevo_reclamo",
            "caso_conversacion": caso_prev,
            "linea_cambiada": linea_cambiada,
            "usar_ia": False,
            "respuesta_deterministica": (
                f"Detecté otra línea ({linea_cambiada['nueva']}). "
                f"El caso activo es {linea_cambiada['anterior']}. "
                "Iniciá un nuevo reclamo para atender a este cliente sin mezclar historias."
            ),
            "clasificacion_ajustada": dict(clasificacion, crear_ticket=False),
            "caso_id": caso_prev.get("id") if caso_prev else None,
            "paso_kb_idx": (caso_prev or {}).get("paso_kb_idx", 0),
            "kb_agotada": (caso_prev or {}).get("kb_agotada", False),
            "intencion_pendiente": "",
        }

    forzar_nuevo = interpretar_accion_operador(accion_operador) == AccionOperador.NUEVO_RECLAMO
    if forzar_nuevo:
        caso_prev = None

    if not ticket and caso_prev and caso_prev.get("ticket_id"):
        row = repo.get_ticket(db, org_id, caso_prev["ticket_id"])
        if row:
            ticket = repo._ticket_resumen(row)

    clasificacion, datos_triaje, intencion_seg = _aplicar_intencion_seguimiento(
        clasificacion,
        historial,
        caso_prev=caso_prev,
        ticket=ticket,
        datos_triaje=datos_triaje,
    )
    flujo_operativo = evaluar_flujo(
        datos_triaje.get("hechos") or {},
        datos_triaje.get("sintoma", ""),
    )
    if flujo_operativo.get("paso_id"):
        datos_triaje.setdefault("hechos", {})["paso_flujo_id"] = flujo_operativo["paso_id"]

    intencion_prev = (caso_prev or {}).get("intencion_pendiente", "")
    estado = _map_estado(clasificacion, historial, caso_prev, accion_operador, intencion_prev)
    intencion = _intencion_pendiente_para_estado(estado, clasificacion)

    paso_kb_idx = (caso_prev or {}).get("paso_kb_idx", 0)
    if estado == EstadoConversacion.GUIANDO_RESOLUCION:
        polaridad = clasificar_polaridad(historial, intencion)
        if polaridad in (PolaridadMensaje.PERSISTENCIA, PolaridadMensaje.NEGACION) or detectar_escalamiento(historial):
            paso_kb_idx += 1

    pasos = clasificacion.get("pasos_n1") or []
    kb_agotada = paso_kb_idx >= len(pasos) and paso_kb_idx > 0 if pasos else paso_kb_idx > 0

    ticket_id = ticket.get("id") if ticket else (caso_prev or {}).get("ticket_id", "")
    if ticket_existente and not ticket:
        ticket_id = ticket_existente.get("id", ticket_id)

    if ticket:
        estado = EstadoConversacion.TICKET_CREADO
        ticket_id = ticket.get("id", "")
    elif ticket_existente and not clasificacion.get("crear_ticket"):
        estado = EstadoConversacion.TICKET_CREADO
        ticket_id = ticket_existente.get("id", "")

    if estado == EstadoConversacion.CERRADO_RESUELTO:
        ticket_id = ""

    caso = repo.upsert_caso_conversacion(
        db,
        org_id,
        session_id,
        usuario=usuario,
        estado=estado.value,
        datos_triaje=datos_triaje,
        clasificacion=clasificacion,
        paso_kb_idx=paso_kb_idx,
        kb_agotada=kb_agotada,
        ticket_id=ticket_id,
        linea_msisdn=datos_triaje.get("linea") or "",
        intencion_pendiente=intencion,
        caso_id=None if forzar_nuevo else (caso_prev or {}).get("id"),
        forzar_nuevo=forzar_nuevo,
    )

    clasif_ajustada = ajustar_clasificacion_por_estado(
        clasificacion,
        caso,
        historial,
        accion_operador=accion_operador,
        ticket_existente=ticket_existente,
    )
    if clasif_ajustada.get("accion") in ACCIONES_SEGUIMIENTO:
        clasif_ajustada["crear_ticket"] = False
    if _debe_crear_ticket_por_persistencia(
        historial,
        flujo_operativo,
        datos_triaje.get("hechos") or {},
        ticket=ticket,
        ticket_existente=ticket_existente,
    ):
        clasif_ajustada.update(
            {
                "accion": "crear_ticket_n2",
                "crear_ticket": True,
                "nivel": "N2",
                "destino": "imowi_noc",
                "proveedor": "imowi NOC",
                "regla_aplicada": "persistencia_post_n1",
                "motivo_escalamiento": (
                    "El inconveniente persiste después de las verificaciones N1; "
                    "requiere revisión del NOC."
                ),
            }
        )
        estado = EstadoConversacion.ESPERANDO_CONFIRMACION
    usar_ia = debe_usar_ia(estado, clasif_ajustada, historial, flujo_operativo)

    ticket_resp = ticket or ticket_existente
    timeline: list[dict] = []
    if ticket_resp and ticket_resp.get("id"):
        timeline = [
            {
                "titulo": e.titulo,
                "detalle": e.detalle,
                "estado": e.estado,
                "created_at": e.created_at.isoformat() if e.created_at else "",
            }
            for e in repo.list_ticket_events(db, org_id, ticket_resp["id"])
        ]

    respuesta_det = respuesta_por_estado(
        estado,
        datos=datos_triaje,
        clasificacion=clasif_ajustada,
        diagnostico=diagnostico,
        ticket=ticket_resp,
        paso_kb_idx=paso_kb_idx,
        ticket_existente=ticket_existente,
        hechos=datos_triaje.get("hechos"),
        timeline=timeline,
        intencion_seguimiento=intencion_seg,
    )
    if not usar_ia and not respuesta_det:
        tid = (ticket_resp or {}).get("id", "")
        respuesta_det = (
            f"Registro el avance del ticket {tid}."
            if tid
            else "Registro el avance del caso."
        )

    cerrar_ticket_id = ""
    if intencion_seg.get("cerrar") and ticket_resp:
        cerrar_ticket_id = ticket_resp.get("id", "")

    return {
        "estado_conversacion": estado.value,
        "caso_conversacion": caso,
        "caso_id": caso.get("id"),
        "paso_kb_idx": paso_kb_idx,
        "kb_agotada": kb_agotada,
        "intencion_pendiente": intencion,
        "usar_ia": usar_ia,
        "respuesta_sugerida": respuesta_det,
        "respuesta_deterministica": respuesta_det if not usar_ia else None,
        "clasificacion_ajustada": clasif_ajustada,
        "intencion_seguimiento": intencion_seg,
        "cerrar_ticket_id": cerrar_ticket_id,
        "linea_cambiada": None,
        "flujo_operativo": flujo_operativo,
        "perfil_operador": perfil_operador(historial),
    }
