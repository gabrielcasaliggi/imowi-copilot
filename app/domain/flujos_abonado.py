"""Playbooks N1 — Cooperativa Batán.

Servicios:
- Internet FTTH (fibra al hogar)
- Internet wireless/radio (CPE + antena)
- Internet ADSL (par de cobre)
- Móvil IMOVI (telefonía celular MVNO)
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


# ---------------------------------------------------------------------------
# PLAYBOOKS
# ---------------------------------------------------------------------------

PLAYBOOKS: dict[str, list[PasoPlaybook]] = {
    # ---- FACTURACIÓN / DEUDA ----
    "corte_deuda": [
        PasoPlaybook(
            "confirmar_deuda",
            "Tu cuenta tiene un saldo pendiente y el servicio puede estar limitado. "
            "¿Querés que te indique cómo regularizarlo?",
        ),
        PasoPlaybook(
            "medios_pago",
            "Podés abonar en Rapipago, Pago Fácil, transferencia bancaria al CBU de la "
            "Cooperativa, o en la oficina comercial (Av. Brown 1234, Batán). "
            "Cuando se acredite el pago, el servicio se rehabilita automáticamente en pocos minutos. "
            "¿Necesitás algo más o querés hablar con un agente?",
        ),
    ],
    "facturacion": [
        PasoPlaybook(
            "tipo_consulta_factura",
            "¿Tu consulta es sobre: 1) un monto que no reconocés, 2) necesitás una copia "
            "del resumen, 3) cambiar el medio de pago, o 4) otra cosa? Escribime el número o contame.",
        ),
        PasoPlaybook(
            "derivar_factura",
            "Para consultas de facturación necesito derivarte con un agente que tiene "
            "acceso al sistema de cuentas corrientes. ¿Querés que te pase?",
        ),
    ],

    # ---- INTERNET FTTH (fibra óptica) ----
    "internet_ftth": [
        PasoPlaybook(
            "reinicio_ont",
            "Internet por fibra óptica (FTTH): ¿podés desenchufar la ONT (cajita blanca "
            "con el cable de fibra amarillo) y el router durante 30 segundos, encender "
            "primero la ONT, esperar que encienda la luz PON/LINK en verde fijo, y después "
            "el router? ¿Volvió la conexión?",
        ),
        PasoPlaybook(
            "luces_ont",
            "Fijate en la ONT: ¿la luz PON está en verde fijo y la luz LOS apagada? "
            "Si LOS está en rojo, puede haber un corte de fibra. Respondé qué ves.",
        ),
        PasoPlaybook(
            "cable_fibra",
            "¿El cable de fibra amarillo está bien enchufado en la ONT (sin dobleces "
            "pronunciados ni daño visible)? A veces un mueble o mascota lo desconecta.",
        ),
        PasoPlaybook(
            "wifi_vs_cable_ftth",
            "¿El problema es solo WiFi o también falla si conectás una PC por cable "
            "directo al router? Si es solo WiFi, puede ser saturación del canal.",
        ),
        PasoPlaybook(
            "persistencia_ftth",
            "Si sigue sin servicio después de estos pasos, parece un tema que requiere "
            "revisión técnica. Te derivo con un agente para coordinar una visita. "
            "¿Querés que lo haga?",
        ),
    ],

    # ---- INTERNET WIRELESS / RADIO ----
    "internet_radio": [
        PasoPlaybook(
            "reinicio_cpe",
            "Internet por radio/antena: ¿podés apagar el equipo de radio (CPE, generalmente "
            "en el techo o pared exterior) y el router durante 30 segundos? Encendé primero "
            "el CPE/radio, esperá 1 minuto a que enganche la señal, y después el router. "
            "¿Volvió la conexión?",
        ),
        PasoPlaybook(
            "led_enlace",
            "¿El LED de enlace/señal del CPE está fijo (sin parpadeo de alarma o apagado)? "
            "Si parpadea rápido o está rojo puede ser pérdida de enlace con la torre.",
        ),
        PasoPlaybook(
            "linea_vista",
            "¿La antena tiene línea de vista libre hacia la torre (sin árboles, "
            "construcciones nuevas u otros obstáculos)? ¿El cable de alimentación (PoE) "
            "está bien conectado y el inyector tiene luz?",
        ),
        PasoPlaybook(
            "wifi_vs_cable_radio",
            "¿Falla solo el WiFi o también si conectás una PC por cable directo al router? "
            "Si es solo WiFi puede ser interferencia o saturación del canal.",
        ),
        PasoPlaybook(
            "zona_vecinos",
            "¿Solo te pasa a vos o también a vecinos de la misma zona/torre? "
            "Si es zonal, probablemente sea un tema de la torre y ya lo vamos a resolver. "
            "Si persiste sólo en tu casa, te derivo con un técnico.",
        ),
    ],

    # ---- INTERNET ADSL ----
    "internet_adsl": [
        PasoPlaybook(
            "reinicio_modem_adsl",
            "Internet ADSL (línea telefónica): ¿podés apagar el módem ADSL 30 segundos, "
            "encenderlo y esperar 2 minutos hasta que sincronice (luz DSL fija)? ¿Volvió?",
        ),
        PasoPlaybook(
            "luces_adsl",
            "¿La luz de DSL/Sync del módem quedó fija (verde o azul)? Si parpadea "
            "continuamente, no está sincronizando con la central. Respondé qué ves.",
        ),
        PasoPlaybook(
            "filtro_splitter",
            "¿Tenés teléfono fijo? Verificá que el filtro/splitter esté bien colocado "
            "y que no haya teléfonos, alarmas u otros aparatos conectados a la línea "
            "sin filtro. Eso puede causar interferencia y pérdida de sincronización.",
        ),
        PasoPlaybook(
            "cable_telefono",
            "¿Probaste conectar el módem directamente a la primera toma telefónica "
            "(la que entra de la calle), sin extensiones? A veces los cables internos "
            "generan ruido.",
        ),
        PasoPlaybook(
            "wifi_vs_cable_adsl",
            "¿El problema es solo WiFi o también falla por cable al módem/router? "
            "Si es solo WiFi, tu línea puede estar bien.",
        ),
        PasoPlaybook(
            "persistencia_adsl",
            "Si sigue sin servicio, posiblemente hay un problema en el par de cobre o la "
            "central. Te derivo con un agente para que se genere la revisión. ¿Querés que lo haga?",
        ),
    ],

    # ---- INTERNET GENÉRICO (preguntar tipo) ----
    "internet": [
        PasoPlaybook(
            "tipo_acceso",
            "Para ayudarte con internet, necesito saber qué tipo de conexión tenés: "
            "¿fibra óptica (cable amarillo a una cajita blanca), radio/antena en el "
            "techo, o ADSL por línea telefónica?",
        ),
    ],

    # ---- INTERNET LENTO ----
    "internet_lento": [
        PasoPlaybook(
            "cuantos_dispositivos",
            "¿Cuántos dispositivos hay conectados al WiFi ahora? A veces la lentitud "
            "es por saturación. ¿Podés probar con uno solo, conectado por cable?",
        ),
        PasoPlaybook(
            "test_velocidad",
            "¿Podés hacer un test de velocidad desde una PC por cable? Entrá a "
            "fast.com o speedtest.net y decime cuánto te da de bajada.",
        ),
        PasoPlaybook(
            "comparar_plan",
            "¿Cuánto te dio? Si está por debajo del 70% del plan contratado con el "
            "equipo por cable, hay que revisarlo. Te derivo con un agente para que "
            "verifiquen la línea. ¿Querés?",
        ),
    ],

    # ---- WIFI ----
    "wifi": [
        PasoPlaybook(
            "zona_wifi",
            "¿El WiFi falla en toda la casa o solo lejos del router? La señal WiFi "
            "pierde fuerza con las paredes, especialmente de hormigón o ladrillo.",
        ),
        PasoPlaybook(
            "reinicio_router_wifi",
            "¿Podés reiniciar el router (apagar 30 segundos y encender)? A veces "
            "se satura la tabla de conexiones.",
        ),
        PasoPlaybook(
            "banda_wifi",
            "Si tu router tiene dos redes (2.4GHz y 5GHz), ¿probaste conectarte a la "
            "otra? La de 5GHz es más rápida pero tiene menos alcance; la de 2.4GHz "
            "llega más lejos.",
        ),
        PasoPlaybook(
            "derivar_wifi",
            "Si sigue mal, puede que necesites un extensor o access point. "
            "¿Querés que te pase con un agente para evaluar opciones?",
        ),
    ],

    # ---- MÓVIL IMOVI ----
    "movil": [
        PasoPlaybook(
            "reinicio_imovi",
            "Para el servicio móvil IMOVI: ¿reiniciaste el teléfono? A veces se "
            "desregistra de la red y el reinicio lo soluciona. ¿Mejoró?",
        ),
        PasoPlaybook(
            "modo_avion",
            "Activá modo avión durante 15 segundos y desactivalo. Esto fuerza al "
            "teléfono a buscar señal de nuevo. ¿Volvió?",
        ),
        PasoPlaybook(
            "red_manual",
            "Entrá en Ajustes > Redes móviles > Operador de red. Sacalo de automático, "
            "elegí otra red (Personal/Claro), esperá que se registre, y después volvé a "
            "seleccionar IMOVI. Esto genera un nuevo registro en la red. ¿Funcionó?",
        ),
        PasoPlaybook(
            "apn_imovi",
            "Verificá el APN: Ajustes > Redes móviles > APN. Debería ser "
            "internet.coopbatan.ar (MCC 722, MNC 310). Si no existe, crealo. ¿Mejoró?",
        ),
        PasoPlaybook(
            "otra_ubicacion",
            "¿El problema es en una sola zona o en varias ubicaciones? Si es solo "
            "en un punto, puede ser una zona sin cobertura. Si pasa en todos lados, "
            "hay que revisar la línea. Te paso con un agente.",
        ),
    ],

    # ---- MOVIL SIN DATOS ----
    "movil_datos": [
        PasoPlaybook(
            "datos_activados",
            "¿Los datos móviles están activados en tu teléfono? Fijate en Ajustes > "
            "Redes móviles > Datos móviles. También verificá que no estés en modo avión.",
        ),
        PasoPlaybook(
            "apn_datos",
            "Revisá el APN de datos: debe ser internet.coopbatan.ar. Si está "
            "incorrecto o vacío, los datos no van a funcionar. ¿Lo corregiste?",
        ),
        PasoPlaybook(
            "roaming_datos",
            "¿Estás en tu zona habitual o viajando? Si estás fuera de la zona de "
            "cobertura IMOVI, necesitás tener habilitado el roaming de datos.",
        ),
        PasoPlaybook(
            "derivar_datos",
            "Si sigue sin datos después de estos pasos, necesitamos revisar tu "
            "línea desde el sistema. Te derivo con un agente. ¿Querés?",
        ),
    ],

    # ---- MOVIL SMS / LLAMADAS ----
    "movil_llamadas": [
        PasoPlaybook(
            "tipo_problema_llamada",
            "¿El problema es que no podés hacer llamadas, no las recibís, o se cortan? "
            "¿Y con los SMS te pasa lo mismo?",
        ),
        PasoPlaybook(
            "reinicio_llamadas",
            "Reiniciá el teléfono y probá hacer una llamada de prueba al *99# o a otro "
            "número. ¿Funciona?",
        ),
        PasoPlaybook(
            "derivar_llamadas",
            "Si persiste, es un tema que necesitamos revisar en red. Te derivo con un "
            "agente que puede verificar tu línea en el HLR. ¿Querés?",
        ),
    ],

    # ---- ALTA NUEVA / CAMBIO DE PLAN ----
    "alta_plan": [
        PasoPlaybook(
            "tipo_alta",
            "¿Querés dar de alta un servicio nuevo, o cambiar/mejorar el plan que ya "
            "tenés? ¿Es internet, móvil, o ambos?",
        ),
        PasoPlaybook(
            "derivar_comercial",
            "Para altas y cambios de plan te conecto con un agente del área comercial "
            "que te puede pasar las opciones y precios vigentes. ¿Querés que te derive?",
        ),
    ],

    # ---- MENÚ GENERAL ----
    "general": [
        PasoPlaybook(
            "menu_servicio",
            "Hola, soy el asistente virtual de Cooperativa Batán. Te puedo ayudar con:\n"
            "• Internet (fibra, radio/antena o ADSL)\n"
            "• Móvil IMOVI (señal, datos, llamadas)\n"
            "• Facturación y pagos\n"
            "• Alta o cambio de plan\n"
            "¿Con qué necesitás ayuda?",
        ),
    ],
}


# ---------------------------------------------------------------------------
# CLASIFICACIÓN DE INTENCIÓN
# ---------------------------------------------------------------------------

def clasificar_intencion(texto: str, servicio_abonado: str = "") -> str:
    t = (texto or "").lower()

    # Facturación / deuda / pago
    if any(k in t for k in (
        "deuda", "corte", "suspend", "factur", "pago", "saldo", "boleta",
        "cuenta corriente", "resumen", "recibo",
    )):
        return "corte_deuda"

    # Alta / cambio de plan
    if any(k in t for k in (
        "dar de alta", "alta", "cambio de plan", "cambiar plan", "mejorar plan",
        "contratar", "baja", "quiero el plan",
    )):
        return "alta_plan"

    # ADSL
    if any(k in t for k in (
        "adsl", "línea telefónica", "linea telefonica", "par de cobre",
        "modem adsl", "módem adsl", "splitter", "filtro adsl",
    )):
        return "internet_adsl"

    # FTTH
    if any(k in t for k in (
        "fibra", "ftth", "fibra optica", "fibra óptica", "ont",
        "cable amarillo", "pon", "gpon",
    )):
        return "internet_ftth"

    # Radio / wireless
    if any(k in t for k in (
        "radio", "antena", "cpe", "inalambr", "inalámbr", "torre",
        "wireless", "enlace", "poe", "inyector",
    )):
        return "internet_radio"

    # Internet lento
    if any(k in t for k in (
        "lento", "lenta", "velocidad", "speed", "tarda", "demora",
        "baja velocidad", "muy lento", "anda lento",
    )):
        return "internet_lento"

    # WiFi
    if any(k in t for k in (
        "wifi", "wi-fi", "señal wifi", "no llega wifi", "wifi no funciona",
    )):
        return "wifi"

    # Internet genérico
    if any(k in t for k in (
        "modem", "módem", "router", "ecolan", "internet fijo",
        "sin internet", "no anda internet", "internet", "no navego",
        "no cargo", "pagina", "página",
    )):
        return "internet"

    # Móvil - datos
    if any(k in t for k in (
        "datos movil", "datos móvil", "sin datos", "no tengo datos",
        "datos no funcionan", "internet del celular", "apn",
    )):
        return "movil_datos"

    # Móvil - llamadas/SMS
    if any(k in t for k in (
        "llamada", "sms", "no puedo llamar", "no me llegan llamadas",
        "se cortan las llamadas", "mensaje de texto",
    )):
        return "movil_llamadas"

    # Móvil genérico
    if any(k in t for k in (
        "imovi", "imovu", "señal", "senal",
        "chip", "4g", "5g", "celular", "móvil", "movil",
        "sim", "linea movil", "línea móvil",
    )):
        return "movil"

    # Fallback por servicio del abonado
    if servicio_abonado in ("internet", "ambos"):
        return "internet"
    if servicio_abonado == "movil":
        return "movil"
    return "general"


def refinar_intencion_internet(texto: str) -> str | None:
    """Tras preguntar tipo de acceso (fibra/radio/ADSL), afina el playbook."""
    t = (texto or "").lower()
    if any(k in t for k in (
        "fibra", "ftth", "ont", "cable amarillo", "cajita blanca", "pon",
    )):
        return "internet_ftth"
    if any(k in t for k in (
        "adsl", "línea", "linea", "telefono", "teléfono", "cobre", "splitter",
    )):
        return "internet_adsl"
    if any(k in t for k in (
        "radio", "antena", "cpe", "inalambr", "inalámbr", "torre", "wireless", "enlace", "techo",
    )):
        return "internet_radio"
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
