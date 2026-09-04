"""Orquestación BillTrack (api_service) + API Radius/NAS → estado PPPoE para el bot."""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.radius.client import RadiusNasClient
from app.radius.contract import EstadoConexionPPPoE, ServicioConectividad

logger = logging.getLogger("operations_hub")

# Umbrales de triage N1 según uptime de sesión
UPTIME_RECIENTE_SEG = 15 * 60  # < 15 min → recién reconectó
UPTIME_ESTABLE_SEG = 60 * 60  # ≥ 1 h → línea estable; indagar LAN/Wi‑Fi

RamaPPPoE = Literal["wifi_lan", "recien_conectado", "sin_sesion", ""]

# Pasos de playbook que el dato Radius vuelve innecesarios (no preguntar de nuevo).
PASOS_WAN_OPTICA = frozenset({
    "energia_ont",
    "luces_los",
    "reinicio_ont",
    "cable_fibra",
    "enlace_optico",
    "servicio_tras_optica",
    "tipo_acceso",
    "confirmar_acceso",
    "poe_antena",
    "cable_wan_bai",
    "reinicio_cpe",
    "led_enlace",
    "linea_vista",
    "reinicio_modem_adsl",
    "luces_adsl",
    "tono_linea",
    "filtro_splitter",
    "cable_telefono",
    "reinicio_lento",
    "luces_durante_corte",
    "reinicio_intermitente",
})

PASOS_LAN_WIFI_SPEEDTEST = frozenset({
    "test_velocidad",
    "cuantos_dispositivos",
    "medio_prueba",
    "horario_lento",
    "repetidores_lento",
    "windows_update_hint",
    "wifi_vs_cable_ftth",
    "zona_wifi",
    "conexion_cableada",
    "otros_dispositivos_wifi",
    "repetidor_wifi",
    "repetidor_ubicacion",
    "repetidor_cable_ap",
    "banda_wifi",
    "canal_interferencia",
    "alcance_cortes",
    "medio_conexion",
})


def parse_uptime_seconds(uptime: str) -> int | None:
    """Parsea uptime estilo MikroTik: 4d4h44m58s, 1w2d, 2h31m, 45m, 10s."""
    raw = (uptime or "").strip().lower().replace(" ", "")
    if not raw:
        return None
    if re.fullmatch(r"\d+", raw):
        return int(raw)
    total = 0
    matched = False
    for amount, unit in re.findall(r"(\d+)([wdhms])", raw):
        matched = True
        n = int(amount)
        if unit == "w":
            total += n * 7 * 24 * 3600
        elif unit == "d":
            total += n * 24 * 3600
        elif unit == "h":
            total += n * 3600
        elif unit == "m":
            total += n * 60
        else:
            total += n
    return total if matched else None


def formatear_uptime_humano(uptime: str) -> str:
    """Texto corto para el abonado: '4 días', '2 h', '10 min'."""
    secs = parse_uptime_seconds(uptime)
    raw = (uptime or "").strip()
    if secs is None:
        return raw
    if secs >= 86400:
        d = secs // 86400
        return f"{d} día" if d == 1 else f"{d} días"
    if secs >= 3600:
        h = secs // 3600
        return f"{h} h"
    if secs >= 60:
        m = secs // 60
        return f"{m} min"
    return f"{secs} s"


def clasificar_rama_pppoe(estado: EstadoConexionPPPoE) -> RamaPPPoE:
    if estado.online is False:
        return "sin_sesion"
    if estado.online is not True or not estado.sesion:
        return ""
    secs = parse_uptime_seconds(estado.sesion.uptime or "")
    if secs is not None and secs < UPTIME_RECIENTE_SEG:
        return "recien_conectado"
    if secs is None or secs >= UPTIME_ESTABLE_SEG:
        # Sin uptime parseable pero online → asumir estable (evitar reinicio genérico)
        return "wifi_lan"
    # Entre 15 min y 1 h: también LAN/Wi‑Fi
    return "wifi_lan"


def rama_pppoe_desde_texto(texto: str) -> RamaPPPoE:
    """Reconstruye la rama desde pppoe_triage / contexto del prompt."""
    t = texto or ""
    if "sin_sesion_ppp" in t:
        return "sin_sesion"
    if "recien_reconecto" in t:
        return "recien_conectado"
    if "linea_ok_indagar_wifi" in t or "NO pedir reinicio de ONT" in t:
        return "wifi_lan"
    return ""


def pasos_omitidos_por_rama_pppoe(rama: str) -> frozenset[str]:
    """Pasos del checklist que no hay que preguntar dada la sesión Radius."""
    if rama in ("wifi_lan", "recien_conectado"):
        return PASOS_WAN_OPTICA
    if rama == "sin_sesion":
        return PASOS_LAN_WIFI_SPEEDTEST
    return frozenset()


def enriquecer_pasos_por_pppoe(
    pasos_cubiertos: list[str] | None,
    contexto: str = "",
    *,
    rama: str = "",
) -> list[str]:
    """Marca cubiertos los pasos que Radius ya resolvió (WAN vs LAN/speedtest)."""
    r = (rama or "").strip() or rama_pppoe_desde_texto(contexto)
    omitir = pasos_omitidos_por_rama_pppoe(r)
    out = [str(x) for x in (pasos_cubiertos or []) if str(x).strip()]
    for pid in omitir:
        if pid not in out:
            out.append(pid)
    return out


def resolve_radius_client(db: Session | None = None) -> RadiusNasClient | None:
    from app.services.platform_settings import resolve_radius

    cfg = resolve_radius(db)
    if not cfg.get("enabled"):
        return None
    client = RadiusNasClient(
        base_url=str(cfg.get("base_url") or ""),
        api_key=str(cfg.get("api_key") or ""),
        token=str(cfg.get("token") or ""),
        timeout=float(cfg.get("timeout") or 8.0),
    )
    if not client.configured():
        return None
    return client


def consultar_conexion_pppoe(
    *,
    dni: str = "",
    client_number: str = "",
    login: str = "",
    db: Session | None = None,
) -> EstadoConexionPPPoE:
    """Resuelve servicio de conectividad + sesión PPP.

    Orden de identidad:
      1) login explícito
      2) client_number → api_service
      3) dni → api_person.client_number → api_service
    """
    from app.services import billtrack as bt

    servicios: list[ServicioConectividad] = []
    servicio: ServicioConectividad | None = None
    err = ""

    login_n = (login or "").strip()
    if not login_n:
        try:
            if (client_number or "").strip():
                servicios = bt.lookup_servicios_conectividad(
                    client_number=str(client_number).strip(), db=db
                )
            elif (dni or "").strip():
                servicios = bt.lookup_servicios_conectividad_por_dni(dni=str(dni).strip(), db=db)
            else:
                return EstadoConexionPPPoE(error="sin dni/client_number/login")
        except Exception as exc:
            logger.exception("BillTrack servicios conectividad falló")
            return EstadoConexionPPPoE(error=f"billtrack: {str(exc)[:120]}")

        servicio = bt.elegir_servicio_principal(servicios)
        if not servicio:
            return EstadoConexionPPPoE(
                servicios=servicios,
                error="sin servicio INTFO/INTBA/INTINA",
            )
        login_n = servicio.login
    else:
        try:
            if (client_number or "").strip():
                servicios = bt.lookup_servicios_conectividad(
                    client_number=str(client_number).strip(), db=db
                )
            elif (dni or "").strip():
                servicios = bt.lookup_servicios_conectividad_por_dni(dni=str(dni).strip(), db=db)
            for s in servicios:
                if s.login == login_n:
                    servicio = s
                    break
            if servicio is None and servicios:
                servicio = bt.elegir_servicio_principal(servicios)
        except Exception:
            logger.exception("BillTrack enrich servicio (login explícito) falló")

        if servicio is None:
            servicio = ServicioConectividad(login=login_n)

    client = resolve_radius_client(db)
    if client is None:
        return EstadoConexionPPPoE(
            servicio=servicio,
            servicios=servicios,
            error="radius api no configurada",
            fuente="billtrack",
        )

    sesion = client.sesion_para_login(login_n)
    if sesion.error and not sesion.online:
        err = sesion.error
    return EstadoConexionPPPoE(
        servicio=servicio,
        sesion=sesion,
        servicios=servicios,
        error=err,
        fuente="radius",
    )


def _tipo_servicio(estado: EstadoConexionPPPoE) -> str:
    if not estado.servicio:
        return "internet"
    return (
        estado.servicio.service_type_label
        or estado.servicio.product
        or estado.servicio.service_type_code
        or "internet"
    ).strip() or "internet"


def _detalle_sesion(estado: EstadoConexionPPPoE) -> str:
    if not estado.sesion:
        return ""
    bits: list[str] = []
    if estado.sesion.public_ip:
        bits.append(f"IP {estado.sesion.public_ip}")
    if estado.sesion.uptime:
        bits.append(f"hace {formatear_uptime_humano(estado.sesion.uptime)}")
    if not bits:
        return ""
    return f" ({', '.join(bits)})"


def mensaje_abonado_pppoe(
    estado: EstadoConexionPPPoE,
    *,
    deuda_positiva: bool = False,
) -> str | None:
    """Mensaje N1 ramificado según online/offline + uptime (+ deuda). None si no hay dato útil."""
    if not estado.servicio or not estado.servicio.login:
        return None
    if estado.sesion is None and estado.error:
        return None

    tipo = _tipo_servicio(estado)
    rama = clasificar_rama_pppoe(estado)
    detalle = _detalle_sesion(estado)

    if rama == "wifi_lan" and estado.sesion:
        if deuda_positiva:
            nota_deuda = (
                " Aunque figura saldo pendiente, tu sesión sigue activa: "
                "no parece un corte por mora."
            )
        else:
            nota_deuda = ""
        return (
            f"Revisé tu cuenta de {tipo}: la conexión está activa{detalle}. "
            f"La línea hasta la red está bien.{nota_deuda} "
            "¿No te anda en ningún dispositivo o solo por Wi‑Fi? "
            "¿Probaste con cable al router?"
        )

    if rama == "recien_conectado" and estado.sesion:
        return (
            f"Revisé tu cuenta de {tipo}: la conexión está activa{detalle}. "
            "Recién reconectó; dale uno o dos minutos y probá navegar. "
            "¿Ya te anda o sigue igual?"
        )

    if rama == "sin_sesion" or estado.online is False:
        if deuda_positiva:
            return (
                f"Revisé tu cuenta de {tipo}: en este momento no hay sesión activa "
                "(no figurás conectado en la red). "
                "Con saldo pendiente a veces hay corte; también puede ser el equipo apagado. "
                "¿Reiniciaste el router/ONT (desenchufar 30 segundos)? "
                "¿Las luces de la cajita están prendidas?"
            )
        return (
            f"Revisé tu cuenta de {tipo}: en este momento no hay sesión activa "
            "(tu usuario no figura conectado en la red). "
            "¿Podés reiniciar el router/ONT (desenchufar 30 segundos) y avisarme "
            "si vuelve a conectar? ¿Las luces de la cajita están prendidas?"
        )
    return None


def triage_pppoe_para_prompt(estado: EstadoConexionPPPoE) -> str:
    """Hint corto para el system prompt en turnos siguientes."""
    rama = clasificar_rama_pppoe(estado)
    if rama == "wifi_lan":
        return (
            "triage=linea_ok_indagar_wifi_vs_cable; "
            "NO pedir reinicio de ONT como primer paso"
        )
    if rama == "recien_conectado":
        return "triage=recien_reconecto; pedir prueba de navegación"
    if rama == "sin_sesion":
        return (
            "triage=sin_sesion_ppp; reinicio ONT/router y luces; "
            "NO pedir speedtest ni fast.com"
        )
    return ""


def contexto_pppoe_para_abonado(
    abonado: Any | None,
    *,
    db: Session | None = None,
) -> dict[str, str]:
    """Claves string para enrich_contexto_desde_integraciones."""
    empty = {
        "pppoe_estado": "",
        "pppoe_login": "",
        "pppoe_tipo": "",
        "pppoe_ip": "",
        "pppoe_uptime": "",
        "pppoe_nas": "",
        "pppoe_resumen": "",
        "pppoe_triage": "",
        "pppoe_producto": "",
        "pppoe_plan_mbps": "",
    }
    if abonado is None:
        return empty

    dni = str(getattr(abonado, "dni", "") or "").strip()
    client_number = str(getattr(abonado, "client_number", "") or "").strip()
    if not dni and not client_number:
        return empty

    if resolve_radius_client(db) is None:
        return empty

    try:
        estado = consultar_conexion_pppoe(dni=dni, client_number=client_number, db=db)
    except Exception as exc:
        logger.exception("contexto_pppoe falló")
        empty["pppoe_resumen"] = f"error: {str(exc)[:80]}"
        return empty

    out = dict(empty)
    if estado.servicio:
        out["pppoe_login"] = estado.servicio.login
        out["pppoe_tipo"] = (
            estado.servicio.service_type_label
            or estado.servicio.product
            or estado.servicio.service_type_code
        )
        if estado.servicio.product or estado.servicio.label:
            out["pppoe_producto"] = (estado.servicio.product or estado.servicio.label).strip()
        from app.services.velocidad_plan import extraer_mbps_plan

        mbps = extraer_mbps_plan(
            estado.servicio.product,
            estado.servicio.label,
            estado.servicio.service_type_label,
        )
        if mbps is not None:
            out["pppoe_plan_mbps"] = f"{mbps:g}"
    if estado.sesion:
        out["pppoe_nas"] = estado.sesion.nas
        out["pppoe_ip"] = estado.sesion.public_ip
        out["pppoe_uptime"] = estado.sesion.uptime
        if estado.online is True:
            out["pppoe_estado"] = "conectado"
        elif estado.online is False:
            out["pppoe_estado"] = "desconectado"
        else:
            out["pppoe_estado"] = "sin_dato"
    elif estado.error:
        out["pppoe_estado"] = "sin_dato"
    out["pppoe_resumen"] = estado.resumen_prompt()
    out["pppoe_triage"] = triage_pppoe_para_prompt(estado)
    return out
