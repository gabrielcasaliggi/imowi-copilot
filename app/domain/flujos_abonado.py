"""Playbooks N1 — Cooperativa Batán / Ecolan Tecnologías.

Catálogo:
- Internet FTTH (fibra), BAI/Wireless/radio, ADSL, intermitencia, clave Wi‑Fi
- TV OTT Sensa (+ Android TV Box / packs)
- Telefonía móvil IMOWI y telefonía fija
- Ecolan B2B (Data Center, VMs, enlaces dedicados, housing/hosting)
- Facturación / pagos QR Fiserv + Mi Cuenta ov.batan.coop
- Trámites digitales batan.coop

Los flujos de internet técnico incorporan pasos y reglas del catálogo
`docs/rag-botmaker-2026-08-14` (blueprints N1 curados). Copy y APN/QR
siguen siendo de Batán; no se importan embeddings ni texto de clientes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.branding_assistant import frase_soy_eko


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
    "facturacion_pago": "[PAGOS_QR]",
    "facturacion_descarga": "[PAGOS_QR]",
    "facturacion_informar_pago": "[PAGOS_QR]",
    "facturacion_factura": "[PAGOS_QR]",
    "facturacion_estado_cuenta": "[PAGOS_QR]",
    "facturacion_reclamo": "[PAGOS_QR]",
    "reactivacion_pago": "[PAGOS_QR]",
    "internet_ftth": "[TEC_FTTH]",
    "internet_radio": "[TEC_WIRELESS]",
    "internet_adsl": "[TEC_ADSL]",
    "internet": "[TEC_FTTH]",
    "internet_lento": "[TEC_FTTH]",
    "internet_intermitente": "[TEC_INTERMITENCIA]",
    "wifi": "[TEC_WIRELESS]",
    "cambio_clave_wifi": "[TEC_WIFI]",
    "estado_reclamo": "[HANDOFF_HUMANO]",
    "movil": "[TEL_MOVIL]",
    "movil_datos": "[TEL_MOVIL]",
    "movil_llamadas": "[TEL_MOVIL]",
    "telefono_fija": "[TEL_FIJA]",
    "tv_sensa": "[TEC_TV_SENSA]",
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
            "medios_pago_qr",
            "Podés pagar con el QR Fiserv de la factura (Mercado Pago, MODO, etc.) "
            "o por los medios de la boleta. Cuando se acredita, el servicio se reactiva solo: "
            "no hace falta avisar el pago. "
            "Si no tenés el QR, mirá Mi Cuenta en ov.batan.coop o pasame DNI/N.º de socio. "
            "¿Pudiste pagar o necesitás que te ubique la cuenta?",
        ),
        PasoPlaybook(
            "confirmar_deuda",
            "¿Me pasás el DNI o N.º de socio para ubicar el saldo y el QR?",
        ),
        PasoPlaybook(
            "derivar_pagos",
            "Si el pago no figura, ¿querés que te derive con facturación?",
        ),
    ],
    "facturacion": [
        PasoPlaybook(
            "triaje_motivo",
            "¿Qué necesitás: pagar, descargar factura/talón, avisar un pago, "
            "que te manden la factura, consultar deuda, o reclamar un cobro?",
        ),
        PasoPlaybook(
            "identificar_cuenta",
            "Para mirar tu cuenta necesito el DNI del titular o N.º de socio. ¿Me lo pasás?",
        ),
        PasoPlaybook(
            "derivar_factura",
            "Con lo que contás hace falta revisar la cuenta adentro. ¿Te derivo con facturación?",
        ),
    ],
    "facturacion_pago": [
        PasoPlaybook(
            "medios_pago_qr",
            "Podés pagar con el QR Fiserv de la factura (Mercado Pago, MODO, etc.) "
            "o en Mi Cuenta ov.batan.coop (también ov.batan.coop/#/pagar con DNI). "
            "No te puedo confirmar la acreditación hasta que figure en el sistema. "
            "¿Pudiste entrar al medio de pago?",
        ),
        PasoPlaybook(
            "talon_si_falta",
            "Si no tenés el QR, la boleta/talón está en Mi Cuenta. ¿Me pasás DNI o N.º de socio para ubicarla?",
        ),
        PasoPlaybook(
            "validacion_pago",
            "¿Pudiste pagar o preferís que te derive con facturación?",
        ),
    ],
    "facturacion_descarga": [
        PasoPlaybook(
            "tipo_documento",
            "¿Necesitás la factura, la boleta o el talón/cupón para pagar?",
        ),
        PasoPlaybook(
            "periodo_descarga",
            "¿De qué mes o período es?",
        ),
        PasoPlaybook(
            "ov_descarga",
            "En Mi Cuenta ov.batan.coop podés descargar el documento. "
            "Si no entras, pasame DNI o N.º de socio. ¿Pudiste abrirla?",
        ),
        PasoPlaybook(
            "derivar_descarga",
            "Si no aparece el período, ¿querés que te derive para que te la manden?",
        ),
    ],
    "facturacion_informar_pago": [
        PasoPlaybook(
            "informar_pago_detalle",
            "OV (ov.batan.coop) o QR Fiserv: acreditación y rehabilitación al instante. "
            "Medio externo: cargar aviso en ov.batan.coop/#/aviso-de-pago si la cuenta estaba "
            "deshabilitada. Con internet fijo identificado, verificar Radius si ya avisó.",
        ),
        PasoPlaybook(
            "aviso_pago_ov",
            "El aviso de pago está en ov.batan.coop. No puedo afirmar que ya se acreditó "
            "hasta que el sistema lo muestre. ¿Pudiste cargar el aviso o sigue sin figurar?",
        ),
        PasoPlaybook(
            "identificar_pago",
            "¿Me pasás DNI o N.º de socio, medio y fecha del pago?",
        ),
        PasoPlaybook(
            "derivar_informar_pago",
            "Si ya pasó el plazo y no figura, ¿te derivo con facturación?",
        ),
    ],
    "facturacion_factura": [
        PasoPlaybook(
            "solicitud_factura_detalle",
            "¿Qué período necesitás y cómo la querés: PDF en Mi Cuenta o que te la manden?",
        ),
        PasoPlaybook(
            "ov_factura",
            "La factura está en ov.batan.coop. ¿Pudiste descargarla o preferís que te la envíen?",
        ),
        PasoPlaybook(
            "identificar_factura",
            "Para ubicarla necesito DNI del titular o N.º de socio. ¿Me lo pasás?",
        ),
        PasoPlaybook(
            "derivar_solicitud_factura",
            "Si no aparece o hay que corregir datos fiscales, ¿te derivo?",
        ),
    ],
    "facturacion_estado_cuenta": [
        PasoPlaybook(
            "estado_cuenta_detalle",
            "¿Querés el saldo, el vencimiento o el estado de una factura?",
        ),
        PasoPlaybook(
            "identificar_cuenta",
            "Pasame DNI o N.º de socio y te digo lo que figura en el padrón, sin inventar montos.",
        ),
        PasoPlaybook(
            "validacion_estado",
            "¿Con ese dato te alcanza, o querés que te derive para revisarlo adentro?",
        ),
    ],
    "facturacion_reclamo": [
        PasoPlaybook(
            "detalle_importe",
            "¿De qué mes es la factura y qué monto ves (o cuánto era antes vs ahora)?",
        ),
        PasoPlaybook(
            "cambio_plan_o_servicios",
            "¿Cambiaste de plan, sumaste un servicio o te avisaron de un ajuste de tarifas?",
        ),
        PasoPlaybook(
            "identificar_cuenta",
            "Para mirar el detalle necesito DNI del titular o N.º de socio. ¿Me lo pasás?",
        ),
        PasoPlaybook(
            "confirmacion_diferencia",
            "Si después de ver el detalle la diferencia sigue, no te puedo prometer un ajuste. "
            "¿Te derivo con facturación?",
        ),
    ],
    "reactivacion_pago": [
        PasoPlaybook(
            "reactivacion_pago_detalle",
            "Si el pago ya está acreditado, la rehabilitación es automática; no hace falta avisarlo. "
            "¿El pago ya figura y el servicio sigue cortado?",
        ),
        PasoPlaybook(
            "plazo_reactivacion",
            "El tiempo de imputación depende del medio (QR, Rapipago, etc.). "
            "¿Hace cuánto pagaste y por qué medio?",
        ),
        PasoPlaybook(
            "identificar_reactivacion",
            "Pasame DNI o N.º de socio para ver estado y saldo reales. ¿Me lo pasás?",
        ),
        PasoPlaybook(
            "derivar_reactivacion",
            "Si ya pasó varias horas y sigue cortado, lo ve facturación. ¿Te derivo?",
        ),
    ],
    "internet_ftth": [
        PasoPlaybook("energia_ont", "Dale, arrancamos por fibra. ¿La cajita blanca tiene luces encendidas?"),
        PasoPlaybook("luces_los", "¿La luz PON está verde fija y la LOS apagada, o ves alguna en rojo?"),
        PasoPlaybook(
            "reinicio_ont",
            "Desenchufá ONT y router 30 segundos; prendé primero la ONT y después el router. ¿Volvió?",
        ),
        # Energía/UTP solamente. LOS roja → el motor escala a N2; no pedir manipular fibra.
        PasoPlaybook(
            "cable_fibra",
            "Sin tocar el cable amarillo de fibra: ¿el de energía y el de red (UTP) están firmes, sin daño visible?",
        ),
        PasoPlaybook(
            "servicio_tras_optica",
            "Con la fibra en verde el enlace óptico está bien. Probá abrir dos páginas. ¿Ya navega?",
        ),
        PasoPlaybook("wifi_vs_cable_ftth", "¿Falla también por cable al router, o solo el WiFi?"),
        PasoPlaybook(
            "turno_campo_ftth",
            "Con esto ya no lo resolvemos a distancia. ¿Querés que abra un ticket para visita técnica?",
        ),
    ],
    "internet_radio": [
        PasoPlaybook("poe_antena", "Ok, por antena (BAI). ¿La fuente PoE tiene la lucecita prendida?"),
        PasoPlaybook(
            "cable_wan_bai",
            "El cable del inyector PoE (salida LAN) va al puerto azul/Internet del router. "
            "No desconectes el de la antena si no está identificado. ¿Está así?",
        ),
        PasoPlaybook(
            "reinicio_cpe",
            "Reiniciá antena y router 30 segundos; prendé primero la antena. ¿Volvió?",
        ),
        PasoPlaybook("led_enlace", "¿El LED de enlace está fijo o parpadea/rojo?"),
        PasoPlaybook("linea_vista", "¿La antena sigue con vista libre a la torre?"),
        PasoPlaybook("zona_vecinos", "¿Les pasa también a vecinos, o solo en tu casa?"),
        PasoPlaybook(
            "validacion_navegacion_radio",
            "Después de estabilizar, ¿ya podés navegar en un equipo?",
        ),
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
        PasoPlaybook(
            "validacion_navegacion_adsl",
            "¿La luz DSL quedó fija y ya podés navegar?",
        ),
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
        PasoPlaybook(
            "confirmar_acceso",
            "Para no derivarte de más: ¿ves una cajita blanca con un cable amarillo (fibra), "
            "una antena en el techo, o el módem entra por el teléfono?",
        ),
    ],
    "internet_lento": [
        PasoPlaybook("cuantos_dispositivos", "¿Cuántos equipos hay conectados al WiFi ahora?"),
        PasoPlaybook(
            "medio_prueba",
            "¿La lentitud la notás por WiFi o también por cable al router?",
        ),
        PasoPlaybook("horario_lento", "¿Es lento todo el día o más a la tarde/noche?"),
        PasoPlaybook(
            "test_velocidad",
            "Si podés, hacé un test por cable en fast.com (no por WiFi) y decime cuánto da.",
        ),
        PasoPlaybook(
            "windows_update_hint",
            "Si usás PC con Windows, ¿hay una actualización descargándose? Eso a veces deja todo lento.",
        ),
        PasoPlaybook("reinicio_lento", "Reiniciá módem/router 30 segundos y probá de nuevo. ¿Mejoró?"),
        PasoPlaybook("comparar_plan", "Si sigue bajo, ¿querés que te pase con un agente?"),
    ],
    "wifi": [
        PasoPlaybook("zona_wifi", "¿El WiFi falla en toda la casa o solo lejos del router?"),
        PasoPlaybook(
            "conexion_cableada",
            "¿Por cable al router hay internet, o tampoco navega?",
        ),
        PasoPlaybook("otros_dispositivos_wifi", "¿Les pasa a todos los equipos o solo a uno?"),
        PasoPlaybook("reinicio_router_wifi", "¿Reiniciaste el router 30 segundos? ¿Mejoró?"),
        PasoPlaybook(
            "clave_wifi_etiqueta",
            "Si no recordás la clave WiFi, en la etiqueta del módem/router están el nombre y la clave de fábrica. ¿Pudiste entrar?",
        ),
        PasoPlaybook("banda_wifi", "Si tenés 2.4 y 5 GHz, ¿probaste la otra red?"),
        PasoPlaybook("canal_interferencia", "¿Podés alejar el router de microondas u otros equipos?"),
        PasoPlaybook("derivar_wifi", "Si sigue mal, ¿querés que te derive?"),
    ],
    "internet_intermitente": [
        PasoPlaybook(
            "alcance_cortes",
            "¿Los cortes te pasan en todos los equipos o solo en uno?",
        ),
        PasoPlaybook(
            "medio_conexion",
            "¿Se corta por WiFi, por cable al router, o por los dos?",
        ),
        PasoPlaybook(
            "frecuencia_cortes",
            "¿Cada cuánto se corta y cuánto tarda en volver?",
        ),
        PasoPlaybook(
            "luces_durante_corte",
            "Cuando se corta, ¿cambia o se apaga alguna luz del módem/ONT?",
        ),
        PasoPlaybook(
            "reinicio_intermitente",
            "Reiniciá el equipo 30 segundos y dejalo un rato. ¿Se mantuvo estable?",
        ),
        PasoPlaybook(
            "turno_campo_intermitente",
            "Si sigue cortándose hace falta técnico. ¿Abro el ticket?",
        ),
    ],
    "cambio_clave_wifi": [
        PasoPlaybook(
            "cambio_clave_wifi_detalle",
            "¿Querés cambiar la contraseña, el nombre de la red, o las dos cosas?",
        ),
        PasoPlaybook(
            "clave_wifi_etiqueta",
            "En la etiqueta del módem/router están el nombre y la clave de fábrica. "
            "¿Tenés acceso al equipo para cambiarla?",
        ),
        PasoPlaybook(
            "aviso_reconexion",
            "Después del cambio todos los dispositivos tienen que volver a conectarse con la clave nueva. ¿Listo para probar uno?",
        ),
        PasoPlaybook(
            "validacion_wifi_nueva",
            "¿Ese dispositivo conectó y navega con la configuración nueva?",
        ),
        PasoPlaybook(
            "derivar_clave_wifi",
            "Si no podés entrar al equipo o el cambio no queda, ¿querés que te derive?",
        ),
    ],
    "estado_reclamo": [
        PasoPlaybook(
            "estado_reclamo_detalle",
            "¿Tenés un reclamo o visita técnica abierta que quieras consultar?",
        ),
        PasoPlaybook(
            "dato_reclamo",
            "Pasame DNI, N.º de socio o el número de ticket si lo tenés.",
        ),
        PasoPlaybook(
            "derivar_reclamo",
            "El estado real lo confirma un agente con el sistema. ¿Te derivo para que te lo confirmen?",
        ),
    ],
    "movil": [
        PasoPlaybook(
            "sintoma_movil",
            "¿Qué te pasa con el móvil IMOWI: sin señal, sin datos, no podés llamar, o robo/pérdida?",
        ),
        PasoPlaybook("datos_roaming_check", "¿Datos móviles activos y modo avión apagado?"),
        PasoPlaybook("reinicio_imovi", "¿Probaste reiniciar el teléfono?"),
        PasoPlaybook("modo_avion", "Modo avión 15 segundos y desactivalo. ¿Volvió?"),
        PasoPlaybook(
            "apn_imovi",
            "Si es Android: Ajustes > Redes móviles/Conexiones > APN. "
            "Nombre = imowi, APN = apn1.catel.org.ar (resto en blanco). Guardá y elegí ese APN. "
            "Si es iPhone 11+ o eSIM suele ser automático; si es más viejo: "
            "Datos celulares > Opciones > Red de datos → APN apn1.catel.org.ar y usuario imowi. "
            "¿Me confirmás si es Android o iPhone y si quedó bien?",
        ),
        PasoPlaybook("otra_sim_o_tel", "Si podés, ¿probaste esa SIM en otro teléfono?"),
        PasoPlaybook(
            "robo_perdida_hint",
            "Si fue robo o pérdida: desde otra compañía marcá *910 (opción 4 – imowi); "
            "desde una línea imowi *303; desde fijo 0800-147-0303. ¿Necesitás reposición de SIM/eSIM?",
        ),
        PasoPlaybook("otra_ubicacion", "¿Te pasa solo en un lugar o en varios? ¿Querés que te derive?"),
    ],
    "movil_datos": [
        PasoPlaybook("datos_activados", "¿Datos móviles prendidos y sin modo avión?"),
        PasoPlaybook(
            "consumo_paquete",
            "¿Te quedan datos del abono o cargaste un pack/bono? "
            "Si se acabaron: WhatsApp mensajería suele seguir; para navegar el resto "
            "comprá un bono en Autogestión Batán (ov.batan.coop) u oficina — "
            "no uses la autogestión de imowi.com.ar. "
            "Si el pack/bono figura OK en el sistema pero NO navegás, "
            "no hace falta seguir tocando el celular: hay que revisar la línea.",
        ),
        PasoPlaybook(
            "so_dispositivo",
            "¿Qué marca y modelo de celular tenés? "
            "(si ya lo dijiste, seguimos con el APN de ese sistema)",
        ),
        PasoPlaybook(
            "apn_datos",
            # Instrucción interna del playbook: NO mezclar Android e iPhone en el mismo mensaje.
            "Android: Ajustes > Redes móviles/Conexiones > Nombres de punto de acceso (APN). "
            "Creá o editá Nombre = imowi, APN = apn1.catel.org.ar (resto en blanco). "
            "Guardá, seleccioná ese APN y reiniciá los datos. ¿Navega?",
        ),
        PasoPlaybook("roaming_datos", "¿Estás en tu zona habitual o de viaje?"),
        PasoPlaybook("prueba_wifi_off", "Apagá el WiFi del celular y probá solo datos. ¿Navega?"),
        PasoPlaybook("derivar_datos", "Si sigue, ¿querés que te derive?"),
    ],
    "movil_llamadas": [
        PasoPlaybook("tipo_problema_llamada", "¿No podés llamar, no te entran, o se cortan?"),
        PasoPlaybook("reinicio_llamadas", "Reiniciá y probá una llamada. ¿Anduvo?"),
        PasoPlaybook("modo_avion_llamadas", "Modo avión 15 segundos y volvé a probar. ¿Mejoró?"),
        PasoPlaybook(
            "sms_a2p_hint",
            "Si es un SMS de banco o app que no llega, suele ser validación A2P: probá otro medio (email/llamada). ¿Era eso o llamadas normales?",
        ),
        PasoPlaybook("otra_ubicacion_llamadas", "¿Te pasa en una sola zona o en varios lados?"),
        PasoPlaybook("derivar_llamadas", "Si sigue, ¿querés que te derive?"),
    ],
    "telefono_fija": [
        PasoPlaybook("tono_fija", "Dale, vamos con el fijo. ¿Al descolgar hay tono?"),
        PasoPlaybook(
            "alcance_aparatos_fija",
            "¿Te pasa en todos los teléfonos de la casa o solo en uno?",
        ),
        PasoPlaybook("cableado_fija", "¿El cable está bien enchufado en la toma de la pared?"),
        PasoPlaybook(
            "otro_telefono_fija",
            "Si podés, ¿probaste otro aparato en esa misma toma?",
        ),
        PasoPlaybook("ruido_linea_fija", "¿Hay ruido o estática en la línea al escuchar?"),
        PasoPlaybook(
            "adsl_misma_linea",
            "¿En esa misma línea tenés internet ADSL? Si sí, no saques el splitter/filtros.",
        ),
        PasoPlaybook(
            "derivar_fija",
            "Si sigue igual te derivo con N° de línea, tono sí/no y si hay ruido. ¿Abrimos el ticket?",
        ),
    ],
    "tv_sensa": [
        PasoPlaybook(
            "triaje_tv_sensa",
            "Dale, vamos con TV. ¿Es la app/web Sensa o la TV con decodificador / Android TV Box de la cooperativa?",
        ),
        PasoPlaybook(
            "internet_en_disp",
            "En el equipo donde querés verla, ¿tenés internet funcionando?",
        ),
        PasoPlaybook(
            "dispositivo_sensa",
            "¿Desde qué equipo: Smart TV, celular/tablet, PC o TV Box?",
        ),
        PasoPlaybook(
            "navega_en_disp",
            "En ese mismo equipo, ¿abrís alguna página de internet sin problema?",
        ),
        PasoPlaybook(
            "app_sensa",
            "¿La app o la web de Sensa abre bien, o ni llega a entrar?",
        ),
        PasoPlaybook(
            "sintoma_sensa",
            "Cuando querés ver algo: ¿no reproduce, se queda cargando, error de cuenta o calidad baja?",
        ),
        PasoPlaybook(
            "acciones_sensa",
            "Probá reiniciar ese equipo y el router, cerrar otras apps que usen mucha red "
            "y actualizar Sensa. ¿Mejoró?",
        ),
        PasoPlaybook(
            "derivar_sensa",
            "Si sigue igual te derivo con dispositivo, síntoma y lo que ya probamos. "
            "Packs premium o habilitación de cuenta los ve comercial. ¿Abrimos el ticket?",
        ),
    ],
    "ecolan_b2b": [
        PasoPlaybook(
            "tipo_ecolan",
            "Te ayudo con Ecolan. ¿Es PBX, Cloud/VM, housing/hosting, enlace dedicado/IP fija, "
            "VPN de sucursal, o una cotización/consulta comercial?",
        ),
        PasoPlaybook(
            "alcance_b2b",
            "¿Afecta a un solo usuario, a toda una sede/sucursal, o a todos los sitios?",
        ),
        PasoPlaybook(
            "impacto_sla",
            "¿Hay un servicio caído ahora con impacto operativo, o es una consulta/cotización "
            "sin urgencia?",
        ),
        PasoPlaybook(
            "prueba_minima_b2b",
            "Si está caído: ¿probaste desde otro enlace o hotspot celular, y reiniciar el CPE "
            "del enlace? Contame qué pasó.",
        ),
        PasoPlaybook(
            "derivar_ecolan",
            "Si sigue caído o necesitás especialista Ecolan (SLA/visita), ¿te derivo? "
            "Si es solo cotización, puedo pasarte el contacto comercial sin abrir ticket técnico.",
        ),
    ],
    "alta_plan": [
        PasoPlaybook("tipo_alta", "¿Alta nueva o cambio de plan? ¿Internet, móvil, Sensa u otro?"),
        PasoPlaybook("zona_comercial", "¿En qué barrio o localidad lo necesitás?"),
        PasoPlaybook("derivar_comercial", "Te paso con comercial. ¿Te derivo?"),
    ],
    "portal_tramites": [
        PasoPlaybook(
            "info_batan_coop",
            "Podés usar Mi Cuenta en ov.batan.coop o batan.coop. ¿Qué trámite necesitás?",
        ),
        PasoPlaybook("derivar_tramites", "Si hace falta operador, ¿querés que te derive?"),
    ],
    "turno_campo": [
        PasoPlaybook("confirmar_turno", "Para la visita hace falta un mayor de edad. ¿Pueden recibirla?"),
        PasoPlaybook("derivar_agenda", "Un agente te ofrece horarios. ¿Abro el ticket de turno?"),
    ],
    "general": [
        PasoPlaybook(
            "menu_servicio",
            f"{frase_soy_eko()}. "
            "¿En qué te ayudo: internet, telefonía móvil, teléfono fijo, Sensa/TV, factura o algo más?",
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


def destino_n2_canal(intencion: str) -> tuple[str, str]:
    """Destino y etiqueta de proveedor para un N2 del canal abonado.

    Internet hogareño / visita de campo → cooperativa.
    Móvil IMOWI → NOC. No mandar FTTH al destino de red móvil.
    """
    intent = (intencion or "").strip()
    if intent.startswith("movil"):
        return "imowi_noc", "NOC"
    if intent == "ecolan_b2b":
        return "cooperativa", "Ecolan"
    return "cooperativa", "Cooperativa / campo"


def tiene_internet_fijo(servicio_abonado: str) -> bool:
    """True si el padrón indica internet fijo (fibra/radio/ADSL)."""
    return (servicio_abonado or "").strip().lower() in ("internet", "ambos")


def tiene_movil_contratado(servicio_abonado: str) -> bool:
    """True si el padrón indica línea móvil IMOWI."""
    return (servicio_abonado or "").strip().lower() in ("movil", "ambos")


def texto_menu_consulta(servicio_abonado: str) -> str:
    """Menú N1 según servicios contratados (no ofrecer lo que no figura)."""
    s = (servicio_abonado or "").strip().lower()
    if s == "movil":
        return (
            "¿Tu consulta es por el servicio de telefonía móvil o por factura/deuda?"
        )
    if s == "internet":
        return "¿Tu consulta es por internet o por factura/deuda?"
    if s == "ambos":
        return (
            "¿Tu consulta es por internet, por el servicio de telefonía móvil, "
            "o por factura/deuda?"
        )
    return (
        "¿En qué te puedo ayudar: internet, telefonía móvil, factura/deuda "
        "u otra consulta?"
    )


def texto_menu_tipo_consulta() -> str:
    """Segundo paso tras elegir telefonía móvil."""
    return (
        "Dale. ¿Es un tema técnico, comercial, "
        "o administrativo referente a la facturación?"
    )


def parse_menu_servicio(texto: str) -> str | None:
    """Respuesta al 1.er menú: movil | internet | facturacion | None."""
    t = (texto or "").lower().strip()
    if not t:
        return None
    # Typos frecuentes: «,ovil», «ovil», «mvil» (móvil)
    compacto = (
        t.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    compacto = re.sub(r"[^a-z0-9]+", "", compacto)
    if compacto in {
        "ovil",
        "mvil",
        "movl",
        "movi",
        "movil",
        "celular",
        "imowi",
        "imovi",
    }:
        return "movil"
    # "no tengo internet" no es elegir diagnóstico de fibra
    if niega_producto_internet(texto):
        return None
    if any(
        k in t
        for k in (
            "factura",
            "deuda",
            "pago",
            "saldo",
            "boleta",
            "administrativ",
            "cobro",
            "cuenta",
        )
    ) and not any(k in t for k in ("móvil", "movil", "celular", "telefon", "datos")):
        return "facturacion"
    if any(
        k in t
        for k in (
            "telefonía móvil",
            "telefonia movil",
            "telefonía movil",
            "telefonia móvil",
            "servicio de telefon",
            "línea móvil",
            "linea movil",
            "móvil",
            "movil",
            "celular",
            "imowi",
            "imovi",
            # Síntoma en vez de elegir el ítem del menú (Patricia / Jorge)
            "sin datos",
            "no tengo datos",
            "no me andan los datos",
            "no anda el dato",
            "no andan los datos",
            "datos del celu",
            "datos del celular",
            "datos movil",
            "datos móvil",
            "datos moviles",
            "datos móviles",
            "internet del celular",
            "se me acabaron los datos",
            "bono de datos",
            "sin señal",
            "sin senal",
            "apn",
        )
    ):
        return "movil"
    if any(k in t for k in ("internet", "fibra", "wifi", "wi-fi", "router", "onu")):
        return "internet"
    if any(k in t for k in ("factura", "deuda", "pago", "saldo", "boleta")):
        return "facturacion"
    return None


def resolver_menu_servicio(texto: str, servicio_abonado: str = "") -> str | None:
    """Opción de menú o síntoma clasificado (el abonado suele repetir el problema)."""
    elec = parse_menu_servicio(texto)
    if elec:
        return elec
    intent = clasificar_intencion(texto, servicio_abonado)
    if intent in ("movil", "movil_datos", "movil_llamadas") or str(intent).startswith(
        "movil"
    ):
        return "movil"
    if intent in (
        "internet",
        "internet_ftth",
        "internet_radio",
        "internet_adsl",
        "internet_lento",
        "internet_intermitente",
        "wifi",
        "cambio_clave_wifi",
    ) or str(intent).startswith("internet"):
        return "internet"
    if intent in (
        "facturacion",
        "corte_deuda",
        "reactivacion_pago",
    ) or str(intent).startswith("factur"):
        return "facturacion"
    return None


def parse_menu_tipo_consulta(texto: str) -> str | None:
    """Respuesta al 2.º menú: tecnico | comercial | facturacion | None."""
    t = (texto or "").lower().strip()
    if not t:
        return None
    if any(
        k in t
        for k in (
            "administrativ",
            "factur",
            "deuda",
            "pago",
            "boleta",
            "saldo",
            "cobro",
        )
    ):
        return "facturacion"
    if any(
        k in t
        for k in (
            "comercial",
            "plan",
            "alta",
            "baja",
            "contratar",
            "pack",
            "promo",
            "venta",
        )
    ):
        return "comercial"
    if any(
        k in t
        for k in (
            "técnico",
            "tecnico",
            "técnica",
            "tecnica",
            "señal",
            "senal",
            "datos",
            "no anda",
            "no funciona",
            "sin servicio",
            "falla",
            "chip",
            "sim",
            "llamar",
            "llamada",
            "sin datos",
            "no tengo datos",
            "apn",
            "4g",
            "5g",
        )
    ):
        return "tecnico"
    return None


def resolver_menu_tipo_consulta(texto: str, servicio_abonado: str = "") -> str | None:
    """2.º menú o síntoma técnico/comercial/factura."""
    tipo = parse_menu_tipo_consulta(texto)
    if tipo:
        return tipo
    intent = clasificar_intencion(texto, servicio_abonado)
    if intent in ("movil", "movil_datos", "movil_llamadas") or str(intent).startswith(
        "movil"
    ):
        return "tecnico"
    if intent == "alta_plan":
        return "comercial"
    if intent in (
        "facturacion",
        "corte_deuda",
        "reactivacion_pago",
    ) or str(intent).startswith("factur"):
        return "facturacion"
    return None


def texto_sin_internet_contratado(servicio_abonado: str, *, insistencia: int = 1) -> str:
    """El abonado habla de internet pero el padrón no tiene internet fijo.

    ``insistencia``: 1 = primer aviso; 2+ = mensaje distinto (sin loop literal).
    """
    movil = tiene_movil_contratado(servicio_abonado)
    if insistencia <= 1:
        if movil:
            return (
                "En tu cuenta no figura internet fijo contratado. "
                "¿Te ayudo con el servicio de telefonía móvil o con la factura?"
            )
        return (
            "En tu cuenta no figura internet fijo contratado. "
            "¿Es por factura/deuda u otra consulta?"
        )
    if insistencia == 2:
        if movil:
            return (
                "Te lo aclaro de otra forma: en el padrón no hay internet de casa "
                "(fibra/radio). Si no te anda «internet» en el celular, es el servicio "
                "móvil (datos IMOWI): escribí *móvil*. Si es un tema de factura, "
                "*factura*. Si igual querés una persona, escribí *agente*."
            )
        return (
            "Te lo aclaro de otra forma: en el padrón no figura internet fijo. "
            "¿Es por factura/deuda u otra consulta? Si preferís una persona, "
            "escribí *agente*."
        )
    # 3+: última oferta antes de derivar si insiste
    if movil:
        return (
            "Sigo sin ver internet fijo en tu cuenta. Puedo ayudarte con *móvil* "
            "o *factura*, o te derivo con un agente si escribís *agente*."
        )
    return (
        "Sigo sin ver internet fijo en tu cuenta. ¿Factura/deuda u otra consulta? "
        "Si querés agente, escribí *agente*."
    )


def niega_producto_internet(texto: str) -> bool:
    """True si dice que no tiene / no contrató internet (no un corte)."""
    t = (texto or "").lower()
    return any(
        k in t
        for k in (
            "no tengo internet",
            "no tengo el internet",
            "no tengo fibra",
            "no tengo internet fijo",
            "sin internet fijo",
            "no es internet",
            "no tengo servicio de internet",
            "no contraté internet",
            "no contrate internet",
            "no tengo contratado internet",
            "no tengo contratado el internet",
        )
    )


_SALUDOS_SOLO = frozenset(
    {
        "hola",
        "hola hola",
        "buenas",
        "buen dia",
        "buen día",
        "buenas tardes",
        "buenas noches",
        "hey",
        "holis",
        "hol",
        "ola",
        "hi",
        "hello",
    }
)


def es_saludo_solo(texto: str) -> bool:
    """True solo si el mensaje ES un saludo (no 'hola no me anda internet')."""
    t = (texto or "").lower().strip()
    t = re.sub(r"[¡!.,¿?]+", "", t).strip()
    return bool(t) and t in _SALUDOS_SOLO


def intencion_es_internet(intencion: str) -> bool:
    intent = (intencion or "").strip()
    return intent.startswith("internet") or intent in (
        "wifi",
        "internet_lento",
        "cambio_clave_wifi",
    )


INTENCIONES_FACTURACION = frozenset({
    "corte_deuda",
    "facturacion",
    "facturacion_pago",
    "facturacion_descarga",
    "facturacion_informar_pago",
    "facturacion_factura",
    "facturacion_estado_cuenta",
    "facturacion_reclamo",
    "reactivacion_pago",
})


def intencion_es_facturacion(intencion: str) -> bool:
    return (intencion or "").strip() in INTENCIONES_FACTURACION


def ajustar_intencion_a_padron(
    intencion: str,
    servicio_abonado: str,
    texto: str = "",
) -> str:
    """No abrir diagnóstico de un producto que el padrón no tiene."""
    _ = texto
    if not intencion_es_internet(intencion):
        return intencion
    if tiene_internet_fijo(servicio_abonado):
        return intencion
    # Solo si el padrón dice explícitamente "solo móvil". Vacío = desconocido.
    if (servicio_abonado or "").strip().lower() == "movil":
        return "general"
    return intencion


def declara_solo_movil_sin_fijo(texto: str, servicio_abonado: str = "") -> bool:
    """True si aclara que no tiene internet fijo y solo usa móvil/IMOWI.

    No confundir con corte (“me quedé sin internet”). El padrón se aplica
    después en `ajustar_intencion_a_padron` (si solo tiene móvil, no es corte).
    """
    _ = servicio_abonado
    t = (texto or "").lower()
    if any(
        k in t
        for k in (
            "solo tengo imowi",
            "solo imowi",
            "solo tengo imovi",
            "solo imovi",
            "solo tengo móvil",
            "solo tengo movil",
            "solo móvil",
            "solo movil",
            "solo tengo celular",
            "solo celular",
            "solo tengo telefonía móvil",
            "solo tengo telefonia movil",
            "solo telefonía móvil",
            "solo telefonia movil",
            "únicamente móvil",
            "unicamente movil",
            "nada más que el móvil",
            "nada mas que el movil",
        )
    ):
        return True
    afirma_movil = any(
        k in t
        for k in (
            "imowi",
            "imovi",
            "móvil",
            "movil",
            "celular",
            "telefonía móvil",
            "telefonia movil",
            "línea móvil",
            "linea movil",
        )
    )
    niega_fijo = any(
        k in t
        for k in (
            "no tengo internet",
            "no tengo el internet",
            "no tengo fibra",
            "sin internet fijo",
            "no tengo fijo",
            "no es internet",
            "no tengo servicio de internet",
            "no contraté internet",
            "no contrate internet",
        )
    )
    return bool(afirma_movil and niega_fijo)


def _menciona_tv_sensa(texto: str) -> bool:
    """True si el mensaje apunta a TV OTT Sensa (no cable genérico ambiguo)."""
    t = (texto or "").lower()
    if any(
        k in t
        for k in (
            "sensa",
            "televisión ott",
            "television ott",
            "tv ott",
            "ott sensa",
            "smart tv",
            "tv box",
            "android tv",
            "televisor",
            "televisión",
            "television",
            "ver la tele",
            "ver tele",
            "ver la tv",
            "ver tv",
            "no anda la tele",
            "no funciona la tele",
            "no puedo ver tele",
            "no puedo ver la tele",
            "no veo la tele",
            "no veo tele",
            "la tele no",
            "la tv no",
        )
    ):
        return True
    # "tv" / "t.v." como palabra (evitar matching dentro de otras)
    return bool(
        re.search(
            r"(?<![a-záéíóúüñ0-9])t\.?v\.?(?![a-záéíóúüñ0-9])",
            t,
            flags=re.IGNORECASE,
        )
    )


def clasificar_intencion(texto: str, servicio_abonado: str = "") -> str:
    intent = _clasificar_intencion_core(texto, servicio_abonado)
    return ajustar_intencion_a_padron(intent, servicio_abonado, texto)


def _clasificar_intencion_facturacion(t: str) -> str | None:
    """Parte facturación al estilo Botmaker; si hay varios motivos, queda el enrutador."""
    hits: list[str] = []

    if any(
        k in t
        for k in (
            "pagué y sigue",
            "pague y sigue",
            "pagué y no anda",
            "pague y no anda",
            "pagué y sigue cortado",
            "pague y sigue cortado",
            "no se reactiv",
            "no se rehabil",
        )
    ) or (
        any(k in t for k in ("ya pagué", "ya pague", "pagué", "pague"))
        and any(k in t for k in ("cortado", "suspend", "sin servicio", "no se reactiva"))
    ):
        hits.append("reactivacion_pago")

    if any(
        k in t
        for k in (
            "me cortaron",
            "me lo cortaron",
            "cortaron el servicio",
            "cortaron por",
            "corte por deuda",
            "por falta de pago",
            "sin servicio por deuda",
            "suspendido por",
            "si me lo cortaron",
            "sí me lo cortaron",
        )
    ):
        hits.append("corte_deuda")

    if re.search(r"\b(todavia|todavía|aun|aún)\s+no\s+(pag|abon)", t):
        hits.append("corte_deuda")
    elif re.search(r"\bno\s+(lo\s+)?(pague|pagué|abone|aboné)\b", t) and any(
        k in t
        for k in (
            "cort",
            "servicio",
            "deuda",
            "factura",
            "pasa",
            "todavia",
            "todavía",
            "aun",
            "aún",
            "internet",
            "sé",
            "se ",
        )
    ):
        hits.append("corte_deuda")

    if any(
        k in t
        for k in (
            "ya pagué",
            "ya pague",
            "ya aboné",
            "ya abone",
            "informar pago",
            "informar un pago",
            "avisar el pago",
            "avisar un pago",
            "avisar que pag",
            "avisar que abon",
            "quiero avisar",
            "queria avisar",
            "quería avisar",
            "aviso de pago",
            "pague recien",
            "pagué recién",
            "pague recién",
            "pagué recien",
            "acabo de pagar",
            "recien pague",
            "recién pagué",
            "no figura el pago",
            "no se acredit",
            "no se refleja",
            "pagué pero",
            "pague pero",
            "comprobante de pago",
        )
    ):
        hits.append("facturacion_informar_pago")

    if any(
        k in t
        for k in (
            "descargar factura",
            "descargar la factura",
            "descargar boleta",
            "talón",
            "talon de pago",
            "talón de pago",
            "cupón de pago",
            "cupon de pago",
            "copia de factura",
            "copia de la factura",
            "copia de boleta",
            "pdf de la factura",
        )
    ):
        hits.append("facturacion_descarga")

    if any(
        k in t
        for k in (
            "no me llegó la factura",
            "no me llego la factura",
            "mandame la factura",
            "enviame la factura",
            "envíame la factura",
            "enviar factura",
            "factura por mail",
            "factura por correo",
            "necesito la factura",
            "recibir factura",
        )
    ):
        hits.append("facturacion_factura")

    if any(
        k in t
        for k in (
            "aumento",
            "aumentó",
            "mas cara",
            "más cara",
            "cobro de más",
            "cobro de mas",
            "me cobraron de más",
            "me cobraron de mas",
            "no reconozco",
            "cobro que no",
            "importe mal",
            "factura distinta",
        )
    ):
        hits.append("facturacion_reclamo")

    if any(
        k in t
        for k in (
            "estado de mi cuenta",
            "estado de cuenta",
            "estado de la cuenta",
            "consultar cuenta",
            "consulta de cuenta",
            "saldo de cuenta",
            "cómo está mi cuenta",
            "como esta mi cuenta",
            "cuanto debo",
            "cuánto debo",
            "si tengo deuda",
            "tengo deuda",
            "consultar deuda",
            "consultar saldo",
            "ver mi saldo",
            "ver el saldo",
            "cuanto me vino",
            "cuánto me vino",
            "vencimiento",
        )
    ):
        hits.append("facturacion_estado_cuenta")

    if any(
        k in t
        for k in (
            "como pago",
            "cómo pago",
            "quiero pagar",
            "medios de pago",
            "pagar factura",
            "pagar la factura",
            "pagar con qr",
            "donde pago",
            "dónde pago",
            "para abonar",
            "web para abonar",
            "como abono",
            "cómo abono",
        )
    ):
        hits.append("facturacion_pago")

    generic = any(
        k in t
        for k in (
            "factura",
            "factur",
            "boleta",
            "saldo",
            "deuda",
            "pago",
            "qr",
            "fiserv",
            "mercado pago",
            "cuenta corriente",
            "resumen",
            "recibo",
            "abonar",
        )
    )
    if generic:
        hits.append("facturacion")

    if not hits:
        return None
    if "corte_deuda" in hits:
        return "corte_deuda"
    if "reactivacion_pago" in hits:
        return "reactivacion_pago"
    uniq: list[str] = []
    for h in hits:
        if h not in uniq:
            uniq.append(h)
    especificos = [h for h in uniq if h != "facturacion"]
    if len(especificos) == 1:
        return especificos[0]
    if len(especificos) > 1:
        return "facturacion"
    return "facturacion"


def _clasificar_intencion_core(texto: str, servicio_abonado: str = "") -> str:
    t = (texto or "").lower().replace("fatura", "factura")

    if es_saludo_solo(t):
        return "general"

    # Corrección frecuente: “no tengo internet, solo IMOWI”
    if declara_solo_movil_sin_fijo(t, servicio_abonado):
        if any(k in t for k in ("datos", "navega", "4g", "5g", "sin señal", "sin senal")):
            return "movil_datos"
        if any(k in t for k in ("llamar", "llamada", "sms")):
            return "movil_llamadas"
        return "movil"

    if any(k in t for k in (
        "data center", "datacenter", "ecolan", "central virtual", "pbx",
        "housing", "hosting", "maquina virtual", "máquina virtual", " cloud",
        "enlace dedicado", "starlink", "ip fija", "vpn sucursal", "sla",
        "cotizacion ecolan", "cotización ecolan", "presupuesto enlace",
        "vpn de sucursal", "vm en el data", "vm en el datacenter",
    )):
        return "ecolan_b2b"

    if any(k in t for k in (
        "batan.coop", "tramite", "trámite", "portal web", "facturacion electronica",
        "facturación electrónica",
    )):
        return "portal_tramites"

    billed = _clasificar_intencion_facturacion(t)
    if billed:
        return billed

    if any(k in t for k in (
        "dar de alta", "alta", "cambio de plan", "cambiar plan", "mejorar plan",
        "contratar", "baja", "quiero el plan",
        "dar de baja imowi", "baja imowi", "arrepentimiento",
    )):
        return "alta_plan"

    if any(k in t for k in (
        "telefono fijo", "teléfono fijo", "linea fija", "línea fija",
        "telefonia fija", "telefonía fija", "sin tono",
        "fijo ecolan", "telefono ecolan", "teléfono ecolan",
        "no me llaman al fijo", "no me entra al fijo", "no anda el fijo",
        "no funciona el fijo", "mi fijo", "el fijo no",
    )):
        return "telefono_fija"

    # TV OTT Sensa — antes de internet genérico. Si además niega internet fijo,
    # priorizar el árbol de conectividad (dependencia de Sensa).
    if _menciona_tv_sensa(t):
        if any(
            k in t
            for k in (
                "sin internet",
                "no tengo internet",
                "no anda internet",
                "no funciona internet",
                "internet cortado",
                "me quedé sin internet",
                "me quede sin internet",
            )
        ):
            return "internet"
        return "tv_sensa"

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
        "cambiar clave wifi", "cambiar la clave del wifi", "cambiar contraseña wifi",
        "cambiar la contraseña del wifi", "cambiar nombre wifi", "cambiar el nombre del wifi",
        "cambiar ssid", "nueva clave wifi", "cambiar password wifi",
        "cambiar la clave de wifi", "cambiar contraseña de wifi",
    )):
        return "cambio_clave_wifi"

    if any(k in t for k in (
        "wifi", "wi-fi", "señal wifi", "no llega wifi", "wifi no funciona",
    )):
        return "wifi"

    if any(k in t for k in (
        "se corta", "se cortan", "intermiten", "intermitente",
        "va y viene", "se cae y vuelve", "se me cae", "se cae el internet",
        "a cada rato se corta",
        "cada tanto se corta",
    )):
        return "internet_intermitente"

    if any(k in t for k in (
        "estado de mi reclamo", "estado del reclamo", "cómo va mi reclamo",
        "como va mi reclamo", "cómo va el reclamo", "como va el reclamo",
        "seguimiento del reclamo", "número de reclamo", "numero de reclamo",
        "estado de la visita técnica", "estado de la visita tecnica",
    )):
        return "estado_reclamo"

    if any(k in t for k in (
        "modem", "módem", "router", "internet fijo",
        "sin internet", "no anda internet", "internet", "no navego",
        "no cargo", "pagina", "página",
        # typos / coloquial frecuentes
        "interntt", "internt", "internte", "intenet", "inteernet",
        "no anda nada", "no me carga nada", "sin servi", "cajita blanca",
    )):
        return "internet"

    if any(k in t for k in (
        "datos movil", "datos móvil", "datos moviles", "datos móviles",
        "sin datos", "no tengo datos", "no me andan los datos",
        "no anda el dato", "no andan los datos", "datos del celu",
        "datos del celular", "datos no funcionan", "internet del celular",
        "apn", "se me acabaron los datos", "bono de datos", "comprar datos",
    )):
        return "movil_datos"

    if any(k in t for k in (
        "llamada", "sms", "no puedo llamar", "no me llegan llamadas",
        "se cortan las llamadas", "mensaje de texto",
        "sms de verificacion", "sms de verificación", "codigo por sms",
        "código por sms", "a2p",
        "correo de voz", "buzon de voz", "buzón de voz", "*333",
    )):
        return "movil_llamadas"

    if any(k in t for k in (
        "imowi", "imovi", "imovu", "señal", "senal",
        "chip", "4g", "5g", "celular", "móvil", "movil",
        "sim", "linea movil", "línea móvil",
        "*910", "*303", "robo el celular", "me robaron el celu", "me robaron el celular",
        "perdi el celular", "perdí el celular", "celular robado", "sim robada",
        "esim", "e-sim", "reemplazo de chip", "reponer sim",
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


def refinar_playbook_internet(texto: str) -> str | None:
    """Sale del triaje `internet` hacia tecnología o síntoma (wifi/lento/cortes)."""
    tech = refinar_intencion_internet(texto)
    if tech:
        return tech
    t = (texto or "").lower()
    if any(
        k in t
        for k in (
            "solo el wifi",
            "solo wifi",
            "solo el wi-fi",
            "solo wi-fi",
            "solo el wi fi",
            "es el wifi",
            "es el wi-fi",
            "no llega el wifi",
            "wifi no llega",
            "el wifi no",
        )
    ):
        return "wifi"
    if any(
        k in t
        for k in (
            "lento",
            "lenta",
            "velocidad",
            "speed",
            "tarda",
            "demora",
            "baja velocidad",
        )
    ):
        return "internet_lento"
    if any(
        k in t
        for k in (
            "se corta",
            "se cortan",
            "intermiten",
            "va y viene",
            "se cae y vuelve",
            "se me cae",
        )
    ):
        return "internet_intermitente"
    return None


def _token_en_texto(texto: str, token: str) -> bool:
    """Match de token con límites de palabra para evitar 'si'∈'quisiera'."""
    t = (token or "").lower().strip()
    if not t:
        return False
    # Frases multi-palabra: substring alcanza
    if " " in t or len(t) > 4:
        return t in texto
    return bool(
        re.search(
            rf"(?<![a-záéíóúüñ0-9]){re.escape(t)}(?![a-záéíóúüñ0-9])",
            texto,
            flags=re.IGNORECASE,
        )
    )


def es_saludo_corto(texto: str) -> bool:
    t = (texto or "").lower().strip()
    t = re.sub(r"[¡!.,¿?]+", "", t).strip()
    if not t or len(t) > 40:
        return False
    saludos = (
        "hola", "hola hola", "buenas", "buen dia", "buen día", "buenas tardes",
        "buenas noches", "hey", "holis", "hol", "ola", "hi", "hello",
    )
    return t in saludos or any(t == s or t.startswith(s + " ") for s in saludos)


def parece_consulta_nueva(texto: str) -> bool:
    """Apertura clara de un tema nuevo (no una respuesta a mitad de flujo)."""
    t = (texto or "").lower().strip()
    if len(t) < 14:
        return False
    aperturas = (
        "quisiera consultar",
        "quería consultar",
        "queria consultar",
        "quiero consultar",
        "necesito consultar",
        "necesito ayuda con",
        "tengo un problema",
        "tengo un reclamo",
        "quiero hacer un reclamo",
        "me podes ayudar",
        "me podés ayudar",
        "estado de mi cuenta",
        "estado de cuenta",
        "consultar el estado",
        "dar de baja",
        "cambiar de plan",
        "otro tema",
        "otra consulta",
        "en realidad es por",
        "ahora es por",
        "no es un problema tecnico",
        "no es un problema técnico",
        "necesito saber cuanto",
        "necesito saber cuánto",
        "queria saber cuanto",
        "quería saber cuánto",
        "queria saber cuanto",
    )
    return any(k in t for k in aperturas)


def dominio_intencion(intencion: str) -> str:
    """Agrupa intenciones del mismo servicio/tema (para detectar cambio de dominio)."""
    intent = (intencion or "").strip()
    if not intent or intent in ("general", "multi_tema"):
        return "general"
    if intent.startswith("movil"):
        return "movil"
    if intencion_es_facturacion(intent) or intent in (
        "corte_deuda",
        "reactivacion_pago",
        "aviso_deuda",
    ):
        return "facturacion"
    if intent.startswith("internet") or intent in ("wifi", "cambio_clave_wifi"):
        return "internet"
    if intent == "tv_sensa":
        return "tv_sensa"
    if intent == "telefono_fija":
        return "telefono_fija"
    if intent == "ecolan_b2b":
        return "ecolan_b2b"
    return intent


def _senal_fuerte_dominio(texto: str, dominio: str) -> bool:
    """Keywords claras de apertura del dominio destino (no mención incidental).

    Evita que respuestas mid-playbook («sí, internet anda», «apagué el WiFi…»)
    disparen cambio de tema por reclasificación genérica.
    """
    t = (texto or "").lower()
    if dominio == "movil":
        return any(
            k in t
            for k in (
                "se me acabaron los datos",
                "acabaron los datos",
                "sin datos",
                "no tengo datos",
                "no me andan los datos",
                "no anda el dato",
                "no andan los datos",
                "datos del abono",
                "datos del celu",
                "datos del celular",
                "datos móvil",
                "datos movil",
                "datos móviles",
                "datos moviles",
                "internet del celular",
                "imowi",
                "bono de datos",
                "pack de datos",
                "sin señal",
                "sin senal",
                "no me llega el sms",
                "sms del banco",
                "no puedo llamar",
                "no me andan las llamadas",
            )
        )
    if dominio == "tv_sensa":
        return "sensa" in t
    if dominio == "internet":
        return any(
            k in t
            for k in (
                "sin internet",
                "no tengo internet",
                "no anda internet",
                "no funciona internet",
                "internet cortado",
                "me quedé sin internet",
                "me quede sin internet",
                "internet lento",
                "anda lento",
                "fibra",
                "router",
                "onu",
                "antena",
                "adsl",
                "wifi no",
                "no llega wifi",
                "no anda el wifi",
                "no funciona el wifi",
                "no anda wifi",
                "cambiar clave wifi",
                "cambiar la clave del wifi",
                "se corta el internet",
                "se me cae el internet",
                "se cae el internet",
            )
        )
    if dominio == "facturacion":
        return any(
            k in t
            for k in (
                "factura",
                "boleta",
                "deuda",
                "saldo",
                "pagar",
                "pagué",
                "pague",
                "cobro",
                "aumento",
            )
        )
    if dominio == "telefono_fija":
        return any(
            k in t
            for k in (
                "fijo",
                "sin tono",
                "línea fija",
                "linea fija",
                "teléfono fijo",
                "telefono fijo",
            )
        )
    if dominio == "ecolan_b2b":
        return any(
            k in t
            for k in ("ecolan", "data center", "datacenter", "enlace dedicado")
        )
    return False


def es_cambio_tema_claro(
    texto: str,
    intencion_actual: str,
    servicio_abonado: str = "",
) -> str | None:
    """Si el mensaje abre otro dominio de servicio, retorna la nueva intención.

    Usa clasificación sin padrón/servicio para no inventar tema por default del abonado.
    No dispara con respuestas cortas de diagnóstico (sí/no, smart tv, modelo, etc.).
    Requiere señal fuerte del dominio nuevo (no basta reclasificar por keywords débiles).
    """
    _ = servicio_abonado
    actual = (intencion_actual or "").strip()
    if not actual or actual in ("general", "multi_tema", "aviso_deuda"):
        return None
    t = (texto or "").strip()
    if len(t) < 12:
        return None
    # Sí/no cortos o frases de 1–4 tokens típicas de playbook
    palabras = t.split()
    if len(palabras) <= 4 and respuesta_paso_ok(texto) is not None:
        return None
    # Sin fallback de servicio: solo keywords del mensaje
    nueva = clasificar_intencion(texto, "")
    if not nueva or nueva == "general":
        return None
    dom_nueva = dominio_intencion(nueva)
    if dom_nueva == dominio_intencion(actual):
        return None
    if not _senal_fuerte_dominio(texto, dom_nueva):
        return None
    return nueva


def confirma_contacto_sin_servicio(texto: str) -> bool:
    """True si solo dice que le contestaron/llamaron, sin confirmar que el servicio anda.

    Evita cerrar N1 / encuesta ante «si me contestó» (p.ej. Whisper: «si me contesto»).
    """
    t = (texto or "").lower().strip()
    t = re.sub(r"[¡!.,¿?]+", " ", t)
    t = " ".join(t.split())
    if not t or len(t) > 120:
        return False
    # «me llamo X» = nombre; no es callback
    if re.search(r"\bme llamo\b", t) and "llamaron" not in t and "llamó" not in t:
        return False
    if not any(
        k in t
        for k in (
            "me contest",
            "me respondieron",
            "me contactaron",
            "me llamaron",
            "me llamó",
            "me llamo,",
            "ya me contest",
            "ya me llam",
        )
    ):
        return False
    if any(
        k in t
        for k in (
            "anda",
            "funciona",
            "anduvo",
            "solucion",
            "resuelto",
            "volvió",
            "volvio",
            "mejoró",
            "mejoro",
            "ya está",
            "ya esta",
            "todo bien",
        )
    ):
        return False
    return True


def respuesta_paso_ok(texto: str) -> bool | None:
    t = (texto or "").lower().strip()
    if not t:
        return None
    # Saludos y consultas nuevas no son sí/no de un paso de playbook
    if es_saludo_corto(t) or parece_consulta_nueva(t):
        return None
    # «me contestó» ≠ paso OK de servicio (ni cierre N1)
    if confirma_contacto_sin_servicio(t):
        return None
    # Respuestas informativas con "aún no / no lo pagué" ≠ fallo de diagnóstico
    if re.search(r"\b(aun|aún|todavia|todavía)\s+no\b", t):
        return None
    if re.search(r"\bno\s+lo\s+(pague|pagué|pago)\b", t):
        return None
    if re.search(r"\bporque\s+quiero\b", t) or "motivo del" in t or "motivo de" in t:
        return None
    palabras_ok = (
        "si", "sí", "ok", "dale", "listo", "hecho", "verificado", "ya",
        "mejoro", "mejoró", "volvio", "volvió", "anda", "funciona",
        "anduvo", "perfecto", "genial",
    )
    if any(p in t for p in ("no funciona", "no anda", "sigue sin", "tampoco", "peor")):
        return False
    if _token_en_texto(t, "no") or any(
        _token_en_texto(t, p) for p in ("sigue", "persiste", "igual", "nada", "falla", "mal")
    ):
        # "no" suelto en frases largas informativas → no forzar fallo
        if len(t.split()) >= 6 and not any(
            p in t for p in ("no funciona", "no anda", "sigue sin", "sigue igual", "tampoco")
        ):
            return None
        return False
    if any(_token_en_texto(t, p) if len(p) <= 4 else p in t for p in palabras_ok):
        return True
    return None


def es_afirmacion_estado_movil(texto: str) -> bool:
    """Confirma señal/datos/reinicio («si tengo»), no acepta ni pide ticket N2."""
    t = (texto or "").lower().strip()
    t = re.sub(r"[¡!.,¿?]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return False
    exactos = {
        "si tengo",
        "sí tengo",
        "si, tengo",
        "sí, tengo",
        "si la tengo",
        "sí la tengo",
        "si lo tengo",
        "sí lo tengo",
        "tengo señal",
        "si tengo señal",
        "sí tengo señal",
        "tengo senal",
        "si tengo senal",
        "reinicie",
        "reinicié",
        "ya reinicie",
        "ya reinicié",
        "si reinicie",
        "sí reinicié",
        "listo reinicie",
        "listo reinicié",
    }
    if t in exactos:
        return True
    if t.startswith(("si tengo ", "sí tengo ", "si, tengo ", "sí, tengo ")):
        return True
    return False


def acepta_derivacion_clara(texto: str) -> bool:
    """True solo si el abonado acepta handoff (no «si tengo» / señal)."""
    if es_afirmacion_estado_movil(texto):
        return False
    t = (texto or "").lower().strip()
    if not t:
        return False
    if any(
        k in t
        for k in (
            "deriv",
            "ticket",
            "agente",
            "operador",
            "abrí",
            "abri",
            "abrí el",
            "pasame",
            "pasame con",
            "quiero que me deriven",
        )
    ):
        return True
    # «sí» / «dale» cortos sin «tengo»
    if "tengo" in t:
        return False
    ok = respuesta_paso_ok(texto)
    if ok is True and len(t.split()) <= 3:
        return True
    return False


def _texto_blob_historial(historial) -> str:
    parts: list[str] = []
    for m in historial or []:
        if isinstance(m, dict):
            parts.append(str(m.get("texto") or m.get("contenido") or ""))
        else:
            parts.append(str(getattr(m, "texto", "") or ""))
    return " ".join(parts).lower()


def contexto_diagnostico_wifi(historial, *, intencion: str = "") -> bool:
    """True si el hilo es diagnóstico WiFi/cobertura (repetidor, router, etc.)."""
    intent = (intencion or "").strip()
    if intent in ("wifi", "cambio_clave_wifi"):
        return True
    blob = _texto_blob_historial(historial)
    if any(k in blob for k in ("repetidor", "rayita", "rayitas")):
        return True
    wifi_markers = ("wifi", "wi-fi", "wi fi", "router", "televisor", "smart tv")
    if any(k in blob for k in wifi_markers) and any(
        k in blob for k in ("señal", "senal", "potencia", "cobertura", "llega", "rayita")
    ):
        return True
    return False


def pregunta_confirmacion_mejora_senal_wifi(
    texto: str,
    historial=None,
    *,
    intencion: str = "",
) -> bool:
    """Abonado pregunta si una mejora de señal (repetidor/rayitas) alcanza para resolver.

    No es cierre/resolución («ya anda»); es confirmación («¿eso me va a solucionar?»).
    """
    t = (texto or "").lower().strip()
    if not t or indica_resuelto(texto):
        return False
    if not contexto_diagnostico_wifi(historial, intencion=intencion):
        return False
    confirmacion = any(
        k in t
        for k in (
            "me va a solucionar",
            "va a solucionar",
            "va a solucionar el problema",
            "eso me soluciona",
            "con eso alcanza",
            "eso alcanza",
            "con eso me alcanza",
            "me va a servir",
            "va a andar bien",
            "va a funcionar",
            "me alcanza",
        )
    ) or (
        "?" in t
        and any(k in t for k in ("alcanza", "soluciona", "sirve", "funciona"))
    )
    if not confirmacion:
        return False
    mejora = any(
        k in t
        for k in (
            "rayita",
            "rayitas",
            "mas potencia",
            "más potencia",
            "mejor señal",
            "mejor senal",
            "mas señal",
            "más señal",
            "veo mas",
            "veo más",
            "subio la señal",
            "subió la señal",
            "mejora la señal",
            "mejora la senal",
            "mejora las señal",
            "potencia",
        )
    )
    return mejora or "repetidor" in _texto_blob_historial(historial)


def mensaje_confirmacion_mejora_senal_wifi(
    texto: str,
    historial=None,
) -> str:
    blob = _texto_blob_historial(historial) + " " + (texto or "").lower()
    zona = ""
    if "cocina" in blob:
        zona = " en la cocina"
    elif "televisor" in blob or " smart tv" in blob:
        zona = " en el televisor"
    elif "habitacion" in blob or "habitación" in blob:
        zona = " en esa habitación"
    elif "baño" in blob or "bano" in blob:
        zona = " en el baño"
    return (
        f"Sí, con más señal en el repetidor debería andar bien{zona}. "
        "Probá conectarte un rato y avisame si sigue fallando."
    )


def indica_resuelto(texto: str) -> bool:
    """El abonado indica que el servicio ya volvió / funciona.

    Requiere anclas claras («ya…», «volvió», «quedó…»). Evita falsos positivos
    como «en el living anda bien, lejos no».
    """
    t = (texto or "").lower().strip()
    if not t:
        return False
    if parece_consulta_nueva(t) or es_saludo_corto(t):
        return False
    # «me contestó / me llamaron» ≠ servicio OK
    if confirma_contacto_sin_servicio(t):
        return False
    # Problema parcial / contraste → nunca cerrar como resuelto
    if any(
        x in t
        for x in (
            "no anda",
            "no funciona",
            "sigue sin",
            "no volvio",
            "no volvió",
            "no mejoro",
            "no mejoró",
            "consultar",
            "quisiera",
            "quiero",
            "pero",
            "lejos",
            "solo en",
            "sólo en",
            "excepto",
            "no llega",
            "sigue mal",
            "sigue igual",
            "en el fondo",
            "habitacion",
            "habitación",
        )
    ):
        return False
    claves = (
        "ya anda",
        "ya funciona",
        "ya volvio",
        "ya volvió",
        "ya mejoró",
        "ya mejoro",
        "mejoró todo",
        "mejoro todo",
        "quedó bien",
        "quedo bien",
        "quedó resuelto",
        "quedo resuelto",
        "ya esta",
        "ya está",
        "ya quedó",
        "ya quedo",
        "se solucionó",
        "se soluciono",
        "ahora sí",
        "ahora si",
        "volvió todo",
        "volvio todo",
        "todo bien ahora",
        "funcionaba bien",
        "funciona bien",
        "ya me funciona",
        "ya me funcionaba",
        "me funcionaba bien",
        "ahora funciona",
        "ahora funcionaba",
        "ahora ya me",
        "ahora ya funciona",
        "ya andaba",
        "me anda bien",
        "me andaba bien",
    )
    if any(k in t for k in claves):
        return True
    # Pide cerrar el caso / ticket tras confirmar que anda
    if any(
        k in t
        for k in (
            "cerrar el ticket",
            "cierra el ticket",
            "cerrá el ticket",
            "cerra el ticket",
            "puede cerrar",
            "podes cerrar",
            "podés cerrar",
            "podes cerrarlo",
            "podés cerrarlo",
            "cerralo",
            "cerralo por favor",
        )
    ) and any(
        k in t
        for k in (
            "gracias",
            "funcion",
            "anda",
            "bien",
            "solucion",
            "resuelto",
            "impecable",
            "perfecto",
            "listo",
        )
    ):
        return True
    # Respuesta corta a «¿Mejoró?» / «¿Volvió?»
    if _token_en_texto(t, "mejoró") or _token_en_texto(t, "mejoro"):
        return True
    if _token_en_texto(t, "volvió") or _token_en_texto(t, "volvio"):
        return True
    return False


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
    # Negaciones frecuentes: no son pedido de agente/técnico.
    for neg in (
        "no es un problema tecnico",
        "no es un problema técnico",
        "no es problema tecnico",
        "no es problema técnico",
        "no es tecnico",
        "no es técnico",
        "no quiero tecnico",
        "no quiero técnico",
        "no necesito tecnico",
        "no necesito técnico",
        "sin tecnico",
        "sin técnico",
    ):
        t = t.replace(neg, " ")
    t = " ".join(t.split())
    # Respuesta corta al menú «técnico / comercial / administrativo» ≠ pedir agente
    if t in (
        "tecnico",
        "técnico",
        "tecnica",
        "técnica",
        "tema tecnico",
        "tema técnico",
        "problema tecnico",
        "problema técnico",
        "es tecnico",
        "es técnico",
    ):
        return False
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
            "atiendan",
            "atiendeme",
            "atiéndeme",
            "atenderme",
            "me atiendan",
            "me atienda",
            "que me atiendan",
            "asesor",
            "que me llamen",
            "llamenme",
            "llámenme",
            "me llamen",
            "representante",
            "quiero hablar",
            "pasar con alguien",
            # Pedido explícito de técnico/visita (no la palabra suelta del menú)
            "quiero un tecnico",
            "quiero un técnico",
            "quiero tecnico",
            "quiero técnico",
            "necesito un tecnico",
            "necesito un técnico",
            "mandame un tecnico",
            "mandame un técnico",
            "mande un tecnico",
            "mande un técnico",
            "manda un tecnico",
            "manda un técnico",
            "envie un tecnico",
            "envíe un técnico",
            "venir un tecnico",
            "venir un técnico",
            "que venga un tecnico",
            "que venga un técnico",
            "que venga",
            "visita tecnica",
            "visita técnica",
            "deberia venir",
            "debería venir",
            "tienen que venir",
            "tiene que venir",
            "atiendan ya",
            "ahora mismo",
        )
    )


def pide_humano_en_flujo_activo(texto: str, ctx: dict) -> bool:
    """True si pide persona/técnico estando ya en un diagnóstico N1."""
    if not pide_humano(texto):
        return False
    intent = str(ctx.get("intencion") or "").strip()
    if not intent or intent == "general":
        return False
    turnos = int(ctx.get("diag_turnos") or 0)
    paso = int(ctx.get("paso_idx") or 0)
    return turnos >= 1 or paso >= 1


def detectar_temas_duales(texto: str) -> list[str]:
    """Detecta si el mensaje mezcla tema técnico y facturación.

    Retorna p.ej. ['tecnico', 'facturacion'] cuando hay ambos.
    """
    t = (texto or "").lower().replace("fatura", "factura")

    # "factura de internet" / "cuánto me vino ... internet" = factura del servicio,
    # no falla técnica + factura a la vez.
    factura = any(
        k in t
        for k in (
            "factura",
            "factur",
            "aumento",
            "aumentó",
            "boleta",
            "tarifa",
            "cobro",
            "saldo",
            "deuda",
            "pago",
            "abonar",
            "más cara",
            "mas cara",
            "subió",
            "subio",
            "cuanto me vino",
            "cuánto me vino",
        )
    )
    sintomas_tecnicos = any(
        k in t
        for k in (
            "wifi",
            "wi-fi",
            "señal",
            "senal",
            "router",
            "módem",
            "modem",
            "ont",
            "fibra",
            "lento",
            "lenta",
            "anda mal",
            "anda cada vez peor",
            "cada vez peor",
            "no anda",
            "no funciona",
            "corte de línea",
            "sin servicio",
            "cajita",
            "sin internet",
            "se corta",
            "reiniciar",
            "sensa",
            "televisión",
            "television",
            "televisor",
            "smart tv",
            "tv box",
        )
    )
    # Mención de "internet"/IMOWI/Sensa solo cuenta como técnico si hay síntoma
    # o si NO hay marco de factura/pago.
    menciona_servicio = any(
        k in t
        for k in (
            "internet",
            "conexión",
            "conexion",
            "imowi",
            "imovi",
            "móvil",
            "movil",
            "celular",
            "chip",
            "4g",
            "5g",
            "sensa",
            "televisión",
            "television",
        )
    )
    tecnico = sintomas_tecnicos or (menciona_servicio and not factura)

    out: list[str] = []
    if tecnico:
        out.append("tecnico")
    if factura:
        out.append("facturacion")
    return out


def resolver_prioridad_tema(texto: str) -> str | None:
    """Interpreta la elección del cliente tras preguntar prioridad doble-tema."""
    t = (texto or "").lower().replace("fatura", "factura")
    # Ambos: no forzar
    if any(k in t for k in ("los dos", "ambas", "los dos temas", "las dos")):
        return "facturacion"  # factura suele ser más rápida; luego técnico
    if any(
        k in t
        for k in (
            "internet",
            "wifi",
            "conexión",
            "conexion",
            "señal",
            "senal",
            "router",
            "técnico",
            "tecnico",
            "la conexión",
            "la conexion",
            "lo técnico",
            "lo tecnico",
            "primero internet",
            "por el internet",
            "imowi",
            "móvil",
            "movil",
            "celular",
            "por el móvil",
            "por el movil",
            "sensa",
            "televisión",
            "television",
            "la tele",
            "por la tele",
            "por sensa",
        )
    ):
        return "tecnico"
    if any(
        k in t
        for k in (
            "factura",
            "factur",
            "aumento",
            "boleta",
            "tarifa",
            "cobro",
            "pago",
            "plata",
            "precio",
            "monto",
            "la cuenta",
        )
    ):
        return "facturacion"
    return None


def intencion_desde_tema(tema: str, texto_original: str = "") -> str:
    """Mapea tema dual → intención concreta."""
    if tema == "facturacion":
        if texto_original:
            intent = clasificar_intencion(texto_original)
            if intencion_es_facturacion(intent):
                return intent
        return "facturacion"
    # técnico: reclasificar con el texto original si aporta, si no internet genérico
    if texto_original:
        intent = clasificar_intencion(texto_original)
        if not intencion_es_facturacion(intent) and intent not in (
            "general",
            "portal_tramites",
            "alta_plan",
        ):
            return intent
    return "internet"


def es_escape_agente(texto: str) -> bool:
    """Escape hatch documentado: *agente* / «agente» solo → handoff inmediato."""
    t = (texto or "").lower().strip()
    if not t:
        return False
    compact = re.sub(r"\s+", "", t)
    if compact in ("*agente*", "agente", "*agente"):
        return True
    return bool(re.fullmatch(r"\*+\s*agente\s*\*+", t))


def contiene_sintoma_canal(texto: str) -> bool:
    """True si el mensaje trae un síntoma/consulta N1 además del pedido de humano."""
    t = (texto or "").lower()
    return any(
        k in t
        for k in (
            "internet",
            "wifi",
            "wi-fi",
            "fibra",
            "antena",
            "router",
            "modem",
            "módem",
            "datos",
            "señal",
            "senal",
            "llamada",
            "factura",
            "pago",
            "deuda",
            "saldo",
            "qr",
            "corte",
            "lento",
            "ont",
            "adsl",
            "imowi",
            "celular",
            "móvil",
            "movil",
            "tono",
            "fijo",
            "sensa",
            "televisión",
            "television",
            "televisor",
            "smart tv",
            "tv box",
            "*910",
            "robo",
            "sim",
            "no anda",
            "no funciona",
            "sin servicio",
            "sin internet",
            "cajita",
            "internt",
        )
    )


def normalizar_queja(texto: str) -> str:
    t = (texto or "").lower().strip()
    t = " ".join(t.split())
    return t[:160]


def misma_queja(texto: str, ctx: dict) -> bool:
    actual = normalizar_queja(texto)
    if len(actual) < 8:
        return False
    prev = str(ctx.get("ultima_queja") or "").strip()
    return bool(prev and actual == prev)


def detecta_frustracion(texto: str, ctx: dict) -> bool:
    """True si reitera la misma queja *después* de avance N1 real (paso_idx ≥ 2).

    No abre ticket por repetir el síntoma al inicio del playbook (triaje).
    Tampoco si el mensaje es una respuesta de diagnóstico (reinicio, luces, cable).
    """
    intent = str(ctx.get("intencion") or "")
    if intent in (
        "internet",
        "wifi",
        "internet_lento",
        "internet_intermitente",
        "internet_adsl",
        "cambio_clave_wifi",
        "ecolan_b2b",
        "facturacion",
        "facturacion_pago",
        "facturacion_descarga",
        "facturacion_informar_pago",
        "facturacion_factura",
        "facturacion_estado_cuenta",
        "facturacion_reclamo",
        "reactivacion_pago",
        "corte_deuda",
        "tv_sensa",
    ):
        return False
    if not misma_queja(texto, ctx):
        return False
    t = (texto or "").lower()
    if any(
        k in t
        for k in (
            "reinici",
            "desenchuf",
            "por cable",
            "living",
            "lejos",
            "pon",
            " los",
            "fibra",
            "equipos",
            "fast.com",
            "cajita",
            "wifi",
            "wi-fi",
            "lento",
            "noche",
            "etiqueta",
            "2.4",
            "5 ghz",
            "microondas",
        )
    ):
        return False
    return int(ctx.get("paso_idx") or 0) >= 2


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
        "internet_intermitente": "Internet intermitente",
        "wifi": "WiFi",
        "cambio_clave_wifi": "Clave WiFi",
        "estado_reclamo": "Estado de reclamo",
        "movil": "Móvil",
        "movil_datos": "Móvil datos",
        "movil_llamadas": "Móvil llamadas",
        "telefono_fija": "Telefonía fija",
        "tv_sensa": "TV Sensa",
        "ecolan_b2b": "Ecolan B2B",
        "corte_deuda": "Facturación/Pagos",
        "facturacion": "Facturación",
        "facturacion_pago": "Pago de factura",
        "facturacion_descarga": "Descarga de factura",
        "facturacion_informar_pago": "Aviso de pago",
        "facturacion_factura": "Solicitud de factura",
        "facturacion_estado_cuenta": "Estado de cuenta",
        "facturacion_reclamo": "Reclamo de factura",
        "reactivacion_pago": "Reactivación por pago",
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
