"""Extracción estructurada para el panel tiquetero."""

from __future__ import annotations

import json
import re

from fastapi import HTTPException

from app.informe_noc import construir_informe_noc
from app.knowledge import buscar_contexto
from app.llm import chat_completion
from app.models import EstructurarInput, EstructurarResponse, MensajeHistorial

PROMPT_EXTRACCION = """
Analizá el historial entre operador y Copilot NOC imowi. Tu salida alimenta un ticket para ingeniería del NOC.
Objetivo: que el NOC resuelva MÁS RÁPIDO sin releer el chat.

HISTORIAL:
{historial}

CONTEXTO RAG: {contexto_rag}

REGLAS DE OBJETIVIDAD:
- Extraé SOLO lo que el operador dijo. NUNCA inventes línea, modelo, cooperativa ni pasos desde la KB.
- "cooperativa" = cliente/cooperativa del reclamo (ej: CoopBatan), NO el usuario del sistema.
- La KB solo influye en "tipo_caso", NO en datos del cliente.

DISPOSITIVO vs FALLA (CRÍTICO):
- "dispositivo" = marca/modelo del TELÉFONO del abonado solo si el operador lo dijo explícitamente (ej: Samsung A22).
- Menciones de Apple, iMessage, Google, WhatsApp en el reclamo describen origen/servicio o tipo de mensaje, NO el modelo del equipo.
- Si el operador corrigió el dispositivo, usá la corrección. "problema"/"falla_tecnica" debe reflejar el síntoma real (ej. no recibe SMS de Apple para suscripción), sin decir que el equipo es Apple salvo que lo afirmen.

LÍNEAS TELEFÓNICAS (ARGENTINA):
- "linea" = cadena numérica COMPLETA provista por el operador (ej: 2235402690). Copiá todos los dígitos.
- PROHIBIDO truncar o acortar porque el número empieza con un código de área (223, 11, 351, etc.).
- No asumas longitud fija de 6, 7 u 8 dígitos; 10-11 dígitos son habituales.

INFORME PARA NOC (campos separados; si no hay dato, dejá ""):
- "problema": síntoma concreto en una frase.
- "alcance": dónde/cuándo afecta (zona, intermitencia, total, etc.).
- "acciones_realizadas": qué ya probó el operador (reinicio, APN, etc.).
- "datos_verificados": solo hechos confirmados por el operador (línea, equipo, versión si la dijo).

"falla_tecnica": texto final multilínea con formato:
PROBLEMA: ...
ALCANCE: ...
ACCIONES DEL OPERADOR: ...
DATOS VERIFICADOS: ...
(Omití líneas vacías. No copies texto de la KB.)

- "usuario_confirmo_ok": true SOLO si dijo explícitamente resuelto/ok/listo/confirmado. NO por "no" o "gracias".
- "tipo_caso": "manual" si hay guía KB aplicable; "escalamiento" si va directo al NOC.
- "listo_para_jsc": true si cooperativa, linea, dispositivo y falla_tecnica están completos.
- "requiere_ticket_noc": true SOLO si debe generarse ticket ahora (escalamiento sin KB, operador pide escalar, pasos fallaron, problema persiste). false si aún está en resolución asistida con KB.
- "modo_resolucion_kb": true si listo_para_jsc, hay KB aplicable y requiere_ticket_noc es false (intentar resolver antes del ticket).

JSON SOLO:
{{
  "cooperativa": "",
  "linea": "",
  "dispositivo": "",
  "problema": "",
  "alcance": "",
  "acciones_realizadas": "",
  "datos_verificados": "",
  "falla_tecnica": "",
  "tipo_caso": "manual|escalamiento",
  "usuario_confirmo_ok": false,
  "listo_para_jsc": false,
  "requiere_ticket_noc": false,
  "modo_resolucion_kb": false
}}
"""

CONFIRMACION_EXPLICITA = (
    "ok", "listo", "confirmado", "resuelto", "solucionado", "solucionó",
    "quedo resuelto", "quedó resuelto", "problema resuelto", "ya funciona",
    "funciona bien", "caso cerrado", "podemos cerrar",
)

ESCALAMIENTO_FRASES = (
    "escalar", "escalam", "al noc", "enviar al noc", "mandar al noc",
    "generar ticket", "crear ticket", "registrar ticket", "hacer ticket",
    "no funciona", "sigue igual", "sigue sin", "no se resolv", "persiste",
    "mismo problema", "aún no", "aun no", "no sirvio", "no sirvió", "sin solucion",
    "voy a escalar", "se escalará", "escalar el caso", "registrar el caso",
    "registrado para el noc", "se registrará", "equipo noc", "caso al noc",
)

_MARCAS_EQUIPO = (
    "samsung", "iphone", "motorola", "xiaomi", "huawei", "nokia", "redmi",
    "pixel", "oppo", "vivo", "tcl", "alcatel", "galaxy",
)


def _normalizar_campo(valor: str | None) -> str:
    if not valor:
        return ""
    t = str(valor).strip()
    return "" if t.upper() == "PENDIENTE" else t


def _texto_historial(historial: list[MensajeHistorial]) -> str:
    return "\n".join(
        f"{'USUARIO' if m.rol == 'usuario' else 'ASISTENTE'}: {m.contenido}"
        for m in historial
    )


def _texto_consulta(historial: list[MensajeHistorial]) -> str:
    return "\n".join(m.contenido for m in historial if m.rol == "usuario")


def _usuario_confirmo_ok(historial: list[MensajeHistorial], llm_dijo: bool) -> bool:
    if not llm_dijo:
        return False
    mensajes_usuario = [m.contenido.lower().strip() for m in historial if m.rol == "usuario"]
    if not mensajes_usuario:
        return False
    ultimos = mensajes_usuario[-4:]
    for msg in reversed(ultimos):
        if msg in ("no", "nop", "nope", "no.", "nah"):
            return False
        if msg in ("gracias", "muchas gracias", "de nada", "chau", "adiós", "adios"):
            return False
        if any(frase in msg for frase in CONFIRMACION_EXPLICITA):
            return True
    return False


def _texto_dialogo_reciente(historial: list[MensajeHistorial], n: int = 8) -> str:
    return " ".join(m.contenido.lower() for m in historial[-n:])


def _detectar_escalamiento(historial: list[MensajeHistorial]) -> bool:
    """Operador o asistente indicaron que el caso va al NOC."""
    return any(frase in _texto_dialogo_reciente(historial) for frase in ESCALAMIENTO_FRASES)


def _extraer_linea(historial: list[MensajeHistorial]) -> str:
    for m in reversed(historial):
        if m.rol != "usuario":
            continue
        limpio = re.sub(r"[^\d]", "", m.contenido)
        candidatos = re.findall(r"\d{10,11}", limpio)
        if candidatos:
            return candidatos[-1]
    return ""


def _extraer_cooperativa(historial: list[MensajeHistorial]) -> str:
    for m in historial:
        if m.rol != "usuario":
            continue
        t = m.contenido.strip()
        b = re.search(
            r"(?:coop(?:erativa)?|de la coop)\s+([a-zA-ZáéíóúÁÉÍÓÚñÑ0-9\s]{2,40})",
            t,
            re.I,
        )
        if b:
            nombre = b.group(1).strip().split(".")[0].split(",")[0].strip()
            if nombre:
                return f"Coop {nombre.title()}" if not nombre.lower().startswith("coop") else nombre.title()
        if re.search(r"coop\s*batan", t, re.I):
            return "Coop Batán"
    return ""


def _extraer_dispositivo(historial: list[MensajeHistorial]) -> str:
    texto = " ".join(m.contenido for m in historial if m.rol == "usuario").lower()
    match = re.search(
        r"(samsung\s*(?:galaxy\s*)?a\d+\w*|iphone\s*\d+\w*|motorola\s*[\w\s]+|redmi\s*[\w\s]+|xiaomi\s*[\w\s]+)",
        texto,
        re.I,
    )
    if match:
        return " ".join(match.group(1).split()).title()
    for marca in _MARCAS_EQUIPO:
        if marca in texto:
            return marca.title()
    return ""


def _estructurar_heuristica(
    data: EstructurarInput,
    resultado_rag,
    modulo_nombre: str,
    modulo_id: str,
) -> EstructurarResponse:
    """Fallback sin LLM (cuota agotada o error) — usa el historial del operador."""
    cooperativa = _extraer_cooperativa(data.historial)
    linea = _extraer_linea(data.historial)
    dispositivo = _extraer_dispositivo(data.historial)
    sintomas = [m.contenido for m in data.historial if m.rol == "usuario"]
    problema = sintomas[-1] if sintomas else ""
    falla = construir_informe_noc(
        problema=problema[:800],
        datos_verificados=", ".join(
            x for x in (f"Cooperativa {cooperativa}" if cooperativa else "", f"Línea {linea}" if linea else "", dispositivo) if x
        ),
    )
    kb_ok = resultado_rag.encontrado
    tipo = _tipo_caso("manual" if kb_ok else "escalamiento", kb_ok)
    listo = bool(cooperativa and linea and dispositivo and falla)
    requiere_ticket = _requiere_ticket_noc(data.historial, False, kb_ok, tipo, listo)
    modo_resolucion = listo and kb_ok and tipo == "manual" and not requiere_ticket
    if kb_ok and tipo == "manual":
        modulo_nombre = "Resolución asistida — caso similar en KB"

    return EstructurarResponse(
        cooperativa=cooperativa,
        modulo=modulo_nombre,
        modulo_id=modulo_id,
        linea=linea,
        dispositivo=dispositivo,
        descripcion=falla,
        falla_tecnica=falla,
        tipo_caso=tipo,
        usuario_confirmo_ok=False,
        listo_para_jsc=listo,
        envio_automatico=listo and requiere_ticket,
        kb_encontrado=kb_ok,
        modo_resolucion_kb=modo_resolucion,
        requiere_ticket_noc=requiere_ticket,
    )


def _requiere_ticket_noc(
    historial: list[MensajeHistorial],
    llm_dijo: bool,
    rag_encontrado: bool,
    tipo: str,
    listo: bool,
) -> bool:
    if not listo:
        return False
    if tipo == "escalamiento" or not rag_encontrado:
        return True
    if _detectar_escalamiento(historial):
        return True
    return False


def _tipo_caso(valor: str | None, rag_encontrado: bool) -> str:
    t = (valor or "").lower().strip()
    if t in ("manual", "cubierto_manual", "resoluble", "resolucion"):
        return "manual"
    if rag_encontrado:
        return "manual"
    return "escalamiento"


def _falla_para_noc(parsed: dict) -> str:
    libre = _normalizar_campo(parsed.get("falla_tecnica") or parsed.get("descripcion"))
    estructurado = construir_informe_noc(
        problema=_normalizar_campo(parsed.get("problema")),
        alcance=_normalizar_campo(parsed.get("alcance")),
        acciones_realizadas=_normalizar_campo(parsed.get("acciones_realizadas")),
        datos_verificados=_normalizar_campo(parsed.get("datos_verificados")),
        falla_libre=libre,
    )
    return estructurado


async def estructurar_ticket(data: EstructurarInput) -> EstructurarResponse:
    consulta = _texto_consulta(data.historial)
    resultado_rag = buscar_contexto(consulta)

    modulo_id = resultado_rag.bloque.id if resultado_rag.bloque else "escalamiento"
    modulo_nombre = (
        "Referencia KB — caso similar"
        if resultado_rag.encontrado
        else "Escalamiento NOC"
    )
    contexto_rag = (
        f"Caso similar en KB (score {resultado_rag.puntaje:.2f}) — priorizar resolución asistida antes de ticket"
        if resultado_rag.encontrado
        else "Sin match claro en KB — escalamiento NOC directo"
    )

    prompt = PROMPT_EXTRACCION.format(
        historial=_texto_historial(data.historial),
        contexto_rag=contexto_rag,
    )

    parsed: dict | None = None
    try:
        raw = chat_completion([{"role": "user", "content": prompt}], temperature=0.1, json_mode=True)
        parsed = json.loads(raw)
    except HTTPException as e:
        if e.status_code in (503, 500, 413):
            return _estructurar_heuristica(data, resultado_rag, modulo_nombre, modulo_id)
        raise
    except (json.JSONDecodeError, Exception):
        return _estructurar_heuristica(data, resultado_rag, modulo_nombre, modulo_id)

    if not isinstance(parsed, dict):
        return _estructurar_heuristica(data, resultado_rag, modulo_nombre, modulo_id)

    cooperativa = _normalizar_campo(parsed.get("cooperativa"))
    linea = _normalizar_campo(parsed.get("linea"))
    dispositivo = _normalizar_campo(parsed.get("dispositivo"))
    falla = _falla_para_noc(parsed)
    tipo = _tipo_caso(parsed.get("tipo_caso"), resultado_rag.encontrado)
    confirmo = _usuario_confirmo_ok(data.historial, bool(parsed.get("usuario_confirmo_ok", False)))
    listo = bool(cooperativa and linea and dispositivo and falla)
    kb_ok = resultado_rag.encontrado
    requiere_ticket = _requiere_ticket_noc(
        data.historial,
        bool(parsed.get("requiere_ticket_noc", False)),
        kb_ok,
        tipo,
        listo,
    )
    modo_resolucion = listo and kb_ok and tipo == "manual" and not requiere_ticket and not confirmo

    if kb_ok and tipo == "manual":
        modulo_nombre = "Resolución asistida — caso similar en KB"

    return EstructurarResponse(
        cooperativa=cooperativa,
        modulo=modulo_nombre,
        modulo_id=modulo_id,
        linea=linea,
        dispositivo=dispositivo,
        descripcion=falla,
        falla_tecnica=falla,
        tipo_caso=tipo,
        usuario_confirmo_ok=confirmo,
        listo_para_jsc=listo,
        envio_automatico=listo and requiere_ticket,
        kb_encontrado=kb_ok,
        modo_resolucion_kb=modo_resolucion,
        requiere_ticket_noc=requiere_ticket,
    )
