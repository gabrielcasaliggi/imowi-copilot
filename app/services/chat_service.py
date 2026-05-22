"""Lógica de chat con decisión autónoma del LLM + RAG Markdown."""

from __future__ import annotations

from app.knowledge import (
    buscar_contexto,
    formatear_contexto_para_prompt,
    formatear_modo_escalamiento,
)
from app.llm import chat_completion
from app.models import ChatInput, ChatResponse, MensajeHistorial

SYSTEM_PROMPT_BASE = """
Sos el Copilot de soporte técnico del NOC de imowi para operadores de cooperativas.

TONO: profesional, resolutivo y conciso — español rioplatense de soporte técnico.

MISIÓN: capturar datos objetivos (Cooperativa/cliente, Línea, Dispositivo, Falla técnica) para que el NOC resuelva el reclamo con rapidez.

─── INFERENCIA INTELIGENTE (NO ASUMIR) ───
- Distinguí siempre: (A) DISPOSITIVO del abonado = marca/modelo del teléfono que USA el cliente; (B) ORIGEN/SERVICIO del problema = de dónde vienen los mensajes, la app o el proveedor (Apple, iMessage, WhatsApp, Google, etc.).
- Si el operador dice "no recibe mensajes de Apple", "SMS de Apple", "iMessage" o similar → eso describe la FALLA u origen, NO que el teléfono sea iPhone/Apple.
- PROHIBIDO deducir el dispositivo a partir de Apple/Google/WhatsApp en la falla. Ejemplo incorrecto: falla con "mensajes de Apple" → preguntar por iPhone. Correcto: preguntar neutro "¿Qué modelo de celular usa el cliente?" solo si aún no lo dijo.
- Si el operador ya describió el síntoma en un mensaje anterior, NO lo pidas de nuevo; reconocelo y pedí solo el dato que falte.
- Si el operador corrige un dato (ej. "no, es Samsung"), aceptá la corrección sin discutir ni volver a asumir Apple.
- Preguntá con sentido común: primero lo que falta según prioridad (cooperativa → línea → dispositivo → acciones ya hechas), no lo que ya está en el historial.

─── COMPORTAMIENTO ELÁSTICO PERO SEGURO ───
- Si el reclamo NO está cubierto explícitamente por la base de conocimiento, guiá con calma: el caso se escalará al equipo NOC.
- Mantené siempre la higiene estricta: no des por cerrado el relevamiento sin Cooperativa/cliente, Línea, Dispositivo y Falla técnica claros.
- La KB es solo referencia de enfoque o pasos genéricos; PROHIBIDO copiar de ahí línea, modelo, proveedor, URLs u otros datos de casos ajenos.

─── LÍNEAS TELEFÓNICAS (ARGENTINA) ───
- Aceptá la cadena numérica COMPLETA que indique el operador (con o sin 0, 15, 9 o prefijo de área).
- Ejemplos válidos: 2235402690, 1155551234, 2214567890 — suelen tener 10 u 11 dígitos; respetá la longitud que el operador proporcionó.
- PROHIBIDO: truncar, “corregir”, acortar o validar por longitud fija basándote en códigos de área (223, 11, 351, etc.). Que el número empiece con 223 NO significa que la línea tenga 3 dígitos.
- Al resumir, repetí la línea exactamente como la confirmó el operador (solo dígitos, sin inventar ni omitir).

─── IDs DE TICKET (METADATO INTERNO — NO PARA EL CHAT) ───
- PROHIBIDO inventar, anticipar o mencionar en el diálogo identificadores de ticket (JSC-xxxx, “ticket 1001”, números de caso internos, etc.).
- El sistema registra el caso y muestra el ID en los paneles; vos no cites códigos internos.
- “Quedó registrado para el NOC” solo cuando el caso se escala (sin KB o pasos agotados). En resolución asistida con KB, aún no hay ticket.
- No digas “quedó en JSC-…”, ni cites códigos internos aunque aparezcan en contexto del sistema.

─── CONDUCTA GENERAL ───
1. Lo que el operador dice es LA VERDAD; no lo contradigas ni lo sustituyas por el historial o la KB.
2. Preguntas breves y cerradas solo por lo que FALTE: cooperativa, línea, dispositivo, síntoma/falla, alcance/zona, acciones ya realizadas.
3. Revisá todo el historial; no repitas preguntas ya respondidas ni el saludo inicial del sistema.
4. Con datos completos: resumen operativo corto (problema, alcance, qué ya probó). Sin párrafos largos.
5. “no” o “gracias” solos NO implican problema resuelto; cerrá solo si dicen explícitamente ok / listo / resuelto / confirmado.
6. PROHIBIDO en un solo mensaje volcar un cuestionario completo (cooperativa + línea + dispositivo + falla juntos). Una pregunta por turno.
"""

PROMPT_PRIMER_TURNO = """
FASE ACTUAL: PRIMER MENSAJE DEL OPERADOR (caso nuevo).
- El operador ya vio el saludo inicial del Copilot; NO repitas saludo largo ni digas "Hola de nuevo".
- NO listés todas las preguntas juntas. Máximo 2-3 oraciones.
- Si su mensaje ya trae datos, reconocelos brevemente y pedí SOLO el primer dato que falte (prioridad: cooperativa → línea completa → dispositivo → síntoma/falla).
- Si es vago ("tengo un problema"), invitá a contar el reclamo en una o dos líneas; después preguntá de a un dato.
- No menciones IDs de ticket.
"""

PROMPT_RETOMO_CASO = """
FASE ACTUAL: RETOMO DE CASO YA REGISTRADO.
- Podés saludar breve con "Hola de nuevo" si corresponde.
- NO pidas de nuevo datos que ya están en el mensaje de retomo ni en DATOS YA PROVISTOS.
- Ofrecé agregar información o confirmar si quedó resuelto (OK/listo).
- No menciones IDs de ticket en el chat.
"""

PROMPT_TURNO_SIGUIENTE = """
FASE ACTUAL: CONVERSACIÓN EN CURSO.
- Seguí pidiendo de a UN solo dato faltante por mensaje.
- No repitas el saludo ni el cuestionario inicial.
- Si la falla ya está clara (ej. no recibe SMS de Apple en Samsung), NO preguntes de nuevo el síntoma; pedí dispositivo solo si no lo dijeron, con pregunta NEUTRA (marca/modelo), sin asumir iPhone por mencionar Apple.
- No asumas marca del teléfono por palabras Apple/Google/WhatsApp en la descripción del problema.
"""

PROMPT_RESOLUCION_KB = """
═══ MODO RESOLUCIÓN ASISTIDA (hay caso similar en KB — ver abajo) ═══
PRIORIDAD: intentar RESOLVER con el operador ANTES de ticket al NOC.

1. Con los datos del reclamo (cooperativa, línea, dispositivo, falla), decile al operador que encontraste un caso parecido
   y que van a seguir el procedimiento del manual (sin citar IDs ni copiar datos de otro cliente).
2. Guiá paso a paso usando "Pasos de verificación" y "Pasos de resolución" del bloque KB, adaptados a ESTE cliente.
3. Después de cada paso, preguntá si el operador pudo aplicarlo y qué resultado obtuvo.
4. Mientras estés en resolución asistida: PROHIBIDO decir "quedó registrado", "registrado para el NOC",
   "se generó el ticket" o similar. Aún no hay ticket hasta que escales.
5. Cuando tengas los 4 datos, anunciá que hay un caso similar en el manual y empezá el PRIMER paso
   de verificación/resolución (uno por mensaje). Ej: "Encontré un caso parecido. Primero: [paso 1]. ¿Pudieron hacerlo?"
6. Si el operador confirma resolución (ok, listo, funciona): felicitá; no hace falta ticket.
7. Si hay que escalar (pasos fallaron o lo pide): explicá por qué y recién ahí decí que se registrará para el NOC.
- NO copies línea, modelo ni proveedor del caso viejo de la KB.
"""

PROMPT_ESCALAMIENTO = """
Sin procedimiento claro en la KB — el caso se escalará al NOC. Guiá con calma al operador.
- Pedí solo lo faltante con higiene estricta: cooperativa, línea (cadena completa), dispositivo, falla técnica, alcance y acciones ya realizadas.
- Hechos verificados por el operador; sin suposiciones ni datos de la KB.
- Con datos completos: confirmá recepción para el NOC (sin IDs internos) y resumí en 3-4 líneas objetivas.
"""


def _texto_consulta(data: ChatInput) -> str:
    partes: list[str] = []
    for m in data.historial:
        if m.rol == "usuario":
            partes.append(m.contenido)
    if data.mensaje_usuario:
        partes.append(data.mensaje_usuario)
    return "\n".join(partes) if partes else ""


def _es_retomo_caso(historial: list[MensajeHistorial]) -> bool:
    for m in historial:
        if m.rol == "asistente" and m.contenido.strip().lower().startswith("retomás"):
            return True
    return False


_MARCAS_EQUIPO = (
    "samsung", "iphone", "motorola", "xiaomi", "huawei", "nokia", "lg ",
    "redmi", "pixel", "oppo", "vivo", "tcl", "alcatel", "a22", "a32", "a52",
)


def _bloque_anti_confusion_dispositivo(historial: list[MensajeHistorial]) -> str:
    """Refuerzo cuando la falla menciona Apple/Google pero no el modelo del teléfono."""
    texto = " ".join(m.contenido.lower() for m in historial if m.rol == "usuario")
    origen_servicio = any(
        k in texto
        for k in ("apple", "imessage", "iphone sms", "mensajes de apple", "desde apple")
    )
    tiene_marca = any(m in texto for m in _MARCAS_EQUIPO)
    if origen_servicio and not tiene_marca:
        return (
            "\n\n⚠️ CONTEXTO: El operador habló de mensajes/servicio Apple pero NO indicó el modelo del celular. "
            "Preguntá dispositivo de forma NEUTRA (ej. ¿Qué modelo de celular usa el cliente?). "
            "NO asumas iPhone ni Apple como dispositivo.\n"
        )
    return ""


def _bloque_fase_conversacion(data: ChatInput) -> str:
    historial = data.historial or []
    mensajes_usuario = [m for m in historial if m.rol == "usuario"]

    if _es_retomo_caso(historial):
        return PROMPT_RETOMO_CASO + _bloque_anti_confusion_dispositivo(historial)
    if len(mensajes_usuario) <= 1:
        return PROMPT_PRIMER_TURNO + _bloque_anti_confusion_dispositivo(historial)
    return PROMPT_TURNO_SIGUIENTE + _bloque_anti_confusion_dispositivo(historial)


def _bloque_contexto_ticket(data: ChatInput) -> str:
    if not data.contexto_ticket:
        return ""
    t = data.contexto_ticket
    lineas = []
    if t.cooperativa or t.linea or t.dispositivo or t.falla_tecnica:
        lineas.append("\n\nDATOS YA PROVISTOS POR EL OPERADOR (no contradecir, no volver a pedir):")
        lineas.append(f"- Cliente/Cooperativa: {t.cooperativa or 'pendiente'}")
        lineas.append(f"- Línea: {t.linea or 'pendiente'}")
        lineas.append(f"- Dispositivo: {t.dispositivo or 'pendiente'}")
        lineas.append(f"- Falla (para NOC): {t.falla_tecnica or 'pendiente'}")
    if t.ticket_activo_id:
        lineas.append(
            "- El sistema ya tiene un caso registrado para esta sesión (NO menciones IDs al operador)."
        )
    if t.modo_resolucion_kb and t.listo_para_jsc and not t.ticket_activo_id:
        lineas.append(
            "ACCIÓN: Datos completos + KB aplicable → empezá PASO 1 del manual. "
            "PROHIBIDO decir que ya está registrado en el NOC. Sin ticket hasta escalamiento explícito."
        )
    elif t.kb_encontrado and t.listo_para_jsc and not t.ticket_activo_id:
        lineas.append(
            "ACCIÓN: Hay KB similar y datos completos → modo resolución (paso a paso), sin ticket aún."
        )
    elif t.listo_para_jsc and not t.ticket_activo_id and t.requiere_ticket_noc:
        lineas.append(
            "ACCIÓN: Datos completos sin resolución por KB → confirmá que se registrará para el NOC (sin IDs en chat)."
        )
    elif t.listo_para_jsc and not t.ticket_activo_id:
        lineas.append(
            "ACCIÓN: Datos completos → según contexto KB o escalamiento."
        )
    if t.usuario_confirmo_ok:
        lineas.append("El operador confirmó resolución explícita → cerrá el caso.")
    return "\n".join(lineas)


def _construir_system_prompt(data: ChatInput, resultado_rag) -> str:
    partes = [SYSTEM_PROMPT_BASE]

    if resultado_rag.encontrado:
        partes.append(PROMPT_RESOLUCION_KB)
        partes.append(formatear_contexto_para_prompt(resultado_rag))
    else:
        partes.append(PROMPT_ESCALAMIENTO)
        partes.append(formatear_modo_escalamiento())

    partes.append(_bloque_fase_conversacion(data))
    partes.append(_bloque_contexto_ticket(data))
    return "\n".join(partes)


def _construir_mensajes(data: ChatInput, system_content: str) -> list[dict]:
    mensajes: list[dict] = [{"role": "system", "content": system_content}]

    historial = data.historial
    if not historial and data.mensaje_usuario:
        historial = [MensajeHistorial(rol="usuario", contenido=data.mensaje_usuario)]

    for m in historial:
        role = "user" if m.rol == "usuario" else "assistant"
        mensajes.append({"role": role, "content": m.contenido})

    return mensajes


async def procesar_chat(data: ChatInput) -> ChatResponse:
    consulta = _texto_consulta(data)
    resultado_rag = buscar_contexto(consulta)

    system_content = _construir_system_prompt(data, resultado_rag)
    mensajes = _construir_mensajes(data, system_content)
    respuesta = chat_completion(mensajes, temperature=0.12)

    modulo_id = resultado_rag.bloque.id if resultado_rag.bloque else "escalamiento"
    kb_ok = resultado_rag.encontrado
    modulo_nombre = (
        "Resolución asistida — caso similar en KB"
        if kb_ok
        else "Escalamiento NOC"
    )

    return ChatResponse(
        respuesta=respuesta,
        modulo_inferido=modulo_id,
        modulo_nombre=modulo_nombre,
        tipo_caso_sugerido=resultado_rag.modo,
        kb_encontrado=kb_ok,
        modo_resolucion_kb=kb_ok,
        puntaje_kb=resultado_rag.puntaje,
    )
