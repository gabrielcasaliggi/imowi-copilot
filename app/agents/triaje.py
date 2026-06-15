"""Agente 1 — Triaje y canales de entrada (interacción empática + extracción invisible)."""

from __future__ import annotations

import re

from app.llm import chat_completion

_MARCAS = ("samsung", "iphone", "motorola", "xiaomi", "huawei", "redmi", "pixel", "nokia")


def extraer_datos(historial: list[dict]) -> dict:
    texto_u = " ".join(m["contenido"] for m in historial if m.get("rol") == "usuario")
    t = texto_u.lower()

    linea = ""
    for m in reversed([x for x in historial if x.get("rol") == "usuario"]):
        texto = m["contenido"]
        lm = re.search(
            r"(?:l[ií]nea|linea|tel[eé]fono|celular|n[uú]mero)\s*[:\s]*(\d{10,11})",
            texto,
            re.I,
        )
        if lm:
            linea = lm.group(1)
            break
        nums = re.findall(r"(?<!\d)(\d{10,11})(?!\d)", texto)
        if nums:
            linea = nums[-1]
            break

    coop = ""
    m = re.search(r"coop(?:erativa)?\s*([a-záéíóúñ0-9]+)", t, re.I)
    if m:
        coop = f"Coop {m.group(1).title()}"
    elif "batan" in t or "batán" in t:
        coop = "Coop Batán"
    elif "viamonte" in t:
        coop = "Coop Viamonte"

    dispositivo = ""
    dm = re.search(r"(samsung\s*a?\d+\w*|iphone\s*\d+\w*|motorola\s*\w+)", t, re.I)
    if dm:
        dispositivo = dm.group(1).title()
    else:
        for marca in _MARCAS:
            if marca in t:
                dispositivo = marca.title()
                break

    geo = ""
    for z in ("brasil", "güemes", "guemes", "mar del plata", "buenos aires"):
        if z in t:
            geo = z.title()
            break

    sintoma_caso = ""
    for u in historial:
        if u.get("rol") != "usuario":
            continue
        contenido = (u.get("contenido") or "").strip()
        if len(contenido) > 10:
            sintoma_caso = contenido[:500]
            break

    sintoma_ultimo = ""
    for u in reversed(historial):
        if u.get("rol") != "usuario":
            continue
        contenido = (u.get("contenido") or "").strip()
        if len(contenido) > 3:
            sintoma_ultimo = contenido[:500]
            break

    # Mantener síntoma del reclamo (primer mensaje sustantivo) salvo que mensajes
    # posteriores aporten categoría técnica (ej. roaming en Uruguay tras un "problema con la línea").
    sintoma = sintoma_caso or sintoma_ultimo
    from app.domain.flujos_operativos import detectar_categoria_flujo

    if sintoma_caso and detectar_categoria_flujo(sintoma_caso, {}) == "general":
        texto_flujo = texto_u[:800]
        if detectar_categoria_flujo(texto_flujo, {}) != "general":
            sintoma = texto_flujo
        elif len(texto_u) > len(sintoma_caso) + 15:
            sintoma = texto_flujo

    return {
        "cooperativa": coop,
        "linea": linea,
        "dispositivo": dispositivo,
        "geolocalizacion": geo,
        "sintoma": sintoma,
        "completo": bool(linea and dispositivo and sintoma),
    }


async def generar_respuesta_chat(
    historial: list[dict],
    contexto_kb: str,
    contexto_red: str,
    informe_agente2: dict,
    acciones_agente3: list[dict],
    clasificacion: dict | None = None,
    estado_conversacion: str | None = None,
    caso_conversacion: dict | None = None,
    ticket: dict | None = None,
    ticket_existente: dict | None = None,
    tickets_similares: list[dict] | None = None,
    respuesta_sugerida: str | None = None,
    perfil_operador: str | None = None,
) -> str:
    from app.services.interprete_conversacional import perfil_operador as _detectar_perfil

    perfil = perfil_operador or _detectar_perfil(historial)
    tono = (
        "Usá términos técnicos directos (APN, JSC, roaming, NOC, registro en red)."
        if perfil == "tecnico"
        else (
            "Explicá en lenguaje simple para operador no técnico; evitá siglas sin traducir."
            if perfil == "informal"
            else "Adaptá el vocabulario al operador: claro, directo, sin exceso de jerga."
        )
    )
    sys = (
        "Sos el Agente de Triaje del NOC (imowi / cooperativa). "
        "Tono: profesional, directo, español rioplatense. "
        f"{tono} "
        "Evitá muletillas y arranques repetidos: no empieces con 'Entiendo que', "
        "'Me parece que estamos avanzando', 'Para seguir adelante' ni variantes salvo que sea imprescindible. "
        "No repitas en dos turnos seguidos el mismo resumen ni la misma pregunta. "
        "Si el operador responde 'sí', 'ok' o confirma algo, avanzá al siguiente estado en una frase corta. "
        "Una sola pregunta por turno si falta un dato. No repitas lo que el operador ya dijo. "
        "No inventes líneas, equipos, tickets ni novedades. Si hay anomalía de red, mencionalo con calma. "
        "Si la línea no aparece en JSC, no frenes el triaje: seguí el flujo técnico y dejá la validación como advertencia operativa. "
        "No pidas DNI, número privado, IMEI, ICCID ni datos administrativos si no aparecen explícitamente en el caso o en la respuesta sugerida. "
        "La KB documental son conversaciones y documentos históricos: usala como contexto, no como verdad operativa actual. "
        "La telemetría/anomalías y los tickets son estado operativo vigente. "
        "No recomiendes cambio de SIM como primer paso: es invasivo para el cliente. "
        "Para datos/navegación priorizá APN, datos móviles activos, modo avión/reinicio y verificación de llamadas. "
        "Para roaming seguí solo este orden: itinerancia/datos activos, APN, habilitación roaming en JSC, reinicio o modo avión, prueba de registro/llamada. "
        "Solo sugerí SIM si el síntoma apunta a SIM/eSIM/chip o ya se agotaron verificaciones simples. "
        "Si el operador pregunta por novedades de un ticket, respondé desde el ticket activo/existente y no propongas un paso de KB. "
        "Si el operador pregunta si se creó el ticket, confirmá el ID y estado con claridad. "
        "Si el cliente sigue con problemas, no propongas cerrar el caso ni digas que datos/llamadas están OK. "
        "La RESPUESTA SUGERIDA POR REGLAS es la fuente de verdad operativa: conservá sus datos (ticket, nivel, pasos) y solo mejorá el tono. "
        "Respondé primero lo que el operador preguntó en este turno, en forma directa y humana. "
        "No ofrezcas crear ticket hasta que el operador confirme que persiste el problema, salvo que la clasificación ya lo haya creado. "
        f"Estado del caso: {estado_conversacion or 'en curso'}. "
        "Respetá la clasificación operativa: si es resolver_n1, guiá pasos; "
        "si es pedir_datos, pedí solo lo que falta; si generó ticket N1 o N2, informá con claridad. "
        "Podés mejorar la redacción de la respuesta sugerida, pero no contradigas sus decisiones."
    )
    user = (
        f"HISTORIAL:\n{_fmt_hist(historial)}\n\n"
        f"RESPUESTA SUGERIDA POR REGLAS:\n{respuesta_sugerida or ''}\n\n"
        f"CASO ACTIVO:\n{caso_conversacion or {}}\n\n"
        f"TICKET ACTIVO O CREADO:\n{ticket or {}}\n\n"
        f"TICKET EXISTENTE:\n{ticket_existente or {}}\n\n"
        f"TICKETS SIMILARES:\n{(tickets_similares or [])[:5]}\n\n"
        f"KB DOCUMENTAL / RAG:\n{contexto_kb[:2200]}\n\n"
        f"BASE OPERATIVA DE ANOMALÍAS:\n{contexto_red[:1200]}\n\n"
        f"DIAGNÓSTICO AGENTE 2:\n{informe_agente2}\n\n"
        f"CLASIFICACIÓN:\n{clasificacion or {}}\n\n"
        f"ACCIONES AGENTE 3:\n{acciones_agente3}\n\n"
        "Respondé al operador en 1-2 oraciones. Si ya hubo varias idas y vueltas, sé más breve."
    )
    try:
        respuesta = chat_completion(
            [{"role": "system", "content": sys}, {"role": "user", "content": user}],
            temperature=0.25,
        )
        return _limpiar_respuesta_repetitiva(historial, respuesta)
    except Exception:
        return _respuesta_fallback(
            historial,
            informe_agente2,
            acciones_agente3,
            clasificacion,
            ticket=ticket,
            ticket_existente=ticket_existente,
            respuesta_sugerida=respuesta_sugerida,
        )


def _fmt_hist(historial: list[dict]) -> str:
    return "\n".join(
        f"{'OP' if m.get('rol') == 'usuario' else 'BOT'}: {m.get('contenido', '')}"
        for m in historial[-12:]
    )


_MULETILLAS_INICIO = (
    "entiendo que ",
    "entiendo, ",
    "dado que ya se han realizado varias pruebas y el problema de roaming persiste, ",
    "dado que ya verificaste los datos móviles y el apn, ",
    "me parece que estamos avanzando en la resolución del problema. ",
    "para seguir avanzando en la resolución del problema, ",
    "para seguir adelante, ",
    "ahora, para seguir avanzando en la resolución del problema, ",
)


def _normalizar_para_comparar(texto: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", texto.lower())).strip()


def _limpiar_respuesta_repetitiva(historial: list[dict], respuesta: str) -> str:
    r = (respuesta or "").strip()
    if not r:
        return r

    for muletilla in _MULETILLAS_INICIO:
        if r.lower().startswith(muletilla):
            r = r[len(muletilla):].lstrip()
            if r:
                r = r[0].upper() + r[1:]
            break

    respuestas_previas = [
        m.get("contenido", "")
        for m in historial[-6:]
        if m.get("rol") == "asistente" and m.get("contenido")
    ]
    actual_norm = _normalizar_para_comparar(r)
    for previa in respuestas_previas[-2:]:
        previa_norm = _normalizar_para_comparar(previa)
        if actual_norm and previa_norm and (
            actual_norm == previa_norm or actual_norm[:120] == previa_norm[:120]
        ):
            return "Ya quedó registrado. ¿Avanzamos con el cierre o necesitás agregar algo más?"

    oraciones = re.split(r"(?<=[.!?])\s+", r)
    filtradas: list[str] = []
    vistas: set[str] = set()
    for oracion in oraciones:
        clave = _normalizar_para_comparar(oracion)
        if not clave or clave in vistas:
            continue
        vistas.add(clave)
        filtradas.append(oracion)
    return " ".join(filtradas[:3]).strip()


def _respuesta_fallback(
    historial: list[dict],
    informe: dict,
    acciones: list,
    clasificacion: dict | None = None,
    *,
    ticket: dict | None = None,
    ticket_existente: dict | None = None,
    respuesta_sugerida: str | None = None,
) -> str:
    ultimo = ""
    for m in reversed(historial):
        if m.get("rol") == "usuario":
            ultimo = (m.get("contenido") or "").lower()
            break
    ticket_ctx = ticket or ticket_existente
    if ticket_ctx and any(p in ultimo for p in ("novedad", "seguimiento", "estado", "ticket")):
        return (
            f"El ticket {ticket_ctx.get('id')} está en estado {ticket_ctx.get('estado', 'abierto')}. "
            "Por ahora no tengo una actualización nueva en el timeline; si querés, puedo registrar una nota de seguimiento."
        )
    if respuesta_sugerida:
        return respuesta_sugerida
    datos = extraer_datos(historial)
    if clasificacion and clasificacion.get("accion") == "pedir_datos":
        faltan = clasificacion.get("datos_faltantes", [])
        if "linea" in faltan:
            return "Entendido. ¿Cuál es la línea completa del cliente?"
        if "sintoma" in faltan:
            return "¿Podés describir el síntoma o inconveniente que reporta el cliente?"
    if not datos["linea"]:
        return "Entendido. ¿Cuál es la línea completa del cliente?"
    if not datos["dispositivo"]:
        return f"Línea {datos['linea']} registrada. ¿Qué modelo de celular usa el cliente?"
    if clasificacion and clasificacion.get("accion") == "resolver_n1" and clasificacion.get("pasos_n1"):
        return f"Seguimos con resolución N1: {clasificacion['pasos_n1'][0]}. ¿El cliente ya probó eso?"
    if clasificacion and clasificacion.get("accion") in ("crear_ticket_n1", "crear_ticket_n2"):
        nivel = clasificacion.get("nivel") or "N1"
        destino = clasificacion.get("destino") or "cooperativa"
        proveedor = clasificacion.get("proveedor")
        extra = f" con referencia a {proveedor}" if proveedor else ""
        return f"Con los datos disponibles no lo puedo cerrar desde la KB. Generé un ticket {nivel} para {destino}{extra} y dejé la evidencia registrada."
    if informe.get("anomalia_red"):
        return (
            f"Detectamos posible incidencia en {informe.get('elemento_afectado', 'red')}. "
            f"Seguimos con el procedimiento del manual. ¿El cliente sigue sin servicio?"
        )
    if acciones:
        a = acciones[0]
        return f"{a.get('descripcion', 'Acción NOC registrada.')} ¿Necesitás agregar algo más?"
    return "Recibí los datos. Seguimos con el troubleshooting según el manual de la cooperativa."
