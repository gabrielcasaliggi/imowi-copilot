"""Playbooks N1 — Cooperativa Batán / Ecolan Tecnologías.

Catálogo:
- Internet FTTH (fibra), Wireless/radio, ADSL
- Telefonía móvil IMOVI y telefonía fija
- Ecolan B2B (Data Center, VMs, enlaces dedicados, housing/hosting)
- Facturación / pagos QR Fiserv
- Trámites digitales batan.coop
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import BOT_DISPLAY_NAME, PRODUCT_DISPLAY_NAME


@dataclass(frozen=True)
class PasoPlaybook:
    id: str
    pregunta: str
    palabras_ok: tuple[str, ...] = (
        "si", "sí", "ok", "listo", "hecho", "verificado", "ya", "mejoro", "mejoró",
        "volvio", "volvió", "anda", "funciona", "anduvo", "perfecto",
    )
    palabras_fail: tuple[str, ...] = (
        "no", "sigue", "persiste", "igual", "nada", "falla", "mal", "sigue sin",
        "tampoco", "peor", "no funciona", "no anda",
    )


# Tags de ticket (PostgreSQL / métricas)
TAG_POR_INTENCION: dict[str, str] = {
    "corte_deuda": "[PAGOS_QR]",
    "facturacion": "[PAGOS_QR]",
    "internet_ftth": "[TEC_FTTH]",
    "internet_radio": "[TEC_WIRELESS]",
    "internet_adsl": "[TEC_ADSL]",
    "internet": "[TEC_FTTH]",
    "internet_lento": "[TEC_FTTH]",
    "wifi": "[TEC_WIRELESS]",
    "movil": "[TEL_MOVIL]",
    "movil_datos": "[TEL_MOVIL]",
    "movil_llamadas": "[TEL_MOVIL]",
    "telefono_fija": "[TEL_FIJA]",
    "ecolan_b2b": "[ECOLAN_B2B]",
    "alta_plan": "[HANDOFF_HUMANO]",
    "portal_tramites": "[HANDOFF_HUMANO]",
    "turno_campo": "[HANDOFF_HUMANO]",
    "general": "[HANDOFF_HUMANO]",
    "no_tecnico": "[HANDOFF_HUMANO]",
}


# ---------------------------------------------------------------------------
# PLAYBOOKS
# ---------------------------------------------------------------------------

PLAYBOOKS: dict[str, list[PasoPlaybook]] = {
    "corte_deuda": [
        PasoPlaybook(
            "confirmar_deuda",
            "Puede haber saldo pendiente. ¿Me pasás el DNI o N.º de socio para ayudarte con el pago?",
        ),
        PasoPlaybook(
            "medios_pago_qr",
            "Podés pagar con el QR Fiserv de la factura (Mercado Pago, MODO, etc.). "
            "Al acreditarse, el servicio se reactiva solo. ¿Pudiste pagar?",
        ),
        PasoPlaybook(
            "derivar_pagos",
            "Si el pago no figura, ¿querés que te derive con facturación?",
        ),
    ],
    "facturacion": [
        PasoPlaybook(
            "pedir_dni_factura",
            "Para ver saldo o factura necesito el DNI del titular o N.º de socio. ¿Me lo pasás?",
        ),
        PasoPlaybook(
            "tipo_consulta_factura",
            "¿Es por saldo, copia de factura, pago con QR, u otra consulta?",
        ),
        PasoPlaybook(
            "medios_pago_qr_factura",
            "Para pagar usá el QR Fiserv de la factura con cualquier billetera. ¿Te sirvió?",
        ),
        PasoPlaybook(
            "derivar_factura",
            "Si hace falta revisar la cuenta adentro, ¿querés que te derive?",
        ),
    ],
    "internet_ftth": [
        PasoPlaybook("energia_ont", "Dale, arrancamos por fibra. ¿La cajita blanca tiene luces encendidas?"),
        PasoPlaybook("luces_los", "¿La luz PON está verde fija y la LOS apagada, o ves alguna en rojo?"),
        PasoPlaybook(
            "reinicio_ont",
            "Desenchufá ONT y router 30 segundos; prendé primero la ONT y después el router. ¿Volvió?",
        ),
        PasoPlaybook("cable_fibra", "¿El cable amarillo está bien enchufado, sin dobleces fuertes?"),
        PasoPlaybook("wifi_vs_cable_ftth", "¿Falla también por cable al router, o solo el WiFi?"),
        PasoPlaybook(
            "turno_campo_ftth",
            "Con esto ya no lo resolvemos a distancia. ¿Querés que abra un ticket para visita técnica?",
        ),
    ],
    "internet_radio": [
        PasoPlaybook("poe_antena", "Ok, por antena. ¿La fuente PoE tiene la lucecita prendida?"),
        PasoPlaybook(
            "reinicio_cpe",
            "Reiniciá antena y router 30 segundos; prendé primero la antena. ¿Volvió?",
        ),
        PasoPlaybook("led_enlace", "¿El LED de enlace está fijo o parpadea/rojo?"),
        PasoPlaybook("linea_vista", "¿La antena sigue con vista libre a la torre?"),
        PasoPlaybook("zona_vecinos", "¿Les pasa también a vecinos, o solo en tu casa?"),
        PasoPlaybook(
            "turno_campo_radio",
            "Si sigue igual, hace falta técnico. ¿Abro el ticket para una visita?",
        ),
    ],
    "internet_adsl": [
        PasoPlaybook("tono_linea", "Vamos con ADSL. ¿El teléfono fijo tiene tono?"),
        PasoPlaybook("filtro_splitter", "¿El microfiltro/splitter está bien colocado?"),
        PasoPlaybook(
            "reinicio_modem_adsl",
            "Apagá el módem 30 segundos, prendelo y esperá un rato. ¿Volvió?",
        ),
        PasoPlaybook("luces_adsl", "¿La luz DSL/Sync quedó fija o sigue parpadeando?"),
        PasoPlaybook("cable_telefono", "¿Probaste el módem en la toma principal de la calle?"),
        PasoPlaybook("persistencia_adsl", "Si no vuelve, ¿querés que te derive con un técnico?"),
    ],
    "internet": [
        PasoPlaybook(
            "sintoma_internet",
            "Entiendo. ¿No te carga nada, anda lento, se corta, o es solo el WiFi?",
        ),
        PasoPlaybook("alcance_internet", "¿Te pasa en todos los dispositivos o solo en uno?"),
        PasoPlaybook(
            "tipo_acceso",
            "¿Tenés fibra (cajita blanca), antena en el techo, o internet por teléfono (ADSL)?",
        ),
    ],
    "internet_lento": [
        PasoPlaybook("cuantos_dispositivos", "¿Cuántos equipos hay conectados al WiFi ahora?"),
        PasoPlaybook("horario_lento", "¿Es lento todo el día o más a la tarde/noche?"),
        PasoPlaybook("test_velocidad", "Si podés, hacé un test por cable en fast.com y decime cuánto da."),
        PasoPlaybook("reinicio_lento", "Reiniciá módem/router 30 segundos y probá de nuevo. ¿Mejoró?"),
        PasoPlaybook("comparar_plan", "Si sigue bajo, ¿querés que te pase con un agente?"),
    ],
    "wifi": [
        PasoPlaybook("zona_wifi", "¿El WiFi falla en toda la casa o solo lejos del router?"),
        PasoPlaybook("otros_dispositivos_wifi", "¿Les pasa a todos los equipos o solo a uno?"),
        PasoPlaybook("reinicio_router_wifi", "¿Reiniciaste el router 30 segundos? ¿Mejoró?"),
        PasoPlaybook("banda_wifi", "Si tenés 2.4 y 5 GHz, ¿probaste la otra red?"),
        PasoPlaybook("canal_interferencia", "¿Podés alejar el router de microondas u otros equipos?"),
        PasoPlaybook("derivar_wifi", "Si sigue mal, ¿querés que te derive?"),
    ],
    "movil": [
        PasoPlaybook("sintoma_movil", "¿Qué te pasa con el móvil: sin señal, sin datos, o no podés llamar?"),
        PasoPlaybook("datos_roaming_check", "¿Datos móviles activos y modo avión apagado?"),
        PasoPlaybook("reinicio_imovi", "¿Probaste reiniciar el teléfono?"),
        PasoPlaybook("modo_avion", "Modo avión 15 segundos y desactivalo. ¿Volvió?"),
        PasoPlaybook("apn_imovi", "El APN debería ser internet.coopbatan.ar. ¿Está así?"),
        PasoPlaybook("otra_sim_o_tel", "Si podés, ¿probaste esa SIM en otro teléfono?"),
        PasoPlaybook("otra_ubicacion", "¿Te pasa solo en un lugar o en varios? ¿Querés que te derive?"),
    ],
    "movil_datos": [
        PasoPlaybook("datos_activados", "¿Datos móviles prendidos y sin modo avión?"),
        PasoPlaybook("consumo_paquete", "¿Te quedan datos del abono?"),
        PasoPlaybook("apn_datos", "Revisá el APN: internet.coopbatan.ar. ¿Quedó bien?"),
        PasoPlaybook("roaming_datos", "¿Estás en tu zona habitual o de viaje?"),
        PasoPlaybook("prueba_wifi_off", "Apagá el WiFi del celular y probá solo datos. ¿Navega?"),
        PasoPlaybook("derivar_datos", "Si sigue, ¿querés que te derive?"),
    ],
    "movil_llamadas": [
        PasoPlaybook("tipo_problema_llamada", "¿No podés llamar, no te entran, o se cortan?"),
        PasoPlaybook("reinicio_llamadas", "Reiniciá y probá una llamada. ¿Anduvo?"),
        PasoPlaybook("modo_avion_llamadas", "Modo avión 15 segundos y volvé a probar. ¿Mejoró?"),
        PasoPlaybook("otra_ubicacion_llamadas", "¿Te pasa en una sola zona o en varios lados?"),
        PasoPlaybook("derivar_llamadas", "Si sigue, ¿querés que te derive?"),
    ],
    "telefono_fija": [
        PasoPlaybook("tono_fija", "¿Al descolgar el fijo hay tono?"),
        PasoPlaybook("cableado_fija", "¿El cable está bien en la toma?"),
        PasoPlaybook("derivar_fija", "Si no hay tono, ¿querés que te derive?"),
    ],
    "ecolan_b2b": [
        PasoPlaybook(
            "tipo_ecolan",
            "Te ayudo con Ecolan. ¿Es PBX, Cloud/VM, housing/hosting o enlace dedicado?",
        ),
        PasoPlaybook("impacto_sla", "¿Hay un servicio caído ahora o es una consulta/cotización?"),
        PasoPlaybook("derivar_ecolan", "Estos casos los toma un especialista. ¿Te derivo?"),
    ],
    "alta_plan": [
        PasoPlaybook("tipo_alta", "¿Alta nueva o cambio de plan? ¿Internet, móvil u otro?"),
        PasoPlaybook("zona_comercial", "¿En qué barrio o localidad lo necesitás?"),
        PasoPlaybook("derivar_comercial", "Te paso con comercial. ¿Te derivo?"),
    ],
    "portal_tramites": [
        PasoPlaybook("info_batan_coop", "También está batan.coop. ¿Qué trámite necesitás?"),
        PasoPlaybook("derivar_tramites", "Si hace falta operador, ¿querés que te derive?"),
    ],
    "turno_campo": [
        PasoPlaybook("confirmar_turno", "Para la visita hace falta un mayor de edad. ¿Pueden recibirla?"),
        PasoPlaybook("derivar_agenda", "Un agente te ofrece horarios. ¿Abro el ticket de turno?"),
    ],
    "general": [
        PasoPlaybook(
            "menu_servicio",
            f"Hola, soy {BOT_DISPLAY_NAME}, de {PRODUCT_DISPLAY_NAME}. "
            "¿En qué te ayudo: internet, móvil, factura o algo más?",
        ),
        PasoPlaybook(
            "detalle_problema",
            "Contame un poco más qué te está pasando y lo vemos paso a paso.",
        ),
    ],
    "no_tecnico": [
        PasoPlaybook(
            "ampliar_reclamo",
            "Dale, contame un poco más para ayudarte o derivarte al área correcta.",
        ),
        PasoPlaybook(
            "tipo_reclamo",
            "¿Es por factura o pago, plan/alta/baja, un reclamo formal, o otra consulta?",
        ),
        PasoPlaybook(
            "dato_cliente",
            "¿Me pasás DNI o N.º de socio para ubicar tu cuenta?",
        ),
        PasoPlaybook(
            "derivar_area",
            "Con eso te derivo al área que corresponde. ¿Querés que abra el ticket?",
        ),
    ],
}


# ---------------------------------------------------------------------------
# CLASIFICACIÓN / HELPERS
# ---------------------------------------------------------------------------

def tag_para_intencion(intencion: str) -> str:
    return TAG_POR_INTENCION.get((intencion or "").strip(), "[HANDOFF_HUMANO]")


def clasificar_intencion(texto: str, servicio_abonado: str = "") -> str:
    t = (texto or "").lower()

    if any(k in t for k in (
        "data center", "datacenter", "ecolan", "central virtual", "pbx",
        "housing", "hosting", "maquina virtual", "máquina virtual", " cloud",
        "enlace dedicado", "starlink", "ip fija", "vpn sucursal", "sla",
    )):
        return "ecolan_b2b"

    if any(k in t for k in (
        "batan.coop", "tramite", "trámite", "portal web", "facturacion electronica",
        "facturación electrónica",
    )):
        return "portal_tramites"

    if any(k in t for k in (
        "deuda", "corte", "suspend", "factur", "pago", "saldo", "boleta",
        "cuenta corriente", "resumen", "recibo", "qr", "fiserv", "mercado pago",
    )):
        if any(k in t for k in ("copia", "resumen", "comprobante", "factura")):
            return "facturacion"
        return "corte_deuda"

    if any(k in t for k in (
        "dar de alta", "alta", "cambio de plan", "cambiar plan", "mejorar plan",
        "contratar", "baja", "quiero el plan",
    )):
        return "alta_plan"

    if any(k in t for k in (
        "telefono fijo", "teléfono fijo", "linea fija", "línea fija",
        "telefonia fija", "telefonía fija", "sin tono",
    )):
        return "telefono_fija"

    if any(k in t for k in (
        "adsl", "par de cobre", "modem adsl", "módem adsl", "splitter",
        "filtro adsl", "microfiltro",
    )):
        return "internet_adsl"

    if any(k in t for k in (
        "fibra", "ftth", "fibra optica", "fibra óptica", "ont",
        "cable amarillo", "pon", "gpon", "nap", "olt",
    )):
        return "internet_ftth"

    if any(k in t for k in (
        "radio", "antena", "cpe", "inalambr", "inalámbr", "torre",
        "wireless", "enlace", "poe", "inyector",
    )):
        return "internet_radio"

    if any(k in t for k in (
        "lento", "lenta", "velocidad", "speed", "tarda", "demora",
        "baja velocidad", "muy lento", "anda lento",
    )):
        return "internet_lento"

    if any(k in t for k in (
        "wifi", "wi-fi", "señal wifi", "no llega wifi", "wifi no funciona",
    )):
        return "wifi"

    if any(k in t for k in (
        "modem", "módem", "router", "internet fijo",
        "sin internet", "no anda internet", "internet", "no navego",
        "no cargo", "pagina", "página",
    )):
        return "internet"

    if any(k in t for k in (
        "datos movil", "datos móvil", "sin datos", "no tengo datos",
        "datos no funcionan", "internet del celular", "apn",
    )):
        return "movil_datos"

    if any(k in t for k in (
        "llamada", "sms", "no puedo llamar", "no me llegan llamadas",
        "se cortan las llamadas", "mensaje de texto",
    )):
        return "movil_llamadas"

    if any(k in t for k in (
        "imovi", "imovu", "señal", "senal",
        "chip", "4g", "5g", "celular", "móvil", "movil",
        "sim", "linea movil", "línea móvil",
    )):
        return "movil"

    if any(k in t for k in (
        "reclamo formal", "reclamo legal", "queja formal", "area legal",
        "área legal", "defensa del consumidor", "baja definitiva",
        "no es tecnico", "no es técnico", "tema comercial", "tema administrativo",
        "consulta general", "otro problema", "tengo un problema con",
    )):
        return "no_tecnico"

    if servicio_abonado in ("internet", "ambos"):
        return "internet"
    if servicio_abonado == "movil":
        return "movil"
    return "general"


def refinar_intencion_internet(texto: str) -> str | None:
    """Tras preguntar tipo de acceso (fibra/radio/ADSL), afina el playbook."""
    t = (texto or "").lower()
    if any(k in t for k in (
        "fibra", "ftth", "ont", "cable amarillo", "cajita blanca", "pon", "nap",
    )):
        return "internet_ftth"
    if any(k in t for k in (
        "adsl", "cobre", "splitter", "microfiltro", "telefonica", "telefónica",
    )):
        return "internet_adsl"
    if any(k in t for k in (
        "radio", "antena", "cpe", "inalambr", "inalámbr", "torre", "wireless",
        "enlace", "techo", "poe",
    )):
        return "internet_radio"
    # "linea/telefono" solos son ambiguos (fija vs adsl); no forzar ADSL acá
    return None


def respuesta_paso_ok(texto: str) -> bool | None:
    t = (texto or "").lower().strip()
    if not t:
        return None
    palabras_ok = (
        "si", "sí", "ok", "listo", "hecho", "verificado", "ya",
        "mejoro", "mejoró", "volvio", "volvió", "anda", "funciona",
        "anduvo", "perfecto", "genial",
    )
    palabras_fail = (
        "no", "sigue", "persiste", "igual", "nada", "falla", "mal",
        "sigue sin", "tampoco", "peor", "no funciona", "no anda",
    )
    if any(p in t for p in palabras_fail):
        return False
    if any(p in t for p in palabras_ok):
        return True
    return None


def indica_resuelto(texto: str) -> bool:
    """El abonado indica que el servicio ya volvió / funciona."""
    t = (texto or "").lower().strip()
    if not t:
        return False
    claves = (
        "ya anda", "ya funciona", "ya volvio", "ya volvió", "volvio", "volvió",
        "mejoro", "mejoró", "funciona", "anduvo", "anda bien", "quedó bien",
        "quedo bien", "resuelto", "solucionado", "perfecto", "genial",
        "todo bien", "ya esta", "ya está",
    )
    if any(x in t for x in (
        "no anda", "no funciona", "sigue sin", "no volvio", "no volvió",
        "no mejoro", "no mejoró",
    )):
        return False
    return any(k in t for k in claves)


def es_paso_derivacion(paso: PasoPlaybook | None) -> bool:
    if not paso:
        return False
    pid = (paso.id or "").lower()
    preg = (paso.pregunta or "").lower()
    if any(x in pid for x in ("derivar", "persistencia", "turno_campo", "turno_")):
        return True
    return (
        "¿querés que" in preg
        or "queres que" in preg
        or "te derive" in preg
        or "abra un ticket" in preg
        or "abra ticket" in preg
    )


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
            "quiero hablar",
            "pasar con alguien",
        )
    )


def normalizar_queja(texto: str) -> str:
    t = (texto or "").lower().strip()
    t = " ".join(t.split())
    return t[:160]


def detecta_frustracion(texto: str, ctx: dict) -> bool:
    """True si el usuario reitera la misma queja sustancial (2ª vez) sin progreso.

    Ignora respuestas cortas de diagnóstico ("no", "sigue igual") para no
    escalar en medio del playbook N1.
    """
    actual = normalizar_queja(texto)
    if len(actual) < 20:
        return False
    if respuesta_paso_ok(texto) is not None and len(actual) < 40:
        return False
    prev = str(ctx.get("ultima_queja") or "").strip()
    return bool(prev and actual == prev)


def registrar_queja(ctx: dict, texto: str) -> dict:
    actual = normalizar_queja(texto)
    if len(actual) < 8:
        return ctx
    prev = str(ctx.get("ultima_queja") or "").strip()
    if prev and actual == prev:
        ctx["reiteracion_queja"] = int(ctx.get("reiteracion_queja") or 0) + 1
    else:
        ctx["ultima_queja"] = actual
        ctx["reiteracion_queja"] = 0
    return ctx


def resumen_handoff(
    *,
    abonado: object | None,
    telefono: str,
    intencion: str,
    motivo: str,
    paso_idx: int = 0,
) -> str:
    """Resumen estandarizado para el panel al derivar."""
    dni = getattr(abonado, "dni", "") if abonado else ""
    nombre = getattr(abonado, "nombre", "") if abonado else ""
    tag = tag_para_intencion(intencion)
    servicio = {
        "internet_ftth": "FTTH",
        "internet_radio": "Wireless",
        "internet_adsl": "ADSL",
        "internet": "Internet",
        "internet_lento": "Internet",
        "wifi": "WiFi",
        "movil": "Móvil",
        "movil_datos": "Móvil datos",
        "movil_llamadas": "Móvil llamadas",
        "telefono_fija": "Telefonía fija",
        "ecolan_b2b": "Ecolan B2B",
        "corte_deuda": "Facturación/Pagos",
        "facturacion": "Facturación",
        "alta_plan": "Alta/plan",
        "no_tecnico": "No técnico",
        "general": "General",
    }.get(intencion, intencion or "General")
    return (
        f"{tag} [HANDOFF_HUMANO] "
        f"Socio/DNI: {dni or 'n/d'} · {nombre or telefono} · "
        f"Servicio: {servicio} · Motivo: {motivo} · "
        f"Diagnóstico N1 hasta paso {paso_idx}."
    )
