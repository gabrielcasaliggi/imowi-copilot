"""Orquestación BCM → estado de ONU/ONT FTTH para el bot.

El cliente se busca por número de cliente ERP (BillTrack client_number / base_account_number).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.bcm.client import BcmClient, clasificar_optica
from app.bcm.contract import EstadoOnuBcm, RamaBcm

logger = logging.getLogger("operations_hub")

RX_VISITA_DBM = -27.0
RX_IDEAL_DBM = -24.0

_RE_RX_DBM = re.compile(r"rx=(-?\d+(?:\.\d+)?)\s*dBm", re.IGNORECASE)


def resolve_bcm_client(db: Session | None = None) -> BcmClient | None:
    from app.services.platform_settings import resolve_bcm

    cfg = resolve_bcm(db)
    if not cfg.get("enabled"):
        return None
    client = BcmClient(
        base_url=str(cfg.get("base_url") or ""),
        user=str(cfg.get("user") or ""),
        app_pass=str(cfg.get("app_pass") or ""),
        timeout=float(cfg.get("timeout") or 12.0),
        verify_ssl=bool(cfg.get("verify_ssl", True)),
    )
    if not client.configured():
        return None
    return client


def clasificar_rama_bcm(estado: EstadoOnuBcm) -> RamaBcm:
    if not estado.encontrado:
        return ""
    if estado.online is False:
        return "onu_offline"
    if estado.online is True and requiere_visita_por_optica(estado):
        return "potencia_mala"
    if estado.online is True:
        return "enlace_ok"
    if requiere_visita_por_optica(estado):
        return "potencia_mala"
    return ""


def requiere_visita_por_optica(estado: EstadoOnuBcm) -> bool:
    """True si RX está fuera de parámetro GPON (< -27 dBm o saturación)."""
    if not estado.encontrado:
        return False
    if estado.calidad_optica == "mala":
        return True
    if estado.rx_dbm is not None and estado.rx_dbm < RX_VISITA_DBM:
        return True
    return False


def _texto_calidad_optica(calidad: str, dbm: float | None) -> str:
    if calidad == "buena":
        return "buena"
    if calidad == "aceptable":
        return "aceptable"
    if calidad == "mala":
        return "baja"
    if dbm is not None and dbm >= RX_IDEAL_DBM:
        return "buena"
    if dbm is not None and dbm >= RX_VISITA_DBM:
        return "aceptable"
    if dbm is not None:
        return "baja"
    return "sin dato"


def mensaje_informe_potencia_onu(estado: EstadoOnuBcm) -> str:
    """Responde la potencia óptica RX de la ONU."""
    if not estado.encontrado or estado.rx_dbm is None:
        return (
            "No pude leer la potencia de tu ONT en este momento. "
            "¿El servicio no te anda en ningún dispositivo o solo por Wi‑Fi?"
        )
    dbm = estado.rx_dbm
    calidad = estado.calidad_optica or clasificar_optica(dbm)
    txt = _texto_calidad_optica(calidad, dbm)
    from app.services.barra_senal import anexar_antes_de_preguntas, bloque_potencia_onu

    cuerpo = (
        f"Tu ONT está recibiendo {dbm:.1f} dBm, potencia {txt}. "
        f"Lo ideal es estar por encima de {RX_IDEAL_DBM:.0f} dBm "
        f"o al menos por encima de {RX_VISITA_DBM:.0f} dBm."
    )
    return anexar_antes_de_preguntas(cuerpo, bloque_potencia_onu(dbm))


def mensaje_visita_onu_por_optica(estado: EstadoOnuBcm) -> str:
    olt = f" en {estado.olt_nombre}" if estado.olt_nombre else ""
    if estado.online is False:
        return (
            "Revisé tu ONT en la red y no está registrada en la central"
            f"{olt}. Con eso ya no alcanza seguir a distancia: te derivo con un agente "
            "para coordinar una visita y revisar la ONT y el cable de fibra."
        )
    detalle = ""
    if estado.rx_dbm is not None:
        calidad = estado.calidad_optica or clasificar_optica(estado.rx_dbm)
        detalle = (
            f" ({estado.rx_dbm:.1f} dBm, potencia {_texto_calidad_optica(calidad, estado.rx_dbm)})"
        )
    return (
        f"Revisé tu ONT: está en línea pero la potencia óptica está fuera de parámetro"
        f"{detalle}. Eso suele requerir revisión en el domicilio o en la red. "
        "Te derivo con un agente para coordinar una visita técnica."
    )


def aplicar_bcm_a_ctx(ctx: dict, onu: EstadoOnuBcm) -> None:
    """Persiste telemetría BCM en el contexto de la conversación."""
    ctx["bcm_resumen"] = onu.resumen_prompt()
    ctx["bcm_triage"] = triage_bcm_para_prompt(onu)
    ctx["bcm_rama"] = clasificar_rama_bcm(onu)
    if onu.rx_dbm is not None:
        ctx["bcm_rx_dbm"] = f"{onu.rx_dbm:g}"
    if onu.calidad_optica:
        ctx["bcm_calidad_optica"] = onu.calidad_optica
    if onu.online is True:
        ctx["bcm_online"] = "1"
        ctx["ont_estado"] = "en_linea"
    elif onu.online is False:
        ctx["bcm_online"] = "0"
        ctx["ont_estado"] = "fuera_de_linea"
    if onu.olt_nombre:
        ctx["bcm_olt"] = onu.olt_nombre
        ctx["olt_huawei"] = onu.olt_nombre
    if onu.serial:
        ctx["bcm_serial"] = onu.serial
    if clasificar_rama_bcm(onu) == "enlace_ok":
        ctx["pppoe_rama"] = ctx.get("pppoe_rama") or "wifi_lan"


def parse_rx_dbm_desde_resumen(resumen: str) -> float | None:
    m = _RE_RX_DBM.search(resumen or "")
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def parse_bcm_desde_contexto(contexto_abonado: str) -> dict[str, Any]:
    """Extrae triage/RX del bloque CONTEXTO_ABONADO."""
    ctx = contexto_abonado or ""
    triage = ""
    for line in ctx.splitlines():
        low = line.strip().lower()
        if low.startswith("- bcm_triage:"):
            triage = line.split(":", 1)[1].strip()
            break
    resumen = ""
    for line in ctx.splitlines():
        low = line.strip().lower()
        if low.startswith("- bcm:"):
            resumen = line.split(":", 1)[1].strip()
            break
    rx = parse_rx_dbm_desde_resumen(resumen)
    calidad = ""
    m_cal = re.search(r"calidad=(buena|aceptable|mala)", resumen, re.IGNORECASE)
    if m_cal:
        calidad = m_cal.group(1).lower()
    online: bool | None = None
    if "estado=en_linea" in resumen or "estado=en linea" in resumen:
        online = True
    elif "estado=fuera_de_linea" in resumen or "estado=fuera de linea" in resumen:
        online = False
    return {
        "triage": triage,
        "resumen": resumen,
        "rx_dbm": rx,
        "calidad_optica": calidad,
        "online": online,
    }


def es_servicio_ftth(servicio: Any | None) -> bool:
    if servicio is None:
        return False
    from app.domain.flujos_abonado import playbook_internet_desde_tipo_servicio

    pb = playbook_internet_desde_tipo_servicio(
        str(getattr(servicio, "service_type_code", "") or ""),
        str(getattr(servicio, "service_type_label", "") or ""),
    )
    return pb == "internet_ftth"


def mensaje_abonado_bcm(
    estado: EstadoOnuBcm,
    *,
    es_ftth: bool = True,
) -> str | None:
    """Mensaje N1 según ONU. None si no hay dato útil o no es FTTH."""
    if not es_ftth:
        return None
    if not estado.encontrado or estado.error:
        return None
    rama = clasificar_rama_bcm(estado)

    from app.services.barra_senal import (
        anexar_antes_de_preguntas,
        bloque_potencia_onu,
        veredicto_optica,
    )

    barra = bloque_potencia_onu(estado.rx_dbm)
    if rama == "onu_offline":
        msg = (
            "Revisé tu ONT en la red: en este momento no está registrada en la central. "
            "¿El equipo tiene alguna lucecita prendida (PON o LOS)?"
        )
        return anexar_antes_de_preguntas(msg, barra)
    if rama == "potencia_mala":
        ver = veredicto_optica(estado.rx_dbm) or "está baja"
        msg = (
            "Revisé tu ONT: está en línea con la central, pero la potencia óptica "
            f"{ver}. ¿El cablecito amarillo está firme, sin dobleces ni pisadas?"
        )
        return anexar_antes_de_preguntas(msg, barra)
    if rama == "enlace_ok":
        ver = veredicto_optica(estado.rx_dbm) or "se ve bien"
        msg = (
            f"Revisé tu ONT: está en línea y la potencia óptica {ver}. "
            "¿No te anda en ningún dispositivo o solo por Wi‑Fi? "
            "¿Probaste con cable al router?"
        )
        return anexar_antes_de_preguntas(msg, barra)
    return None


def triage_bcm_para_prompt(estado: EstadoOnuBcm) -> str:
    rama = clasificar_rama_bcm(estado)
    if rama == "onu_offline":
        return "triage=onu_ftth_offline; chequear luces PON/LOS; no pedir Wi‑Fi primero"
    if rama == "potencia_mala":
        return "triage=onu_ftth_potencia_mala; cable amarillo; no pedir reinicio de router como primer paso"
    if rama == "enlace_ok":
        return (
            "triage=onu_ftth_enlace_ok; indagar Wi‑Fi vs cable; "
            "NO pedir reinicio de ONT como primer paso"
        )
    if estado.error:
        return ""
    if not estado.encontrado:
        return "triage=onu_no_encontrada_bcm"
    return ""


def resolver_numero_cliente_bcm(abonado: Any, db: Session | None) -> str:
    nro = str(getattr(abonado, "client_number", "") or "").strip()
    if nro:
        return nro
    dni = str(getattr(abonado, "dni", "") or "").strip()
    if not dni:
        return ""
    try:
        from app.services import billtrack as bt

        hit = bt.lookup_abonado_por_dni(dni, db=db) or {}
        nro = str(hit.get("client_number") or "").strip()
        if nro:
            return nro
        servicios = bt.lookup_servicios_conectividad_por_dni(dni=dni, db=db)
        svc = bt.elegir_servicio_principal(servicios)
        return str(getattr(svc, "base_account_number", "") or "").strip() if svc else ""
    except Exception:
        logger.exception("BCM: no se pudo resolver numero_cliente BillTrack")
        return ""


def consultar_onu_bcm(
    numero_cliente: str,
    *,
    db: Session | None = None,
) -> EstadoOnuBcm:
    nro = (numero_cliente or "").strip()
    if not nro:
        return EstadoOnuBcm(numero_cliente="", error="numero_cliente vacío")
    client = resolve_bcm_client(db)
    if client is None:
        return EstadoOnuBcm(numero_cliente=nro, error="bcm no configurado")
    try:
        return client.buscar_onu_por_cliente(nro)
    except Exception as exc:
        logger.exception("BCM buscar ONU falló")
        return EstadoOnuBcm(numero_cliente=nro, error=str(exc)[:160])


def candidatos_numero_bcm(
    abonado: Any | None,
    *,
    db: Session | None = None,
    ctx: dict | None = None,
    base_account_number: str = "",
) -> list[str]:
    """Números ERP a probar en BCM (client_number y cuenta del servicio)."""
    seen: list[str] = []

    def _add(raw: Any) -> None:
        s = str(raw or "").strip()
        if s and s not in seen:
            seen.append(s)

    if abonado is not None:
        _add(getattr(abonado, "client_number", ""))
    ctx = ctx or {}
    _add(ctx.get("client_number"))
    _add(base_account_number)
    _add(ctx.get("pppoe_base_account"))
    if abonado is not None:
        _add(resolver_numero_cliente_bcm(abonado, db))
        dni = str(getattr(abonado, "dni", "") or "").strip()
        if dni:
            try:
                from app.services import billtrack as bt

                servicios = bt.lookup_servicios_conectividad_por_dni(dni=dni, db=db)
                for svc in servicios or []:
                    _add(getattr(svc, "base_account_number", ""))
            except Exception:
                logger.exception("BCM: candidatos desde servicios BillTrack")
    return seen


def consultar_onu_bcm_mejor_esfuerzo(
    abonado: Any | None,
    *,
    db: Session | None = None,
    ctx: dict | None = None,
    base_account_number: str = "",
) -> EstadoOnuBcm:
    """Prueba varios números hasta encontrar ONU con RX."""
    last = EstadoOnuBcm(numero_cliente="", error="numero_cliente vacío")
    for nro in candidatos_numero_bcm(
        abonado, db=db, ctx=ctx, base_account_number=base_account_number
    ):
        onu = consultar_onu_bcm(nro, db=db)
        last = onu
        if onu.encontrado and onu.rx_dbm is not None:
            return onu
        if onu.encontrado:
            last = onu
    return last


def contexto_bcm_para_abonado(
    abonado: Any | None,
    *,
    numero_cliente: str = "",
    db: Session | None = None,
) -> dict[str, str]:
    """Claves string para enrich_contexto_desde_integraciones."""
    empty = {
        "ont_estado": "",
        "olt_huawei": "",
        "bcm_estado": "",
        "bcm_serial": "",
        "bcm_olt": "",
        "bcm_rx": "",
        "bcm_modelo": "",
        "bcm_resumen": "",
        "bcm_triage": "",
    }
    if abonado is None and not (numero_cliente or "").strip():
        return empty
    if resolve_bcm_client(db) is None:
        return empty
    nro = (numero_cliente or "").strip()
    if not nro and abonado is not None:
        nro = resolver_numero_cliente_bcm(abonado, db)
    if not nro:
        return empty
    onu = consultar_onu_bcm(nro, db=db)
    if onu.error and not onu.encontrado:
        return {**empty, "bcm_resumen": onu.resumen_prompt()}
    estado = ""
    if onu.online is True:
        estado = "en_linea"
    elif onu.online is False:
        estado = "fuera_de_linea"
    rx = f"{onu.rx_dbm:.1f}dBm" if onu.rx_dbm is not None else ""
    return {
        "ont_estado": estado or ("encontrado" if onu.encontrado else ""),
        "olt_huawei": onu.olt_nombre,
        "bcm_estado": estado,
        "bcm_serial": onu.serial,
        "bcm_olt": onu.olt_nombre,
        "bcm_rx": rx,
        "bcm_modelo": onu.modelo,
        "bcm_resumen": onu.resumen_prompt(),
        "bcm_triage": triage_bcm_para_prompt(onu),
    }


def _aplica_ftth(intencion: str, contexto_abonado: str) -> bool:
    intent = (intencion or "").strip()
    if intent == "internet_radio":
        return False
    if intent == "internet_ftth":
        return True
    blob = contexto_abonado or ""
    low = blob.lower()
    if "bcm_triage" in low or "- bcm:" in low:
        return True
    if "uisp_triage" in low and "bcm_triage" not in low:
        return False
    return "intfo" in low or "ftth" in low or "fibra" in low


def evaluar_turno_onu_bcm(
    *,
    contexto_abonado: str,
    mensaje_cliente: str,
    historial_mensajes: list[Any] | None = None,
    pasos_cubiertos: list[str] | None = None,
    turnos_diagnostico: int = 0,
    intencion: str = "",
) -> dict[str, Any] | None:
    """Turno N1 guiado por telemetría BCM. None si no aplica."""
    _ = historial_mensajes
    if not _aplica_ftth(intencion, contexto_abonado):
        return None
    parsed = parse_bcm_desde_contexto(contexto_abonado)
    resumen = str(parsed.get("resumen") or "")
    if not resumen or "no encontrado" in resumen or "error consulta" in resumen:
        return None

    from app.domain.flujos_abonado import indica_resuelto, pide_humano

    if indica_resuelto(mensaje_cliente):
        return None

    pasos = list(pasos_cubiertos or [])
    t = (mensaje_cliente or "").lower()
    persistencia = any(
        k in t
        for k in (
            "sigue sin",
            "sigue igual",
            "no anda",
            "no mejora",
            "no mejoró",
            "no mejoro",
            "sigue mal",
            "sigue baja",
            "sigue bajo",
        )
    )
    from app.domain.flujos_abonado import cliente_pregunta_potencia_onu

    pregunta_potencia = cliente_pregunta_potencia_onu(mensaje_cliente)

    online = parsed.get("online")
    rx = parsed.get("rx_dbm")
    calidad = str(parsed.get("calidad_optica") or "")
    estado = EstadoOnuBcm(
        numero_cliente="",
        encontrado=True,
        online=online if isinstance(online, bool) else None,
        rx_dbm=rx if isinstance(rx, float) else None,
        calidad_optica=calidad if calidad in ("buena", "aceptable", "mala") else "",
    )
    rama = clasificar_rama_bcm(estado)
    if rama == "" and "onu_ftth_offline" in str(parsed.get("triage") or ""):
        rama = "onu_offline"
    elif rama == "" and "onu_ftth_potencia_mala" in str(parsed.get("triage") or ""):
        rama = "potencia_mala"
    elif rama == "" and "onu_ftth_enlace_ok" in str(parsed.get("triage") or ""):
        rama = "enlace_ok"

    if pregunta_potencia:
        return {
            "accion": "ask",
            "mensaje": mensaje_informe_potencia_onu(estado),
            "paso_cubierto": "consulta_potencia_onu",
            "motivo": "bcm_consulta_potencia",
        }

    if rama == "onu_offline":
        if persistencia or pide_humano(mensaje_cliente) or int(turnos_diagnostico or 0) >= 2:
            return {
                "accion": "escalate",
                "mensaje": mensaje_visita_onu_por_optica(estado),
                "paso_cubierto": "",
                "motivo": "bcm_onu_offline_visita",
            }
        if "bcm_onu_offline" not in pasos:
            return {
                "accion": "ask",
                "mensaje": (
                    "Revisé tu ONT: no está registrada en la central. "
                    "¿El equipo tiene alguna lucecita prendida (PON o LOS)?"
                ),
                "paso_cubierto": "bcm_onu_offline",
                "motivo": "bcm_onu_offline",
            }
        return None

    if rama == "potencia_mala":
        if persistencia or pide_humano(mensaje_cliente) or "bcm_potencia_mala" in pasos:
            return {
                "accion": "escalate",
                "mensaje": mensaje_visita_onu_por_optica(estado),
                "paso_cubierto": "",
                "motivo": "bcm_potencia_mala_visita",
            }
        return {
            "accion": "ask",
            "mensaje": (
                f"{mensaje_informe_potencia_onu(estado)} "
                "¿El cablecito amarillo está firme, sin dobleces ni pisadas?"
            ),
            "paso_cubierto": "bcm_potencia_mala",
            "motivo": "bcm_potencia_mala",
        }

    return None
