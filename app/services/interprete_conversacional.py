"""Capa de interpretación conversacional — normaliza lenguaje técnico e informal."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.llm import chat_completion

logger = logging.getLogger(__name__)

# --- Patrones agrupados por intención (variantes técnicas e informales) ---

_PATRONES_ESTADO_TICKET = (
    "creaste el ticket",
    "creo el ticket",
    "creó el ticket",
    "creaste ticket",
    "generaste el ticket",
    "registraste el ticket",
    "quedo el ticket",
    "quedó el ticket",
    "esta creado el ticket",
    "está creado el ticket",
    "hay ticket",
    "numero de ticket",
    "número de ticket",
    "cual es el ticket",
    "cuál es el ticket",
    "lo cargaste",
    "lo registraste",
    "quedó reclamo",
    "quedo reclamo",
    "pasame el numero",
    "pasame el número",
    "pasá el número",
    "numero de reclamo",
    "número de reclamo",
    "te pregunté si creaste",
    "me dijiste el ticket",
)

_PATRONES_CORRECCION = (
    "fue una pregunta",
    "no me pasaste",
    "no me diste",
    "ningun cambio",
    "ningún cambio",
    "no es asi",
    "no es así",
    "no quedo resuelto",
    "no quedó resuelto",
    "sigue con problemas",
    "sigue el problema",
    "usuario sigue",
    "cliente sigue",
    "todavia tiene",
    "todavía tiene",
    "repetis",
    "repetís",
    "repetir",
    "mismo paso",
    "ya te dije",
    "otra vez lo mismo",
    "eso ya lo revisamos",
    "ya lo revisamos",
    "me adelantaste",
    "no es correcto",
)

_PATRONES_PASO_EJECUTADO = (
    "ya lo hicimos",
    "ya lo hicimo",
    "lo hicimos",
    "lo hicimo",
    "ya lo probamos",
    "lo probamos",
    "ya probamos",
    "hicimos ambas",
    "ambas cosas",
    "ya se hizo",
    "ya lo verificamos",
    "lo verificamos",
    "ya lo intentamos",
    "lo intentamos",
    "ya lo hice",
    "lo hice",
    "reinicio hecho",
    "modo avion hecho",
    "modo avión hecho",
)

_PATRONES_PERSISTENCIA = (
    "ya se hizo",
    "ya lo hicimos",
    "ya lo hicimo",
    "hecho y sigue",
    "sigue igual",
    "sigue sin",
    "persiste",
    "sin cambios",
    "sin solucion",
    "sin solución",
    "sin resultado",
    "hice lo que me dijiste",
    "hice lo que dijiste",
    "seguimos igual",
    "no cambió",
    "no cambio",
    "sigue fallando",
    "sigue sin andar",
    "ya lo probamos",
    "probamos sin",
    "no funcion",
    "no anda",
    "confirmo persistencia",
    "confirmar persistencia",
    "te confirmo persistencia",
    "excepto los sms",
    "excepto el sms",
    "todo funciona bien excepto",
    "todo ok excepto",
)

_PATRONES_AGRADECIMIENTO = (
    "gracias",
    "muchas gracias",
    "ok gracias",
    "genial gracias",
    "perfecto gracias",
    "dale gracias",
)

_PATRONES_RESUELTO = (
    "ya funciona",
    "funciona bien",
    "quedo resuelto",
    "quedó resuelto",
    "problema resuelto",
    "caso cerrado",
    "ya anda",
    "listo ya anda",
)

_PATRONES_DATOS_FALLAN = (
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
    "whatsapp no carga",
    "whatsapp no anda",
    "no le anda internet",
    "no anda internet",
    "no carga internet",
    "sin pdp",
    "sin navegacion",
    "sin navegación",
    "no navega datos",
)

_PATRONES_DATOS_OK = (
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
    "internet anda",
)

_PATRONES_LLAMADAS_OK = (
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
    "llamada sale",
    "puede llamar pero",
)

_PATRONES_LLAMADAS_FALLAN = (
    "llamadas no",
    "no puede llamar",
    "no llama",
    "no puede hacer llamadas",
    "no podemos hacer la llamada",
    "no pudimos hacer la llamada",
)

_PATRONES_ALCANCE = (
    "uruguay",
    "argentina",
    "brasil",
    "paraguay",
    "chile",
    "exterior",
    "extranjero",
    "afuera",
    "otro pais",
    "otro país",
    "saliendo de",
    "en el exterior",
    "fuera del pais",
    "fuera del país",
)

_PATRONES_CONFIRMACION = (
    "ya lo verificamos",
    "lo verificamos",
    "ya lo hicimos",
    "lo hicimos",
    "hecho",
    "ya está",
    "ya esta",
    "listo eso",
    "verificado",
    "verificada",
    "verificamos",
    "revisado",
    "revisada",
    "revisamos",
    "correcto",
    "correcta",
    "confirmado",
    "confirmamos",
    "eso está bien",
    "eso esta bien",
    "está bien",
    "esta bien",
    "todo bien",
    "de acuerdo",
    "exacto",
    "claro",
    "así es",
    "asi es",
    "apn ok",
    "roaming habilitado",
    "roaming activo",
    "jsc activo",
    "reinicio hecho",
    "modo avion hecho",
    "modo avión hecho",
)

_HECHOS_BOOL = frozenset({
    "datos_moviles_activos",
    "apn_configurado",
    "roaming_verificado",
    "roaming_activado_jsc",
    "reinicio_o_modo_avion",
    "alcance_confirmado",
    "zona_unica",
    "multiples_zonas",
    "sim_cambiada",
})

_HECHOS_TRI = frozenset({"datos_ok", "llamadas_ok", "resuelto"})


def _contiene_patron(texto: str, patrones: tuple[str, ...]) -> bool:
    t = texto.lower()
    return any(p in t for p in patrones)


def _es_pregunta(msg: str) -> bool:
    t = msg.lower().strip()
    if "?" in t:
        return True
    return any(
        p in t
        for p in (
            "tenes ",
            "tenés ",
            "tienes ",
            "podes ",
            "podés ",
            "me recomendas",
            "me recomendás",
            "que hago",
            "qué hago",
            "como seguimos",
            "cómo seguimos",
            "esto va a noc",
            "va a noc",
        )
    )


def detectar_intencion_normalizada(
    msg: str,
    *,
    tiene_ticket: bool = False,
    hechos: dict | None = None,
) -> dict[str, Any]:
    """Intención operativa a partir de variantes de lenguaje."""
    t = (msg or "").strip()
    tl = t.lower().rstrip(".!?")
    h = hechos or {}

    if tiene_ticket and _contiene_patron(
        tl, ("novedad", "seguimiento", "estado del ticket", "estado del caso", "como va", "cómo va")
    ):
        return {"tipo": "novedad_ticket", "confianza": 0.85, "fuente": "reglas"}

    if _contiene_patron(tl, _PATRONES_ESTADO_TICKET) or (
        _es_pregunta(t) and any(p in tl for p in ("ticket", "reclamo", "noc", "cargaste", "registraste"))
    ):
        return {"tipo": "estado_ticket", "confianza": 0.95, "fuente": "reglas"}

    if _contiene_patron(tl, ("resumen", "resumime", "resumí", "que hicimos", "qué hicimos", "recapitul")):
        return {"tipo": "resumen_caso", "confianza": 0.9, "fuente": "reglas"}

    if _contiene_patron(tl, ("cerralo", "cerrá", "cierra el ticket", "podes cerrarlo", "podés cerrarlo", "cerrar ticket")):
        return {"tipo": "cerrar_ticket", "confianza": 0.9, "fuente": "reglas"}

    if _contiene_patron(tl, _PATRONES_CORRECCION):
        return {"tipo": "correccion", "confianza": 0.9, "fuente": "reglas"}

    if tl in _PATRONES_AGRADECIMIENTO or tl.startswith("gracias"):
        return {"tipo": "agradecimiento", "confianza": 0.9, "fuente": "reglas"}

    if _es_pregunta(t) and _contiene_patron(
        tl, ("recomendas", "recomendás", "recomiendas", "conviene", "deberia", "debería", "entonces le")
    ):
        return {"tipo": "pregunta_recomendacion", "confianza": 0.85, "fuente": "reglas"}

    if h.get("resuelto") and tl in ("si", "sí", "sip", "ok", "dale", "confirmo"):
        return {"tipo": "confirmar_cierre", "confianza": 0.9, "fuente": "reglas"}

    if h.get("resuelto") and _contiene_patron(tl, _PATRONES_RESUELTO):
        return {"tipo": "caso_resuelto", "confianza": 0.85, "fuente": "reglas"}

    from app.domain.conversacion import mensaje_indica_persistencia_parcial, operador_confirmo_persistencia_explicita

    if mensaje_indica_persistencia_parcial(tl) or operador_confirmo_persistencia_explicita(tl):
        return {"tipo": "persistencia", "confianza": 0.9, "fuente": "reglas"}

    if _contiene_patron(tl, _PATRONES_PERSISTENCIA):
        return {"tipo": "persistencia", "confianza": 0.85, "fuente": "reglas"}

    if _contiene_patron(tl, _PATRONES_CONFIRMACION) and not _es_pregunta(t):
        if len(tl) <= 25 and tl in ("si", "sí", "sip", "ok", "dale", "listo", "bien", "yes"):
            return {"tipo": "confirmacion_paso", "confianza": 0.9, "fuente": "reglas"}
        if any(p in tl for p in _PATRONES_CONFIRMACION):
            return {"tipo": "confirmacion_paso", "confianza": 0.85, "fuente": "reglas"}

    if _contiene_patron(tl, _PATRONES_LLAMADAS_OK) or _contiene_patron(tl, _PATRONES_LLAMADAS_FALLAN):
        return {"tipo": "informe_prueba", "confianza": 0.85, "fuente": "reglas"}

    if len(tl) > 18 and _contiene_patron(tl, _PATRONES_ALCANCE):
        return {"tipo": "informe_alcance", "confianza": 0.8, "fuente": "reglas"}

    if tiene_ticket and len(tl) > 8:
        return {"tipo": "seguimiento_activo", "confianza": 0.5, "fuente": "reglas"}

    return {"tipo": "continuar", "confianza": 0.4, "fuente": "reglas"}


def extraer_hechos_normalizados(msg: str, *, ultimo_bot: str = "") -> dict[str, Any]:
    """Hechos técnicos inferidos de un mensaje (sin depender de frase exacta del playbook)."""
    t = (msg or "").lower().strip()
    bot = (ultimo_bot or "").lower()
    out: dict[str, Any] = {}

    if _contiene_patron(t, _PATRONES_DATOS_FALLAN):
        out["datos_ok"] = False
        out["resuelto"] = False

    for patron in _PATRONES_DATOS_OK:
        if patron in t and not _contiene_patron(t, _PATRONES_DATOS_FALLAN):
            out["datos_ok"] = True
            break

    if _contiene_patron(t, _PATRONES_LLAMADAS_FALLAN):
        out["llamadas_ok"] = False
    elif _contiene_patron(t, _PATRONES_LLAMADAS_OK):
        out["llamadas_ok"] = True
        if _contiene_patron(t, _PATRONES_DATOS_FALLAN):
            out["datos_ok"] = False
            out["resuelto"] = False

    if _contiene_patron(t, _PATRONES_PERSISTENCIA + _PATRONES_CORRECCION):
        out["resuelto"] = False

    from app.domain.conversacion import mensaje_indica_persistencia_parcial, operador_confirmo_persistencia_explicita

    if mensaje_indica_persistencia_parcial(t) or operador_confirmo_persistencia_explicita(t):
        out["resuelto"] = False
        out["persistencia_confirmada"] = operador_confirmo_persistencia_explicita(t)

    if _contiene_patron(t, _PATRONES_RESUELTO) and not _contiene_patron(t, _PATRONES_DATOS_FALLAN):
        from app.domain.conversacion import mensaje_indica_persistencia_parcial

        if not mensaje_indica_persistencia_parcial(t):
            out["resuelto"] = True

    if _contiene_patron(t, _PATRONES_ALCANCE) and (
        len(t) > 18 or _contiene_patron(t, ("datos", "internet", "señal", "senal", "llamadas", "whatsapp"))
    ):
        out["alcance_confirmado"] = True
        if _contiene_patron(t, _PATRONES_DATOS_FALLAN + ("internet", "whatsapp", "navegar")):
            out["datos_ok"] = False

    if _contiene_patron(t, ("afuera", "extranjero", "exterior", "uruguay", "brasil", "argentina")) and _contiene_patron(
        t, ("internet", "datos", "whatsapp", "navegar", "no anda", "no le anda")
    ):
        out["alcance_confirmado"] = True
        out["datos_ok"] = False
        out["resuelto"] = False

    if "apn" in bot or "apn" in t:
        if _contiene_patron(t, _PATRONES_CONFIRMACION + ("apn ok", "apn configurado", "configure")):
            out["apn_configurado"] = True
        if _contiene_patron(t, _PATRONES_DATOS_FALLAN):
            out["apn_configurado"] = True
            out["datos_ok"] = False

    if ("jsc" in bot or "roaming" in bot) and _contiene_patron(
        t, ("habilitado", "habilitados", "activo", "activos", "jsc activo", "roaming habilitado", "roaming activo")
    ):
        out["roaming_verificado"] = True

    if _contiene_patron(t, ("modo avion", "modo avión", "reinicio", "reinici", "reiniciado")):
        out["reinicio_o_modo_avion"] = True
    if ("modo avión" in bot or "modo avion" in bot or "reinici" in bot) and _contiene_patron(
        t, _PATRONES_PASO_EJECUTADO + _PATRONES_PERSISTENCIA
    ):
        out["reinicio_o_modo_avion"] = True
        if _contiene_patron(
            t,
            _PATRONES_PERSISTENCIA
            + ("sin solucion", "sin solución", "sigue", "no funcion", "no anda", "persiste"),
        ):
            out["resuelto"] = False

    if _contiene_patron(
        t,
        (
            "datos moviles activos",
            "datos móviles activos",
            "datos activados",
            "datos habilitados",
            "datos móviles habilitados",
            "datos moviles habilitados",
        ),
    ):
        out["datos_moviles_activos"] = True

    if _contiene_patron(
        t, ("roaming habilitado", "roaming activo", "jsc activo", "itinerancia habilitada", "itinerancia activa")
    ):
        out["roaming_verificado"] = True

    return out


def _fusionar_hechos(base: dict, nuevos: dict) -> dict:
    out = dict(base)
    for k, v in nuevos.items():
        if k not in out or out[k] is None:
            out[k] = v
        elif k in _HECHOS_TRI and v is False:
            out[k] = False
        elif k in _HECHOS_BOOL and v is True:
            out[k] = True
    return out


def _hecho_pendiente_por_bot(bot: str, hechos: dict) -> str | None:
    """Clave de hecho que el último mensaje del bot esperaba y aún no quedó registrada."""
    if ("modo avión" in bot or "modo avion" in bot or "reinici" in bot) and not hechos.get("reinicio_o_modo_avion"):
        return "reinicio_o_modo_avion"
    if "llamada" in bot and hechos.get("llamadas_ok") is None:
        return "llamadas_ok"
    if "apn" in bot and hechos.get("apn_configurado") is None:
        return "apn_configurado"
    if ("jsc" in bot or "roaming" in bot) and hechos.get("roaming_verificado") is None:
        return "roaming_verificado"
    if (
        ("una sola zona" in bot or "varias ubicaciones" in bot or "varias zonas" in bot)
        and hechos.get("zona_unica") is None
        and hechos.get("multiples_zonas") is None
    ):
        return "zona"
    return None


def mensaje_confirma_paso_operativo(msg: str) -> bool:
    """Operador confirma haber ejecutado el paso sugerido (sin afirmar resolución)."""
    t = (msg or "").lower().strip().rstrip(".!?")
    if not t:
        return False
    if _contiene_patron(t, _PATRONES_PASO_EJECUTADO + _PATRONES_CONFIRMACION):
        return True
    return len(t) <= 25 and t in ("si", "sí", "sip", "ok", "dale", "listo", "bien", "yes")


def mensaje_reporta_persistencia(msg: str) -> bool:
    """Operador indica que ejecutó el paso pero el problema persiste."""
    t = (msg or "").lower().strip()
    if _contiene_patron(t, _PATRONES_PERSISTENCIA):
        return True
    return _contiene_patron(t, _PATRONES_PASO_EJECUTADO) and _contiene_patron(
        t,
        _PATRONES_PERSISTENCIA
        + ("sin solucion", "sin solución", "sin resultado", "no funcion", "no anda", "sigue"),
    )


def necesita_interpretacion_ia(
    msg: str,
    intencion: dict,
    hechos: dict,
    *,
    ultimo_bot: str = "",
) -> bool:
    """True si el mensaje es ambiguo y conviene pedir interpretación estructurada."""
    t = (msg or "").strip()
    bot = (ultimo_bot or "").lower()
    if len(t) < 4:
        return False
    conf = float(intencion.get("confianza") or 0)
    pendiente = _hecho_pendiente_por_bot(bot, hechos)
    if intencion.get("tipo") in ("confirmacion_paso", "persistencia") and pendiente:
        return True
    if conf >= 0.85 and not pendiente:
        return False
    if intencion.get("tipo") in ("estado_ticket", "correccion", "agradecimiento"):
        return False
    if _contiene_patron(t.lower(), _PATRONES_CONFIRMACION) and len(t) <= 30:
        return False
    # Triaje inicial con línea + síntoma: no hace falta intérprete
    if re.search(r"\d{10,11}", t) and len(t.split()) >= 5:
        return False
    # Si el playbook hizo una pregunta cerrada y el operador respondió en lenguaje
    # libre, usamos IA para mapear la respuesta al hecho pendiente antes de repreguntar.
    if (
        ("una sola zona" in bot or "varias ubicaciones" in bot or "varias zonas" in bot)
        and hechos.get("zona_unica") is None
        and hechos.get("multiples_zonas") is None
    ):
        return True
    if "llamada" in bot and hechos.get("llamadas_ok") is None:
        return True
    if "apn" in bot and hechos.get("apn_configurado") is None:
        return True
    if ("modo avión" in bot or "modo avion" in bot or "reinici" in bot) and hechos.get("reinicio_o_modo_avion") is None:
        return True
    if ("jsc" in bot or "roaming" in bot) and hechos.get("roaming_verificado") is None:
        return True
    # Mensaje sustantivo sin clasificación clara
    if conf < 0.7 and len(t.split()) >= 4:
        return True
    if _es_pregunta(t) and intencion.get("tipo") == "continuar":
        return True
    if intencion.get("tipo") == "seguimiento_activo" and conf <= 0.55:
        return True
    return False


def interpretar_mensaje_estructurado(
    historial: list[dict],
    *,
    ultimo_bot: str = "",
    hechos_prev: dict | None = None,
) -> dict[str, Any] | None:
    """Interpretación IA estructurada para mensajes ambiguos. Retorna None si falla."""
    ultimo = ""
    for m in reversed(historial):
        if m.get("rol") == "usuario":
            ultimo = (m.get("contenido") or "").strip()
            break
    if not ultimo:
        return None

    hist_txt = "\n".join(
        f"{'OP' if m.get('rol') == 'usuario' else 'BOT'}: {m.get('contenido', '')}"
        for m in historial[-8:]
    )
    sys = (
        "Sos intérprete operativo de consola NOC telco. "
        "Devolvé SOLO JSON válido con claves: intencion, hechos, confianza, aclaracion. "
        "intencion: uno de estado_ticket, resumen_caso, cerrar_ticket, novedad_ticket, "
        "correccion, agradecimiento, pregunta_recomendacion, persistencia, confirmacion_paso, "
        "informe_prueba, informe_alcance, seguimiento_activo, continuar. "
        "hechos: objeto con claves opcionales booleanas "
        "datos_ok, llamadas_ok, resuelto, apn_configurado, roaming_verificado, "
        "reinicio_o_modo_avion, datos_moviles_activos, alcance_confirmado, "
        "zona_unica, multiples_zonas. "
        "Usá true/false/null. confianza: 0.0-1.0. "
        "aclaracion: string corto si confianza < 0.6, sino vacío. "
        "No inventes ticket_id ni pasos. Interpretá lenguaje técnico e informal. "
        "Si el bot preguntó si ocurre en una sola zona o en varias, mapeá la respuesta "
        "a zona_unica o multiples_zonas aunque el operador use sinónimos."
    )
    user = (
        f"HISTORIAL:\n{hist_txt}\n\n"
        f"ULTIMO_BOT:\n{ultimo_bot}\n\n"
        f"HECHOS_PREVIOS:\n{hechos_prev or {}}\n\n"
        f"MENSAJE_OPERADOR:\n{ultimo}\n\n"
        "Respondé JSON."
    )
    try:
        raw = chat_completion(
            [{"role": "system", "content": sys}, {"role": "user", "content": user}],
            temperature=0.1,
            json_mode=True,
        )
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        data.setdefault("fuente", "ia")
        data.setdefault("confianza", 0.5)
        return data
    except Exception as exc:
        logger.warning("interpretar_mensaje_estructurado falló: %s", exc)
        return None


def aplicar_interpretacion(
    hechos: dict,
    intencion: dict,
    interpretacion: dict,
) -> tuple[dict, dict]:
    """Fusiona interpretación IA/reglas en hechos e intención."""
    out_hechos = dict(hechos)
    out_int = dict(intencion)
    conf = float(interpretacion.get("confianza") or 0)
    if conf < 0.55:
        return out_hechos, out_int

    tipo = interpretacion.get("intencion") or interpretacion.get("tipo")
    if tipo and conf >= 0.6:
        out_int["tipo"] = tipo
        out_int["confianza"] = conf
        out_int["fuente"] = interpretacion.get("fuente", "ia")

    hechos_ia = interpretacion.get("hechos") or {}
    if isinstance(hechos_ia, dict):
        limpios = {k: v for k, v in hechos_ia.items() if v is not None}
        out_hechos = _fusionar_hechos(out_hechos, limpios)

    if interpretacion.get("aclaracion") and conf < 0.6:
        out_int["aclaracion"] = interpretacion["aclaracion"]

    return out_hechos, out_int


def perfil_operador(historial: list[dict]) -> str:
    """Detecta si el operador usa lenguaje técnico o informal."""
    texto = " ".join(
        (m.get("contenido") or "").lower() for m in historial if m.get("rol") == "usuario"
    )
    tecnico = sum(
        1
        for kw in (
            "apn",
            "jsc",
            "roaming",
            "pdp",
            "noc",
            "itinerancia",
            "msisdn",
            "iccid",
            "modo avion",
            "modo avión",
            "registro en red",
        )
        if kw in texto
    )
    informal = sum(
        1
        for kw in ("no le anda", "afuera", "whatsapp", "internet", "el cliente", "sigue igual")
        if kw in texto
    )
    if tecnico >= informal + 1:
        return "tecnico"
    if informal > tecnico:
        return "informal"
    return "mixto"
