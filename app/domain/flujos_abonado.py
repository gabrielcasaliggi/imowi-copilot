"""Playbooks N1 para abonado final (internet Ecolan + móvil)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PasoPlaybook:
    id: str
    pregunta: str
    palabras_ok: tuple[str, ...] = ("si", "sí", "ok", "listo", "hecho", "verificado", "ya")
    palabras_fail: tuple[str, ...] = ("no", "sigue", "persiste", "igual", "nada", "falla")


PLAYBOOKS: dict[str, list[PasoPlaybook]] = {
    "corte_deuda": [
        PasoPlaybook(
            "confirmar_deuda",
            "Detectamos un saldo pendiente en tu cuenta. ¿Querés que te indique cómo regularizar el servicio?",
        ),
        PasoPlaybook(
            "medios_pago",
            "Podés abonar por los medios habituales de la cooperativa. Cuando esté acreditado, el servicio se rehabilita automáticamente. ¿Necesitás hablar con un agente?",
        ),
    ],
    "internet": [
        PasoPlaybook(
            "reinicio_modem",
            "Para internet: ¿podés apagar el módem/router 30 segundos, encenderlo y decirme si vuelve la conexión?",
        ),
        PasoPlaybook(
            "wifi_cable",
            "¿Probaste conectar una PC por cable al router? ¿El problema es solo WiFi o también por cable?",
        ),
        PasoPlaybook(
            "luces_modem",
            "¿Las luces del módem están normales (sin alarma roja)? Respondé sí o no.",
        ),
    ],
    "movil": [
        PasoPlaybook(
            "reinicio_equipo",
            "Para el móvil: ¿reiniciaste el teléfono y confirmás si vuelve la señal/datos?",
        ),
        PasoPlaybook(
            "modo_avion",
            "Activá modo avión 15 segundos y desactiválo. ¿Mejoró?",
        ),
        PasoPlaybook(
            "otra_zona",
            "¿El problema es en una sola zona o en varias ubicaciones?",
        ),
    ],
    "general": [
        PasoPlaybook(
            "describir",
            "Contame brevemente el problema: ¿es internet fijo, móvil, o un corte de servicio?",
        ),
    ],
}


def clasificar_intencion(texto: str, servicio_abonado: str = "") -> str:
    t = (texto or "").lower()
    if any(k in t for k in ("deuda", "corte", "suspend", "factur", "pago", "saldo")):
        return "corte_deuda"
    if any(k in t for k in ("wifi", "modem", "módem", "router", "fibra", "ecolan", "internet fijo", "sin internet")):
        return "internet"
    if any(k in t for k in ("señal", "senal", "datos movil", "datos móvil", "chip", "llamada", "sms", "4g", "5g")):
        return "movil"
    if servicio_abonado == "internet":
        return "internet"
    if servicio_abonado == "movil":
        return "movil"
    return "general"


def respuesta_paso_ok(texto: str) -> bool | None:
    t = (texto or "").lower().strip()
    if not t:
        return None
    oks = ("si", "sí", "ok", "listo", "hecho", "verificado", "ya", "mejoró", "mejoro", "anda", "funciona")
    fails = ("no", "sigue", "persiste", "igual", "nada", "falla", "mal", "peor")
    if any(w in t for w in fails):
        return False
    if any(w in t for w in oks):
        return True
    return None


def pide_humano(texto: str) -> bool:
    t = (texto or "").lower()
    return any(
        k in t
        for k in (
            "humano",
            "agente",
            "persona",
            "operador",
            "hablar con alguien",
            "asesor",
        )
    )
