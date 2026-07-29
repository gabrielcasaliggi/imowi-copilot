"""Playbooks N1 — Cooperativa Batán (internet radio/ADSL + móvil IMOVI)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PasoPlaybook:
    id: str
    pregunta: str
    palabras_ok: tuple[str, ...] = (
        "si", "sí", "ok", "listo", "hecho", "verificado", "ya", "mejoro", "mejoró",
    )
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
    "internet_radio": [
        PasoPlaybook(
            "reinicio_cpe",
            "Internet Ecolan por radio/antena: ¿podés apagar el equipo de radio (CPE) "
            "y el router 30 segundos, encender primero la radio y después el router, "
            "y decirme si vuelve la conexión?",
        ),
        PasoPlaybook(
            "led_enlace",
            "¿El LED de enlace/señal de la radio está fijo (sin parpadeo de alarma)? "
            "Respondé sí o no.",
        ),
        PasoPlaybook(
            "linea_vista",
            "¿La antena tiene vista libre hacia la torre (sin obstáculos nuevos) "
            "y el cable de alimentación está bien conectado?",
        ),
        PasoPlaybook(
            "wifi_vs_cable",
            "¿Falla solo el WiFi o también si conectás una PC por cable al router?",
        ),
        PasoPlaybook(
            "zona_vecinos",
            "¿Solo te pasa a vos o también a vecinos de la misma zona? "
            "Si sigue igual, te derivo con un agente.",
        ),
    ],
    "internet_adsl": [
        PasoPlaybook(
            "reinicio_modem_adsl",
            "Internet ADSL (línea telefónica): ¿podés apagar el módem ADSL 30 segundos, "
            "encenderlo y esperar 2 minutos a que sincronice? ¿Volvió?",
        ),
        PasoPlaybook(
            "luces_adsl",
            "¿La luz de DSL/Internet del módem quedó fija (sin alarma roja)? Respondé sí o no.",
        ),
        PasoPlaybook(
            "filtro_splitter",
            "Si tenés teléfono fijo: ¿el filtro/splitter está bien colocado "
            "y no hay otros aparatos en la misma toma sin filtro?",
        ),
        PasoPlaybook(
            "wifi_vs_cable",
            "¿El problema es solo WiFi o también falla por cable al módem/router?",
        ),
        PasoPlaybook(
            "persistencia",
            "Si sigue sin servicio después de estos pasos, te derivo con un agente. "
            "¿Querés que te pase con alguien?",
        ),
    ],
    "internet": [
        PasoPlaybook(
            "tipo_acceso",
            "Para internet Ecolan: ¿tu servicio es por radio/antena (inalámbrico) "
            "o por línea telefónica (ADSL)?",
        ),
    ],
    "movil": [
        PasoPlaybook(
            "reinicio_imovi",
            "Para móvil IMOVI: ¿reiniciaste el teléfono y confirmás si vuelve la señal o los datos?",
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
            "¿Tu consulta es por internet (radio o ADSL), móvil IMOVI, o factura/deuda?",
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
            "adsl",
            "línea telefónica",
            "linea telefonica",
            "par de cobre",
            "modem adsl",
            "módem adsl",
            "splitter",
            "filtro adsl",
        )
    ):
        return "internet_adsl"
    if any(
        k in t
        for k in (
            "radio",
            "antena",
            "cpe",
            "inalambr",
            "inalámbr",
            "torre",
            "ftth",
            "wireless",
            "enlace",
        )
    ):
        return "internet_radio"
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
            "internet",
        )
    ):
        return "internet"
    if any(
        k in t
        for k in (
            "imovi",
            "imovu",
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
            "móvil",
            "movil",
        )
    ):
        return "movil"
    if servicio_abonado == "internet":
        return "internet"
    if servicio_abonado == "movil":
        return "movil"
    return "general"


def refinar_intencion_internet(texto: str) -> str | None:
    """Tras preguntar radio vs ADSL, afina el playbook."""
    t = (texto or "").lower()
    if any(k in t for k in ("adsl", "línea", "linea", "telefono", "teléfono", "cobre", "splitter")):
        return "internet_adsl"
    if any(k in t for k in ("radio", "antena", "cpe", "inalambr", "inalámbr", "torre", "wireless", "enlace")):
        return "internet_radio"
    return None


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
