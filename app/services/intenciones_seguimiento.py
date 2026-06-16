"""Detección de intenciones de seguimiento y memoria conversacional operativa."""

from __future__ import annotations

from typing import Any

from app.domain.flujos_operativos import detectar_categoria_flujo, siguiente_paso_mensaje
from app.services.interprete_conversacional import (
    _fusionar_hechos,
    detectar_intencion_normalizada,
    extraer_hechos_normalizados,
    mensaje_confirma_paso_operativo,
    mensaje_reporta_persistencia,
)


def _ultimo_usuario(historial: list[dict]) -> str:
    for m in reversed(historial):
        if m.get("rol") == "usuario":
            return (m.get("contenido") or "").strip()
    return ""


def _texto_usuario(historial: list[dict]) -> str:
    return "\n".join(
        (m.get("contenido") or "").lower()
        for m in historial
        if m.get("rol") == "usuario"
    )


_FRASES_ZONA_UNICA = (
    "una sola zona",
    "solo en una zona",
    "sólo en una zona",
    "solo en esa zona",
    "sólo en esa zona",
    "esa sola zona",
    "en esa zona",
    "solo en ese lugar",
    "sólo en ese lugar",
    "solo ahi",
    "solo ahí",
    "solamente ahi",
    "solamente ahí",
    "solo pasa en",
    "sólo pasa en",
)

_FRASES_VARIAS_ZONAS = (
    "varias zonas",
    "todas las zonas",
    "todos lados",
    "en todos lados",
    "distintas zonas",
    "varios lugares",
    "distintos lugares",
    "varias ubicaciones",
    "diferentes lugares",
)


def _ultimo_asistente(historial: list[dict]) -> str:
    for m in reversed(historial):
        if m.get("rol") == "asistente":
            return (m.get("contenido") or "").lower().strip()
    return ""


def es_pregunta(msg: str) -> bool:
    t = msg.lower().strip()
    if "?" in t:
        return True
    return any(
        p in t
        for p in (
            "tenes ",
            "tienes ",
            "tenés ",
            "podes ",
            "podés ",
            "puede ",
            "me recomendas",
            "me recomendás",
            "me conviene",
            "deberia",
            "debería",
            "que hago",
            "qué hago",
            "que me recomendas",
            "qué me recomendas",
            "alguna novedad",
            "hay novedad",
            "como seguimos",
            "cómo seguimos",
            "fue una pregunta",
            "me pasaste",
            "me diste",
        )
    )


def _es_persistencia_post_paso(msg: str) -> bool:
    """Operador indica que hizo el paso pero el problema persiste."""
    return mensaje_reporta_persistencia(msg)


def _es_confirmacion_paso(msg: str) -> bool:
    """Detecta que el operador confirma haber hecho el paso sugerido por el bot."""
    if not msg or es_pregunta(msg):
        return False
    return mensaje_confirma_paso_operativo(msg)


_FRASES_LLAMADA_OK = (
    "llamada si",
    "llamadas si",
    "llamada sí",
    "llamadas sí",
    "llama si",
    "llama bien",
    "llamada ok",
    "llamadas ok",
    "puede llamar",
    "llamadas andan",
    "llamada anda",
    "voz si",
    "voz sí",
    "voz ok",
)
_FRASES_DATOS_FALLAN = (
    "datos no",
    "sin datos",
    "no navega",
    "no anda",
    "sin internet",
    "no usa datos",
    "no usa los datos",
)


def _es_respuesta_prueba_llamada(msg: str) -> bool:
    """Operador informa resultado de la prueba de llamada (voz sí/no, datos sí/no)."""
    t = msg.lower().strip()
    if any(p in t for p in _FRASES_LLAMADA_OK):
        return True
    if any(
        p in t
        for p in (
            "llamadas no",
            "no puede llamar",
            "no llama",
            "no puede hacer llamadas",
            "no podemos hacer la llamada",
            "no pudimos hacer la llamada",
        )
    ):
        return True
    return False


def _aplicar_confirmacion_paso(hechos: dict, ultimo_bot: str, ultimo_usuario: str) -> None:
    """Marca el paso que el bot pidió en su último mensaje."""
    bot = ultimo_bot.lower()
    usr = ultimo_usuario.lower()
    if "llamada" in bot and _es_respuesta_prueba_llamada(ultimo_usuario):
        if any(
            p in usr
            for p in (
                "no podemos",
                "no puede",
                "no pudimos",
                "no funciona",
                "llamadas no",
                "no llama",
                "no puede llamar",
            )
        ):
            hechos["llamadas_ok"] = False
        else:
            hechos["llamadas_ok"] = True
            if any(p in usr for p in _FRASES_DATOS_FALLAN):
                hechos["datos_ok"] = False
                hechos["resuelto"] = False
        return
    if "llamada" in bot and any(p in usr for p in ("no podemos", "no puede", "no pudimos", "no funciona")):
        hechos["llamadas_ok"] = False
        return
    if "jsc" in bot and ("roaming" in bot or "itinerancia" in bot):
        hechos["roaming_verificado"] = True
        return
    if "jsc" in bot and any(p in bot for p in ("línea", "linea", "servicio", "mensajería", "mensajeria", "sms")):
        hechos["linea_jsc_verificada"] = True
        return
    if ("jsc" in bot or "roaming" in bot) and any(
        p in usr for p in ("habilitados", "habilitado", "activos", "activo", "estan habilitados", "están habilitados")
    ):
        hechos["roaming_verificado"] = True
        return
    if "apn" in bot:
        if any(p in usr for p in ("no navega", "no puede navegar", "sin datos", "no anda", "sin internet")):
            hechos["apn_configurado"] = True
            hechos["datos_ok"] = False
        else:
            hechos["apn_configurado"] = True
        return
    if "modo avión" in bot or "modo avion" in bot or "reinici" in bot:
        hechos["reinicio_o_modo_avion"] = True
        return
    if "una sola zona" in bot or "varias ubicaciones" in bot or "varias zonas" in bot:
        if any(p in usr for p in _FRASES_VARIAS_ZONAS):
            hechos["multiples_zonas"] = True
            hechos["zona_unica"] = False
        elif any(p in usr for p in _FRASES_ZONA_UNICA):
            hechos["zona_unica"] = True
            hechos["multiples_zonas"] = False
        return
    if "llamada" in bot:
        hechos["llamadas_ok"] = True
        return
    if "datos móviles" in bot or "datos moviles" in bot or "itinerancia" in bot:
        hechos["datos_moviles_activos"] = True
        return
    if any(
        p in bot
        for p in (
            "alcance del problema",
            "afecta señal",
            "afecta senal",
            "solo llamadas",
            "confirmar zona",
        )
    ):
        if len(usr) > 18 or any(
            p in usr
            for p in (
                "datos",
                "señal",
                "senal",
                "llamadas",
                "uruguay",
                "argentina",
                "brasil",
                "exterior",
                "roaming",
                "sin datos",
                "no tiene datos",
                "internet",
            )
        ):
            hechos["alcance_confirmado"] = True
        return


def _es_hallazgo_jsc_roaming_inactivo(msg: str) -> bool:
    t = msg.lower()
    if "roaming" not in t and "itinerancia" not in t:
        return False
    return any(
        p in t
        for p in (
            "no estaba activado",
            "estaba desactivado",
            "estaba apagado",
            "sin roaming",
            "roaming desactivado",
            "roaming apagado",
            "no tenia roaming",
            "no tenía roaming",
            "no tiene roaming",
            "no estaba habilitado",
            "servicio de roaming inactivo",
        )
    )


def _replay_confirmaciones_historial(historial: list[dict], hechos: dict) -> None:
    """Reconstruye pasos confirmados recorriendo todo el diálogo (no solo el último turno)."""
    ultimo_bot_ctx = ""
    for m in historial:
        rol = m.get("rol")
        contenido = (m.get("contenido") or "").strip()
        if not contenido:
            continue
        if rol == "asistente":
            ultimo_bot_ctx = contenido
            continue
        if rol != "usuario" or not ultimo_bot_ctx:
            continue
        usr = contenido.lower()
        if _es_confirmacion_paso(contenido):
            _aplicar_confirmacion_paso(hechos, ultimo_bot_ctx, usr)
        elif _es_persistencia_post_paso(contenido):
            _aplicar_confirmacion_paso(hechos, ultimo_bot_ctx, usr)
            hechos["resuelto"] = False
        elif "llamada" in ultimo_bot_ctx.lower() and _es_respuesta_prueba_llamada(contenido):
            _aplicar_confirmacion_paso(hechos, ultimo_bot_ctx, usr)
        elif "apn" in ultimo_bot_ctx.lower() and any(
            p in usr for p in ("no navega", "no puede navegar", "sin datos", "no anda", "sin internet")
        ):
            _aplicar_confirmacion_paso(hechos, ultimo_bot_ctx, usr)
        elif ("jsc" in ultimo_bot_ctx.lower() or "roaming" in ultimo_bot_ctx.lower()) and any(
            p in usr for p in ("habilitados", "habilitado", "activos", "activo", "estan habilitados", "están habilitados")
        ):
            hechos["roaming_verificado"] = True
        elif "jsc" in ultimo_bot_ctx.lower() and any(
            p in ultimo_bot_ctx.lower() for p in ("línea", "linea", "servicio", "mensajería", "mensajeria", "sms")
        ):
            hechos["linea_jsc_verificada"] = True
        elif _es_hallazgo_jsc_roaming_inactivo(contenido):
            hechos["roaming_verificado"] = True
            hechos["roaming_jsc_inactivo"] = True
        elif any(
            p in usr
            for p in (
                "roaming habilitado",
                "roaming activado",
                "activamos el roaming",
                "ya activamos roaming",
                "activamos roaming",
                "habilitamos roaming",
            )
        ):
            hechos["roaming_activado_jsc"] = True
            hechos["roaming_jsc_inactivo"] = False


def extraer_hechos_conversacion(historial: list[dict], previos: dict | None = None) -> dict:
    """Resume lo que ya se hizo o se sabe del caso a partir del diálogo."""
    hechos: dict[str, Any] = dict(previos or {})
    texto = _texto_usuario(historial)
    ultimo = _ultimo_usuario(historial).lower()

    _replay_confirmaciones_historial(historial, hechos)

    if _es_hallazgo_jsc_roaming_inactivo(_ultimo_usuario(historial)):
        hechos["roaming_verificado"] = True
        hechos["roaming_jsc_inactivo"] = True

    if any(p in texto for p in ("cambiamos la sim", "cambió la sim", "cambio la sim", "nueva sim", "le cambiamos la sim")):
        if not es_pregunta(ultimo) or "ya " in ultimo or "lo hicimos" in ultimo:
            hechos["sim_cambiada"] = True

    if any(p in texto for p in ("recomend", "sugiero", "probar cambiando la sim", "cambiar la sim")):
        hechos["sim_recomendada"] = True

    if any(p in texto for p in ("apn", "internet.coop")):
        if any(p in texto for p in ("configure", "configur", "cambio eso", "lo probo y funcion", "funciono", "funcionó")):
            hechos["apn_configurado"] = True
        elif "recomend" in texto or "sugiero" in ultimo:
            hechos["apn_recomendado"] = True

    if any(p in texto for p in ("modo avion", "modo avión", "reinicio", "reinició", "reiniciar", "apagar y prender")):
        hechos["reinicio_o_modo_avion"] = True
    ultimo_bot = _ultimo_asistente(historial)
    if (
        mensaje_confirma_paso_operativo(_ultimo_usuario(historial))
        or mensaje_reporta_persistencia(_ultimo_usuario(historial))
    ) and any(p in ultimo_bot for p in ("modo avión", "modo avion", "reinici")):
        hechos["reinicio_o_modo_avion"] = True
        if mensaje_reporta_persistencia(_ultimo_usuario(historial)):
            hechos["resuelto"] = False

    if any(p in texto for p in ("datos moviles activos", "datos móviles activos", "datos activados", "datos habilitados")):
        hechos["datos_moviles_activos"] = True

    if any(
        p in texto
        for p in (
            "roaming habilitado",
            "roaming activo",
            "roaming activado",
            "itinerancia habilitada",
            "itinerancia activa",
            "itinerancia activada",
        )
    ):
        hechos["roaming_verificado"] = True

    if _es_respuesta_prueba_llamada(_ultimo_usuario(historial)) and hechos.get("llamadas_ok") is not False:
        if any(
            p in ultimo
            for p in (
                "no podemos",
                "no puede",
                "no pudimos",
                "llamadas no",
                "no llama",
                "no puede llamar",
            )
        ):
            hechos["llamadas_ok"] = False
        else:
            hechos["llamadas_ok"] = True
            if any(p in ultimo for p in _FRASES_DATOS_FALLAN):
                hechos["datos_ok"] = False
                hechos["resuelto"] = False
    if any(p in ultimo for p in ("llamadas no", "no puede llamar", "no llama", "no puede hacer llamadas")):
        hechos["llamadas_ok"] = False
    if any(p in ultimo for p in ("no podemos hacer la llamada", "no pudimos hacer la llamada")):
        hechos["llamadas_ok"] = False

    if any(p in texto for p in _FRASES_ZONA_UNICA):
        hechos["zona_unica"] = True
        hechos["multiples_zonas"] = False
    if any(p in texto for p in _FRASES_VARIAS_ZONAS):
        hechos["multiples_zonas"] = True
        hechos["zona_unica"] = False

    _frases_datos_fallan = (
        "no puede navegar",
        "sin datos",
        "no tiene datos",
        "no navega",
        "no usa los datos",
        "sin internet",
        "datos no",
        "no funciona",
        "no funcionó",
        "no funciono",
        "sigue sin datos",
        "sigue con problemas",
        "sigue el problema",
        "usuario sigue",
        "cliente sigue",
    )
    _paises_roaming = (
        "uruguay",
        "argentina",
        "brasil",
        "paraguay",
        "chile",
        "bolivia",
        "exterior",
        "extranjero",
        "saliendo de",
    )
    if any(p in texto for p in _paises_roaming) and any(
        p in texto for p in ("datos", "internet", "navegar", "sin datos", "no tiene datos")
    ):
        hechos["alcance_confirmado"] = True
        hechos["datos_ok"] = False
    _frases_datos_ok = (
        "puede navegar",
        "navega bien",
        "datos andan",
        "ya anda",
        "datos ok",
        "navega ok",
        "funciono",
        "funcionó",
        "ya funciona",
        "navega sin problemas",
    )
    if any(p in texto for p in _frases_datos_fallan):
        hechos["datos_ok"] = False
    for m in historial:
        if m.get("rol") != "usuario":
            continue
        t = (m.get("contenido") or "").lower()
        if any(p in t for p in _frases_datos_fallan):
            hechos["datos_ok"] = False
            continue
        if any(p in t for p in _frases_datos_ok):
            hechos["datos_ok"] = True

    if any(
        p in ultimo
        for p in (
            "sin solucion",
            "sin solución",
            "no funcion",
            "no anda",
            "sigue igual",
            "no puede",
            "no es asi",
            "no es así",
            "sigue con problemas",
            "sigue el problema",
            "usuario sigue",
            "cliente sigue",
        )
    ):
        hechos["resuelto"] = False
        if any(p in ultimo for p in ("problema", "datos", "sin ", "no ")):
            hechos["datos_ok"] = False
    if any(
        p in ultimo
        for p in (
            "funciono",
            "funcionó",
            "ya funciona",
            "quedo resuelto",
            "quedó resuelto",
            "problema resuelto",
            "lo probo y funcion",
            "si lo probo y funcion",
        )
    ):
        hechos["resuelto"] = True

    pasos: list[str] = []
    if hechos.get("sim_cambiada"):
        pasos.append("Cambio de SIM realizado")
    elif hechos.get("sim_recomendada") and not hechos.get("sim_cambiada"):
        pasos.append("Cambio de SIM recomendado (pendiente o en consulta)")
    if hechos.get("llamadas_ok") is True:
        pasos.append("Llamadas verificadas: OK")
    elif hechos.get("llamadas_ok") is False:
        pasos.append("Llamadas verificadas: fallan")
    if hechos.get("apn_configurado"):
        pasos.append("APN de datos configurado")
    elif hechos.get("apn_recomendado") and not hechos.get("apn_configurado"):
        pasos.append("APN recomendado (pendiente)")
    if hechos.get("datos_moviles_activos"):
        pasos.append("Datos móviles habilitados")
    if hechos.get("reinicio_o_modo_avion"):
        pasos.append("Modo avión/reinicio realizado")
    if hechos.get("roaming_verificado"):
        if hechos.get("roaming_jsc_inactivo") and not hechos.get("roaming_activado_jsc"):
            pasos.append("Roaming inactivo en JSC (hallazgo)")
        else:
            pasos.append("Roaming/itinerancia verificado")
    if hechos.get("datos_ok") is True:
        pasos.append("Datos móviles: OK")
    elif hechos.get("datos_ok") is False:
        pasos.append("Datos móviles: fallan")
    if hechos.get("zona_unica") is True:
        pasos.append("Afectación localizada en una zona")
    elif hechos.get("multiples_zonas") is True:
        pasos.append("Afectación en varias zonas")
    hechos["pasos_realizados"] = pasos
    cat_prev = hechos.get("categoria_flujo")
    cat_full = detectar_categoria_flujo(texto, hechos)
    if cat_prev in ("roaming", "datos", "senal", "sms", "sim"):
        pass
    elif cat_full != "general":
        hechos["categoria_flujo"] = cat_full
    elif not cat_prev:
        hechos["categoria_flujo"] = "general"

    hechos_norm = extraer_hechos_normalizados(_ultimo_usuario(historial), ultimo_bot=_ultimo_asistente(historial))
    hechos = _fusionar_hechos(hechos, hechos_norm)
    return hechos


def _es_nuevo_reclamo_en_sesion(historial: list[dict], caso: dict | None) -> bool:
    ultimo = _ultimo_usuario(historial).lower()
    prev = ((caso or {}).get("datos_triaje") or {}).get("sintoma", "").lower()
    if not prev:
        return False
    if not any(
        p in ultimo
        for p in (
            "linea",
            "línea",
            "sintoma",
            "modelo",
            "registra",
            "datos",
            "señal",
            "senal",
            "sms",
            "mensaje de texto",
            "mensajes de texto",
            "imessage",
            "a2p",
        )
    ):
        return False
    if detectar_categoria_flujo(prev) != detectar_categoria_flujo(ultimo):
        return True
    palabras_prev = {w for w in prev.split() if len(w) > 4}
    palabras_nuevo = {w for w in ultimo.split() if len(w) > 4}
    return bool(palabras_prev and palabras_nuevo and len(palabras_prev & palabras_nuevo) < 2)


def detectar_intencion_seguimiento(
    historial: list[dict],
    *,
    caso: dict | None = None,
    ticket: dict | None = None,
    hechos: dict | None = None,
) -> dict:
    ultimo = _ultimo_usuario(historial)
    ticket_id = (ticket or {}).get("id") or (caso or {}).get("ticket_id") or ""
    tiene_ticket = bool(ticket_id)
    h = hechos or {}

    norm = detectar_intencion_normalizada(ultimo, tiene_ticket=tiene_ticket, hechos=h)
    tipo = norm.get("tipo", "continuar")

    if tipo == "seguimiento_activo" and _es_nuevo_reclamo_en_sesion(historial, caso):
        tipo = "continuar"

    if tipo == "continuar" and tiene_ticket and len(historial) > 2 and not _es_nuevo_reclamo_en_sesion(historial, caso):
        tipo = "seguimiento_activo"
        norm = {**norm, "tipo": tipo, "confianza": 0.55}

    return {
        "tipo": tipo,
        "ticket_id": ticket_id,
        "confianza": norm.get("confianza", 0.5),
        "fuente": norm.get("fuente", "reglas"),
    }


def siguiente_paso_sugerido(hechos: dict, sintoma: str = "") -> str | None:
    return siguiente_paso_mensaje(hechos, sintoma)


def construir_resumen(hechos: dict, datos: dict, ticket: dict | None) -> str:
    linea = datos.get("linea") or (ticket or {}).get("linea") or "la línea"
    sintoma = datos.get("sintoma") or (ticket or {}).get("descripcion_falla") or "el inconveniente reportado"
    partes = [
        f"Resumen del caso para {linea}:",
        f"- Motivo inicial: {sintoma}.",
    ]
    pasos = hechos.get("pasos_realizados") or []
    if pasos:
        partes.append("- Acciones en consola:")
        partes.extend(f"  · {p}" for p in pasos)
    else:
        partes.append("- Todavía no quedaron acciones técnicas registradas en la conversación.")
    if ticket:
        partes.append(
            f"- Ticket {ticket.get('id')} ({ticket.get('nivel', 'N1')}) en estado {ticket.get('estado', 'Abierto')}."
        )
    if hechos.get("resuelto"):
        partes.append("- Resultado: el operador indicó que el caso quedó resuelto.")
    return "\n".join(partes)
