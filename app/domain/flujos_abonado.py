"""Playbooks N1 para abonado final (internet Ecolan + móvil) — Cooperativa Batán."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PasoPlaybook:
    id: str
    pregunta: str
    palabras_ok: tuple[str, ...] = ("si", "sí", "ok", "listo", "hecho", "verificado", "ya", "mejoro", "mejoró")
    palabras_fail: tuple[str, ...] = ("no", "sigue", "persiste", "igual", "nada", "falla", "mal")


PLAYBOOKS: dict[str, list[PasoPlaybook]] = {
    "corte_deuda": [
        PasoPlaybook(
            "confirmar_deuda",
            "Tu cuenta tiene un saldo pendiente y el servicio puede estar limitado. "
            "¿Querés que te indique cómo regularizarlo?",
        ),
        PasoPlaybook(
            "medios_pago",
            "Podés abonar por los medios habituales de Cooperativa Batán. "
            "Cuando se acredite, el servicio se rehabilita solo. "
            "¿Necesitás hablar con un agente?",
        ),
    ],
    "internet": [
        PasoPlaybook(
            "reinicio_modem",
            "Vamos con internet Ecolan. ¿Podés apagar el módem 30 segundos, encenderlo "
            "y decirme si vuelve la conexión?",
        ),
        PasoPlaybook(
            "luces_modem",
            "¿Las luces del módem están normales (sin alarma roja fija)? Respondé sí o no.",
        ),
        PasoPlaybook(
            "wifi_cable",
            "¿El problema es solo WiFi o también falla si conectás por cable al router?",
        ),
        PasoPlaybook(
            "zona_vecinos",
            "¿Solo te pasa a vos o también a vecinos / en otra habitación? "
            "Si sigue igual, te derivo con un agente.",
        ),
    ],
    "movil": [
        PasoPlaybook(
            "reinicio_equipo",
            "Para el móvil: ¿reiniciaste el teléfono y confirmás si vuelve la señal o los datos?",
        ),
        PasoPlaybook(
            "modo_avion",
            "Activá modo avión 15 segundos y desactiválo. ¿Mejoró?",
        ),
        PasoPlaybook(
            "otra_ubicacion",
            "¿El problema es en una sola zona o en varias ubicaciones? "
            "Si sigue fallando, te paso con un agente.",
        ),
    ],
    "general": [
        PasoPlaybook(
            "menu_servicio",
            "Hola, soy el asistente de Cooperativa Batán. "
            "¿Tu consulta es por internet Ecolan, móvil, o factura/deuda?",
        ),
    ],
}


def clasificar_intencion(texto: str, servicio_abonado: str = "") -> str:
    t = (texto or "").lower()
    if any(k in t for k in ("deuda", "corte", "suspend", "factur", "pago", "saldo", "boleta")):
        return "corte_deuda"
    if any(
        k in t
        for k in (
            "wifi",
            "modem",
            "módem",
            "router",
            "fibra",
            "ecolan",
            "internet fijo",
            "sin internet",
            "no anda internet",
        )
    ):
        return "internet"
    if any(
        k in t
        for k in (
            "señal",
            "senal",
            "datos movil",
            "datos móvil",
            "chip",
            "llamada",
            "sms",
            "4g",
            "5g",
            "celular",
        )
    ):
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
    palabras_ok = (
        "si", "sí", "ok", "listo", "hecho", "verificado", "ya",
        "mejoro", "mejoró", "volvio", "volvió", "anda",
    )
    palabras_fail = ("no", "sigue", "persiste", "igual", "nada", "falla", "mal", "sigue sin")
    if any(p in t for p in palabras_fail):
        return False
    if any(p in t for p in palabras_ok):
        return True
    return None


def pide_humano(texto: str) -> bool:
    t = (texto or "").lower()
    return any(
        k in t
        for k in (
            "agente",
            "humano",
            "operador",
            "persona",
            "hablar con",
            "atencion",
            "atención",
            "tecnico",
            "técnico",
            "representante",
        )
    )
