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
}


# ---------------------------------------------------------------------------
# PLAYBOOKS
# ---------------------------------------------------------------------------

PLAYBOOKS: dict[str, list[PasoPlaybook]] = {
    # ---- FACTURACIÓN / DEUDA / QR FISERV ----
    "corte_deuda": [
        PasoPlaybook(
            "confirmar_deuda",
            "Tu cuenta puede tener saldo pendiente y el servicio limitado. "
            "Para consultas de factura/saldo necesito tu DNI o N.º de socio/cuenta. "
            "¿Me lo compartís? Si ya lo dimos, ¿querés que te indique cómo pagar?",
        ),
        PasoPlaybook(
            "medios_pago_qr",
            "Podés abonar con el código QR interoperable Fiserv impreso en la factura/cupón: "
            "escanealo desde Mercado Pago, Cuenta DNI, BNA+, MODO u otra billetera, "
            "o subí la foto de la factura desde la galería del teléfono. "
            "También podés pagar en Rapipago, Pago Fácil, transferencia o en oficina comercial. "
            "Cuando se acredita el pago por QR, el servicio (fibra, radio, ADSL o telefonía) "
            "se reactiva automáticamente, sin operador. ¿Necesitás algo más?",
        ),
        PasoPlaybook(
            "derivar_pagos",
            "Si el pago no aparece acreditado o no podés generar/usar el QR, "
            "¿querés que te derive con un agente de facturación?",
        ),
    ],
    "facturacion": [
        PasoPlaybook(
            "pedir_dni_factura",
            "Para consultar saldo, deuda o enviarte el comprobante, necesito el DNI del "
            "titular o el N.º de socio/cuenta. ¿Me lo pasás?",
        ),
        PasoPlaybook(
            "tipo_consulta_factura",
            "¿Tu consulta es sobre: 1) saldo/monto vencido, 2) copia del resumen, "
            "3) pago con QR Fiserv, 4) cambiar medio de pago, o 5) otra cosa?",
        ),
        PasoPlaybook(
            "medios_pago_qr_factura",
            "Para pagar: usá el QR Fiserv de la factura con cualquier billetera "
            "(Mercado Pago, Cuenta DNI, MODO, etc.). La acreditación reactiva el servicio "
            "en automático. ¿Pudiste pagar o necesitás que un agente revise la cuenta?",
        ),
        PasoPlaybook(
            "derivar_factura",
            "Para gestiones de cuenta corriente que requieren sistema interno, "
            "¿querés que te pase con un agente de facturación?",
        ),
    ],

    # ---- INTERNET FTTH (fibra óptica / OLT Huawei) ----
    "internet_ftth": [
        PasoPlaybook(
            "energia_ont",
            "Internet por fibra (FTTH / ONT): primero chequeamos energía. "
            "¿La cajita blanca (ONT) tiene luces encendidas y el transformador "
            "bien enchufado a la corriente? Si está apagada del todo, puede ser falta "
            "de energía en el domicilio (Dying Gasp). ¿Tiene alimentación?",
        ),
        PasoPlaybook(
            "luces_los",
            "En la ONT: ¿la luz PON/LINK está verde fija y la luz LOS apagada? "
            "Si LOS está en rojo o hay Loss of Signal, suele ser corte o interrupción "
            "de la fibra hacia el domicilio. Contame qué luces ves.",
        ),
        PasoPlaybook(
            "reinicio_ont",
            "Si hay señal pero no navega (a veces por potencia atenuada, p. ej. peor "
            "que -27 dBm), hagamos reinicio físico: desenchufá ONT y router 30 segundos; "
            "encendé primero la ONT, esperá 2–3 minutos a que PON quede verde fijo, "
            "después el router. ¿Volvió la conexión?",
        ),
        PasoPlaybook(
            "cable_fibra",
            "¿El cable de fibra amarillo está bien enchufado en la ONT (sin dobleces "
            "pronunciados ni daño visible)? Revisá también la caja NAP si está accesible.",
        ),
        PasoPlaybook(
            "wifi_vs_cable_ftth",
            "¿El problema es solo WiFi o también falla una PC por cable directo al router? "
            "Si es solo WiFi, la fibra puede estar bien y revisamos la red inalámbrica.",
        ),
        PasoPlaybook(
            "turno_campo_ftth",
            "Si sigue sin servicio, hace falta revisión de cuadrilla (evidencia en OLT/NAP "
            "vía app JSAT). Debe haber una persona mayor de edad en el domicilio. "
            "¿Querés que abra un ticket para agendar turno de campo?",
        ),
    ],

    # ---- INTERNET WIRELESS / RADIO ----
    "internet_radio": [
        PasoPlaybook(
            "poe_antena",
            "Internet por radio/antena (Wireless): ¿la fuente PoE de la antena exterior "
            "tiene luz encendida? Si el PoE está apagado, la antena no alimenta y no hay enlace.",
        ),
        PasoPlaybook(
            "reinicio_cpe",
            "Reiniciá: apagá el equipo de radio (CPE) y el router Wi-Fi interno 30 segundos. "
            "Encendé primero el CPE/radio, esperá ~1 minuto a que enganche, después el router. "
            "¿Volvió la conexión?",
        ),
        PasoPlaybook(
            "led_enlace",
            "¿El LED de enlace/señal del CPE está fijo (sin alarma o apagado)? "
            "Si parpadea rápido o está rojo, puede haber caída de enlace o del nodo/torre.",
        ),
        PasoPlaybook(
            "linea_vista",
            "¿La antena tiene línea de vista libre hacia la torre (sin árboles o "
            "construcciones nuevas)? ¿El cable PoE está firme en antena e inyector?",
        ),
        PasoPlaybook(
            "zona_vecinos",
            "¿Solo te pasa a vos o también a vecinos de la misma zona/torre? "
            "Si es zonal, puede ser el nodo de distribución. Si es solo tu casa, "
            "seguimos con revisión puntual.",
        ),
        PasoPlaybook(
            "turno_campo_radio",
            "Si no se resolvió en N1, coordinamos cuadrilla (evidencia JSAT). "
            "¿Querés que abra ticket para turno de campo?",
        ),
    ],

    # ---- INTERNET ADSL ----
    "internet_adsl": [
        PasoPlaybook(
            "tono_linea",
            "Internet ADSL (par de cobre): ¿el teléfono fijo tiene tono de marcación? "
            "Si no hay tono, el problema puede ser de la línea telefónica antes que del módem.",
        ),
        PasoPlaybook(
            "filtro_splitter",
            "Verificá el microfiltro/splitter: debe estar antes del módem y del teléfono. "
            "Ningún teléfono, alarma u otro aparato debería ir a la línea sin filtro.",
        ),
        PasoPlaybook(
            "reinicio_modem_adsl",
            "Apagá el módem ADSL 30 segundos, encendelo y esperá ~2 minutos hasta que "
            "sincronice (luz DSL/Sync fija). ¿Volvió?",
        ),
        PasoPlaybook(
            "luces_adsl",
            "¿La luz DSL/Sync quedó fija (verde/azul)? Si parpadea siempre, no sincroniza "
            "con la central. Contame qué ves.",
        ),
        PasoPlaybook(
            "cable_telefono",
            "¿Probaste el módem en la primera toma telefónica (entrada de calle), "
            "sin extensiones internas?",
        ),
        PasoPlaybook(
            "persistencia_adsl",
            "Si sigue fallando, puede ser el par de cobre o la central. "
            "¿Querés que abra ticket para revisión técnica / turno?",
        ),
    ],

    # ---- INTERNET GENÉRICO ----
    "internet": [
        PasoPlaybook(
            "sintoma_internet",
            "Contame: ¿no tenés internet en absoluto, anda lento, se corta, "
            "o el problema es solo el WiFi?",
        ),
        PasoPlaybook(
            "alcance_internet",
            "¿Te pasa en todos los dispositivos o solo en uno? "
            "¿En toda la casa o en alguna habitación?",
        ),
        PasoPlaybook(
            "tipo_acceso",
            "¿Qué tecnología tenés?\n"
            "• Fibra óptica (FTTH: cable amarillo + cajita blanca/ONT)\n"
            "• Radio / antena Wireless (techo o pared exterior + PoE)\n"
            "• ADSL por línea telefónica (módem + cable de teléfono)\n"
            "Respondé: fibra, radio o ADSL.",
        ),
    ],

    # ---- INTERNET LENTO ----
    "internet_lento": [
        PasoPlaybook(
            "cuantos_dispositivos",
            "¿Cuántos dispositivos hay en el WiFi? Probá con uno solo por cable al router "
            "y contame si mejora.",
        ),
        PasoPlaybook(
            "horario_lento",
            "¿Es todo el día o más a la tarde/noche (horario pico)?",
        ),
        PasoPlaybook(
            "test_velocidad",
            "Hacé un test por cable (fast.com o speedtest.net) y decime la bajada que te da.",
        ),
        PasoPlaybook(
            "reinicio_lento",
            "Reiniciá módem/ONT y router 30 segundos y repetí el test por cable. ¿Mejoró?",
        ),
        PasoPlaybook(
            "comparar_plan",
            "Si por cable sigue bajo el ~70% del plan, hay que revisar línea/OLT. "
            "¿Querés que derive a un agente técnico?",
        ),
    ],

    # ---- WIFI ----
    "wifi": [
        PasoPlaybook(
            "zona_wifi",
            "¿El WiFi falla en toda la casa o solo lejos del router?",
        ),
        PasoPlaybook(
            "otros_dispositivos_wifi",
            "¿Les pasa a todos los equipos o solo a uno? Si es uno, olvidá la red y reconectá.",
        ),
        PasoPlaybook(
            "reinicio_router_wifi",
            "Reiniciá el router 30 segundos. ¿Mejoró?",
        ),
        PasoPlaybook(
            "banda_wifi",
            "Si hay 2.4 GHz y 5 GHz, ¿probaste la otra banda? "
            "5 GHz es más rápida y de menos alcance; 2.4 GHz llega más lejos.",
        ),
        PasoPlaybook(
            "canal_interferencia",
            "Alejá el router de microondas/cordless y ubicarlo más alto y central ayuda. "
            "¿Pudiste probar otro lugar?",
        ),
        PasoPlaybook(
            "derivar_wifi",
            "Si sigue mal, puede hacer falta extensor/AP o revisión. "
            "¿Querés que te pase con un agente?",
        ),
    ],

    # ---- MÓVIL IMOVI ----
    "movil": [
        PasoPlaybook(
            "sintoma_movil",
            "¿Qué pasa con el móvil IMOVI?: ¿sin señal, sin datos, no llamás/recibís, "
            "o se cortan las llamadas?",
        ),
        PasoPlaybook(
            "datos_roaming_check",
            "Confirmá que datos móviles (y roaming si estás fuera de zona) estén activos, "
            "y que no estés en modo avión. ¿Están bien?",
        ),
        PasoPlaybook(
            "reinicio_imovi",
            "Reiniciá el teléfono. ¿Mejoró?",
        ),
        PasoPlaybook(
            "modo_avion",
            "Modo avión 15 segundos y desactivá. ¿Volvió la señal/servicio?",
        ),
        PasoPlaybook(
            "apn_imovi",
            "APN: Ajustes > Redes móviles > APN → internet.coopbatan.ar "
            "(MCC 722, MNC 310). Si no está, crealo y reiniciá. ¿Mejoró?",
        ),
        PasoPlaybook(
            "otra_sim_o_tel",
            "Si podés: misma SIM en otro teléfono u otra SIM en el tuyo. "
            "Así vemos si es línea o equipo.",
        ),
        PasoPlaybook(
            "otra_ubicacion",
            "¿Es en una sola zona o en varios lugares? Si sigue en todos lados, "
            "¿querés que derive a un agente para revisar la línea?",
        ),
    ],

    "movil_datos": [
        PasoPlaybook(
            "datos_activados",
            "¿Datos móviles activos y sin modo avión?",
        ),
        PasoPlaybook(
            "consumo_paquete",
            "¿Te queda saldo/paquete de datos del abono?",
        ),
        PasoPlaybook(
            "apn_datos",
            "APN debe ser internet.coopbatan.ar. Corregilo, reiniciá y probá. ¿Anda?",
        ),
        PasoPlaybook(
            "roaming_datos",
            "¿Estás en zona habitual o de viaje? Fuera de cobertura IMOVI hace falta "
            "roaming de datos habilitado.",
        ),
        PasoPlaybook(
            "prueba_wifi_off",
            "Apagá el WiFi del teléfono y probá solo con datos. ¿Navega?",
        ),
        PasoPlaybook(
            "derivar_datos",
            "Si sigue sin datos, hay que revisar la línea en sistema. "
            "¿Querés que te derive con un agente?",
        ),
    ],

    "movil_llamadas": [
        PasoPlaybook(
            "tipo_problema_llamada",
            "¿No podés hacer llamadas, no las recibís, se cortan, y/o falla el SMS?",
        ),
        PasoPlaybook(
            "reinicio_llamadas",
            "Reiniciá y probá una llamada de prueba (*99# u otro número). ¿Funciona?",
        ),
        PasoPlaybook(
            "modo_avion_llamadas",
            "Modo avión 15 s y volvé. ¿Podés llamar o recibir?",
        ),
        PasoPlaybook(
            "otra_ubicacion_llamadas",
            "¿Te pasa en una zona o en varios lugares?",
        ),
        PasoPlaybook(
            "derivar_llamadas",
            "Si persiste, revisamos en red/HLR. ¿Querés que te derive con un agente?",
        ),
    ],

    # ---- TELEFONÍA FIJA ----
    "telefono_fija": [
        PasoPlaybook(
            "tono_fija",
            "Telefonía fija: ¿hay tono de marcación al levantar el auricular?",
        ),
        PasoPlaybook(
            "cableado_fija",
            "Revisá que el cable esté bien en la toma y que no haya desvíos o equipos "
            "intermedios defectuosos. ¿Sigue sin tono o sin llamadas?",
        ),
        PasoPlaybook(
            "derivar_fija",
            "Si no hay tono o no entran/salen llamadas, abrimos revisión de línea fija. "
            "¿Querés que te derive con un agente?",
        ),
    ],

    # ---- ECOLAN B2B / DATA CENTER ----
    "ecolan_b2b": [
        PasoPlaybook(
            "tipo_ecolan",
            "Soy el asistente de Cooperativa Batán / Ecolan Tecnologías. "
            "¿Tu consulta es por Central Telefónica Virtual (PBX), Cloud/VM, "
            "Housing/Hosting, o enlace dedicado (fibra + backup Starlink / IP fija / VPN)?",
        ),
        PasoPlaybook(
            "impacto_sla",
            "Para priorizar: ¿hay servicio caído ahora, degradación, o es una cotización/"
            "proyecto nuevo? Indicá disponibilidad o SLA si aplica.",
        ),
        PasoPlaybook(
            "derivar_ecolan",
            "Los casos Ecolan B2B (Data Center, enlaces con SLA, cotizaciones) los atiende "
            "un especialista. ¿Querés que te derive ahora con el resumen al panel?",
        ),
    ],

    # ---- ALTA / PLAN ----
    "alta_plan": [
        PasoPlaybook(
            "tipo_alta",
            "¿Alta nueva o cambio de plan? ¿Internet (fibra/radio/ADSL), móvil IMOVI, "
            "telefonía fija, o servicio Ecolan empresa?",
        ),
        PasoPlaybook(
            "zona_comercial",
            "¿Zona o dirección aproximada (barrio/localidad) para chequear cobertura?",
        ),
        PasoPlaybook(
            "derivar_comercial",
            "Te conecto con comercial para opciones y precios vigentes. ¿Querés que te derive?",
        ),
    ],

    # ---- TRÁMITES DIGITALES ----
    "portal_tramites": [
        PasoPlaybook(
            "info_batan_coop",
            "Para trámites digitales, facturación electrónica y solicitudes de servicios "
            "también podés usar el portal batan.coop. ¿Qué trámite necesitás hacer?",
        ),
        PasoPlaybook(
            "derivar_tramites",
            "Si el trámite requiere operador, ¿querés que te derive con un agente?",
        ),
    ],

    # ---- TURNO DE CAMPO (post N1) ----
    "turno_campo": [
        PasoPlaybook(
            "confirmar_turno",
            "Para la visita técnica: debe haber una persona mayor de edad en el domicilio. "
            "El operario registra fotos de evidencia (NAP, potencia, etc.) en la app JSAT "
            "antes de cerrar. ¿Confirmás que pueden recibir la visita?",
        ),
        PasoPlaybook(
            "derivar_agenda",
            "Un agente te va a ofrecer franjas horarias según cupos de cuadrilla "
            "(la agenda automática se integra en una etapa siguiente). "
            "¿Querés que abra el ticket de turno ahora?",
        ),
    ],

    # ---- MENÚ GENERAL ----
    "general": [
        PasoPlaybook(
            "menu_servicio",
            "Hola, soy el Asistente Virtual de Cooperativa Batán y Ecolan Tecnologías. "
            "Te puedo ayudar con:\n"
            "• Internet (fibra FTTH, radio/Wireless o ADSL)\n"
            "• Móvil IMOVI y telefonía fija\n"
            "• Facturación, saldo y pago con QR Fiserv\n"
            "• Alta o cambio de plan\n"
            "• Ecolan (Data Center, VMs, enlaces dedicados)\n"
            "• Trámites en batan.coop\n"
            "¿Con qué necesitás ayuda?",
        ),
        PasoPlaybook(
            "detalle_problema",
            "Contame con más detalle qué está pasando (servicio y síntoma). "
            "Te guío en diagnóstico N1 antes de derivar a un agente. "
            "Para gestiones de cuenta, voy a pedirte DNI o N.º de socio.",
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
    }.get(intencion, intencion or "General")
    return (
        f"{tag} [HANDOFF_HUMANO] "
        f"Socio/DNI: {dni or 'n/d'} · {nombre or telefono} · "
        f"Servicio: {servicio} · Motivo: {motivo} · "
        f"Diagnóstico N1 hasta paso {paso_idx}."
    )
