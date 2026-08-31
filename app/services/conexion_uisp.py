"""Orquestación UISP NMS → estado del CPE radio para el bot.

El CPE se busca por `identification.name` = username Radius (login BillTrack).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.uisp.client import UispNmsClient, clasificar_senal
from app.uisp.contract import EstadoCpeUisp, RamaUisp

logger = logging.getLogger("operations_hub")

# Por debajo de -75 dBm la señal radio está fuera de parámetro → visita de campo.
SENAL_RADIO_VISITA_DBM = -75
SENAL_RADIO_IDEAL_DBM = -65

_RE_SENAL_DBM = re.compile(r"senal=(-?\d+(?:\.\d+)?)\s*dBm", re.IGNORECASE)


def resolve_uisp_client(db: Session | None = None) -> UispNmsClient | None:
    from app.services.platform_settings import resolve_uisp

    cfg = resolve_uisp(db)
    if not cfg.get("enabled"):
        return None
    client = UispNmsClient(
        base_url=str(cfg.get("base_url") or ""),
        token=str(cfg.get("token") or ""),
        timeout=float(cfg.get("timeout") or 12.0),
        verify_ssl=bool(cfg.get("verify_ssl", True)),
    )
    if not client.configured():
        return None
    return client


def clasificar_rama_uisp(estado: EstadoCpeUisp) -> RamaUisp:
    if not estado.encontrado:
        return ""
    if estado.online is False:
        return "cpe_offline"
    if estado.online is True and requiere_visita_campo_por_senal(estado):
        return "senal_mala"
    if estado.online is True:
        return "enlace_ok"
    return ""


def requiere_visita_campo_por_senal(estado: EstadoCpeUisp) -> bool:
    """True si la telemetría UISP indica señal fuera de parámetro (< -75 dBm)."""
    if not estado.encontrado or estado.online is not True:
        return False
    if estado.calidad_senal == "mala":
        return True
    if estado.signal_dbm is not None and estado.signal_dbm < SENAL_RADIO_VISITA_DBM:
        return True
    return False


def requiere_visita_campo_antena(estado: EstadoCpeUisp) -> bool:
    """Antena offline persistente o señal fuera de parámetro → visita técnica."""
    if not estado.encontrado:
        return False
    if estado.online is False:
        return True
    return requiere_visita_campo_por_senal(estado)


def _texto_calidad_senal(calidad: str, dbm: float | None) -> str:
    if calidad == "buena":
        return "excelente"
    if calidad == "aceptable":
        return "aceptable"
    if calidad == "mala":
        return "baja"
    if dbm is not None and dbm >= SENAL_RADIO_IDEAL_DBM:
        return "buena"
    if dbm is not None and dbm >= SENAL_RADIO_VISITA_DBM:
        return "aceptable"
    if dbm is not None:
        return "baja"
    return "sin dato"


def mensaje_informe_senal_antena(estado: EstadoCpeUisp) -> str:
    """Responde cuánta señal tiene la antena y cuál es el rango ideal."""
    if not estado.encontrado or estado.signal_dbm is None:
        return (
            "No pude leer la señal de tu antena en este momento. "
            "¿El servicio no te anda en ningún dispositivo o solo por Wi‑Fi?"
        )
    dbm = estado.signal_dbm
    calidad = estado.calidad_senal or clasificar_senal(dbm)
    txt = _texto_calidad_senal(calidad, dbm)
    return (
        f"Tu antena está recibiendo {dbm:.0f} dBm, señal {txt}. "
        f"Lo ideal es estar por encima de {SENAL_RADIO_IDEAL_DBM} dBm "
        f"(excelente) o al menos por encima de {SENAL_RADIO_VISITA_DBM} dBm."
    )


def mensaje_visita_antena_por_senal(estado: EstadoCpeUisp) -> str:
    """Deriva a agente para coordinar visita y revisar antena/alineación."""
    sitio = f" hacia {estado.sitio}" if estado.sitio else ""
    if estado.online is False:
        return (
            "Revisé tu antena en la red y no está en línea con la torre"
            f"{sitio}. Con eso ya no alcanza seguir a distancia: te derivo con un agente "
            "para coordinar una visita y revisar la antena, el PoE y el cableado."
        )
    dbm = estado.signal_dbm
    calidad = estado.calidad_senal or (clasificar_senal(dbm) if dbm is not None else "")
    detalle = ""
    if dbm is not None:
        detalle = f" ({dbm:.0f} dBm, señal {_texto_calidad_senal(calidad, dbm)})"
    return (
        f"Revisé tu antena: está en línea pero la señal está fuera de parámetro{detalle}. "
        "Eso suele requerir revisar alineación, soporte o línea de vista en el domicilio. "
        "Te derivo con un agente para coordinar una visita técnica."
    )


def aplicar_uisp_a_ctx(ctx: dict, cpe: EstadoCpeUisp) -> None:
    """Persiste telemetría UISP en el contexto de la conversación."""
    ctx["uisp_resumen"] = cpe.resumen_prompt()
    ctx["uisp_triage"] = triage_uisp_para_prompt(cpe)
    ctx["uisp_rama"] = clasificar_rama_uisp(cpe)
    if cpe.signal_dbm is not None:
        ctx["uisp_signal_dbm"] = f"{cpe.signal_dbm:g}"
    if cpe.calidad_senal:
        ctx["uisp_calidad_senal"] = cpe.calidad_senal
    if cpe.online is True:
        ctx["uisp_online"] = "1"
    elif cpe.online is False:
        ctx["uisp_online"] = "0"
    if cpe.sitio:
        ctx["uisp_sitio"] = cpe.sitio


def parse_signal_dbm_desde_resumen(resumen: str) -> float | None:
    m = _RE_SENAL_DBM.search(resumen or "")
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def parse_uisp_desde_contexto(contexto_abonado: str) -> dict[str, Any]:
    """Extrae triage/señal del bloque CONTEXTO_ABONADO."""
    ctx = contexto_abonado or ""
    triage = ""
    for line in ctx.splitlines():
        low = line.strip().lower()
        if low.startswith("- uisp_triage:"):
            triage = line.split(":", 1)[1].strip()
            break
    resumen = ""
    for line in ctx.splitlines():
        low = line.strip().lower()
        if low.startswith("- uisp:"):
            resumen = line.split(":", 1)[1].strip()
            break
    signal = parse_signal_dbm_desde_resumen(resumen)
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
        "signal_dbm": signal,
        "calidad_senal": calidad,
        "online": online,
    }


def estado_cpe_desde_contexto(contexto_abonado: str, *, login: str = "") -> EstadoCpeUisp:
    parsed = parse_uisp_desde_contexto(contexto_abonado)
    resumen = str(parsed.get("resumen") or "")
    encontrado = bool(resumen) and "no encontrado" not in resumen.lower()
    signal = parsed.get("signal_dbm")
    calidad = str(parsed.get("calidad_senal") or "")
    if not calidad and signal is not None:
        calidad = clasificar_senal(signal)
    return EstadoCpeUisp(
        login=login,
        encontrado=encontrado,
        online=parsed.get("online"),
        signal_dbm=signal,
        calidad_senal=calidad,  # type: ignore[arg-type]
    )


def evaluar_turno_visita_antena_uisp(
    *,
    contexto_abonado: str,
    mensaje_cliente: str,
    historial_mensajes: list[Any] | None,
    pasos_cubiertos: list[str],
    turnos_diagnostico: int,
    intencion: str,
) -> dict[str, str] | None:
    """Reglas determinísticas: señal/antena UISP → visita de campo vs seguir N1."""
    from app.domain.flujos_abonado import (
        cliente_pregunta_senal_antena,
        indica_resuelto,
        pide_humano,
    )

    if indica_resuelto(mensaje_cliente):
        return None

    parsed = parse_uisp_desde_contexto(contexto_abonado)
    triage = str(parsed.get("triage") or "")
    if not triage and not parsed.get("resumen"):
        return None

    es_radio = (intencion or "").strip() in (
        "internet_radio",
        "internet",
        "internet_lento",
        "internet_intermitente",
    ) or any(k in triage for k in ("cpe_radio", "senal_mala", "offline"))
    if not es_radio:
        return None

    # Enlace OK: no escalar por antena (sigue WiFi/router).
    if "cpe_radio_enlace_ok" in triage and not requiere_visita_campo_por_senal(
        estado_cpe_desde_contexto(contexto_abonado)
    ):
        if not cliente_pregunta_senal_antena(mensaje_cliente):
            return None

    estado = estado_cpe_desde_contexto(contexto_abonado)
    turnos = max(0, int(turnos_diagnostico or 0))

    if cliente_pregunta_senal_antena(mensaje_cliente) and estado.signal_dbm is not None:
        msg = mensaje_informe_senal_antena(estado)
        if requiere_visita_campo_por_senal(estado):
            return {
                "accion": "escalate",
                "mensaje": f"{msg} {mensaje_visita_antena_por_senal(estado)}",
                "paso_cubierto": "consulta_senal_antena",
                "motivo": "uisp_consulta_senal_mala",
            }
        return {
            "accion": "ask",
            "mensaje": msg,
            "paso_cubierto": "consulta_senal_antena",
            "motivo": "uisp_consulta_senal",
        }

    offline = "cpe_radio_offline" in triage or estado.online is False
    if offline:
        t = (mensaje_cliente or "").lower()
        poe_ok = any(
            k in t
            for k in (
                "lucecita",
                "luz del inyector",
                "luz prend",
                "po e",
                "poe",
                "inyect",
            )
        ) and any(k in t for k in ("si", "sí", "prend", "encend", "tiene luz", "esta prend"))
        if poe_ok or "poe_antena" in pasos_cubiertos or turnos >= 2 or pide_humano(
            mensaje_cliente
        ):
            return {
                "accion": "escalate",
                "mensaje": mensaje_visita_antena_por_senal(estado),
                "paso_cubierto": "turno_campo_radio",
                "motivo": "uisp_cpe_offline_visita",
            }
        return None

    if not requiere_visita_campo_por_senal(estado):
        return None

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
    if (
        turnos >= 1
        or persistencia
        or pide_humano(mensaje_cliente)
        or "linea_vista" in pasos_cubiertos
        or "uisp_senal_mala" in pasos_cubiertos
    ):
        return {
            "accion": "escalate",
            "mensaje": mensaje_visita_antena_por_senal(estado),
            "paso_cubierto": "turno_campo_radio",
            "motivo": "uisp_senal_mala_visita",
        }

    if "uisp_senal_mala" not in pasos_cubiertos:
        return {
            "accion": "ask",
            "mensaje": (
                f"{mensaje_informe_senal_antena(estado)} "
                "¿Crecieron árboles, chapas o algo nuevo entre la antena y la torre?"
            ),
            "paso_cubierto": "uisp_senal_mala",
            "motivo": "uisp_senal_mala_linea_vista",
        }
    return None


def consultar_cpe_uisp(
    login: str,
    *,
    db: Session | None = None,
) -> EstadoCpeUisp:
    user = (login or "").strip()
    if not user:
        return EstadoCpeUisp(login="", error="login vacío")
    client = resolve_uisp_client(db)
    if client is None:
        return EstadoCpeUisp(login=user, error="uisp no configurado")
    try:
        return client.buscar_cpe_por_login(user)
    except Exception as exc:
        logger.exception("UISP buscar CPE falló")
        return EstadoCpeUisp(login=user, error=str(exc)[:160])


def _login_desde_abonado(abonado: Any, db: Session | None) -> str:
    """Username Radius = nombre del CPE. Sale del servicio de conectividad BillTrack."""
    dni = str(getattr(abonado, "dni", "") or "").strip()
    client_number = str(getattr(abonado, "client_number", "") or "").strip()
    if not dni and not client_number:
        return ""
    try:
        from app.services import billtrack as bt

        if client_number:
            servicios = bt.lookup_servicios_conectividad(client_number=client_number, db=db)
        else:
            servicios = bt.lookup_servicios_conectividad_por_dni(dni=dni, db=db)
        servicio = bt.elegir_servicio_principal(servicios)
        return (servicio.login if servicio else "") or ""
    except Exception:
        logger.exception("UISP: no se pudo resolver login BillTrack")
        return ""


def es_servicio_radio(servicio: Any | None) -> bool:
    if servicio is None:
        return False
    from app.domain.flujos_abonado import playbook_internet_desde_tipo_servicio

    pb = playbook_internet_desde_tipo_servicio(
        str(getattr(servicio, "service_type_code", "") or ""),
        str(getattr(servicio, "service_type_label", "") or ""),
    )
    return pb == "internet_radio"


def mensaje_abonado_uisp(
    estado: EstadoCpeUisp,
    *,
    es_radio: bool = True,
) -> str | None:
    """Mensaje N1 según CPE. None si no hay dato útil o no es radio."""
    if not es_radio:
        return None
    if not estado.encontrado or estado.error:
        return None
    rama = clasificar_rama_uisp(estado)

    if rama == "cpe_offline":
        return (
            "Revisé tu antena en la red: en este momento no está en línea con la torre. "
            "¿La fuente PoE (el inyectocito de la antena) tiene la lucecita prendida?"
        )
    if rama == "senal_mala":
        return (
            "Revisé tu antena: está en línea con la torre, pero la señal está baja "
            "(fuera de lo ideal). ¿Crecieron árboles, chapas o algo nuevo entre la antena y la torre?"
        )
    if rama == "enlace_ok":
        return (
            "Revisé tu antena: está en línea y el enlace con la torre se ve bien. "
            "¿No te anda en ningún dispositivo o solo por Wi‑Fi? "
            "¿Probaste con cable al router?"
        )
    return None


def triage_uisp_para_prompt(estado: EstadoCpeUisp) -> str:
    rama = clasificar_rama_uisp(estado)
    if rama == "cpe_offline":
        return "triage=cpe_radio_offline; chequear PoE/energía; no pedir Wi‑Fi primero"
    if rama == "senal_mala":
        return "triage=cpe_radio_senal_mala; linea_de_vista; no pedir reinicio de router como primer paso"
    if rama == "enlace_ok":
        return (
            "triage=cpe_radio_enlace_ok; indagar Wi‑Fi vs cable; "
            "NO pedir reinicio de antena como primer paso"
        )
    if estado.error:
        return ""
    if not estado.encontrado:
        return "triage=cpe_no_encontrado_uisp"
    return ""


def contexto_uisp_para_abonado(
    abonado: Any | None,
    *,
    login: str = "",
    db: Session | None = None,
) -> dict[str, str]:
    """Claves string para enrich_contexto_desde_integraciones."""
    empty = {
        "uisp_estado": "",
        "uisp_login": "",
        "uisp_sitio": "",
        "uisp_senal": "",
        "uisp_modelo": "",
        "uisp_resumen": "",
        "uisp_triage": "",
    }
    if abonado is None and not (login or "").strip():
        return empty
    if resolve_uisp_client(db) is None:
        return empty

    user = (login or "").strip()
    if not user and abonado is not None:
        user = _login_desde_abonado(abonado, db)
    if not user:
        return empty

    try:
        estado = consultar_cpe_uisp(user, db=db)
    except Exception as exc:
        logger.exception("contexto_uisp falló")
        empty["uisp_resumen"] = f"error: {str(exc)[:80]}"
        return empty

    out = dict(empty)
    out["uisp_login"] = estado.login
    out["uisp_resumen"] = estado.resumen_prompt()
    out["uisp_triage"] = triage_uisp_para_prompt(estado)
    if not estado.encontrado:
        out["uisp_estado"] = "no_encontrado"
        return out
    if estado.online is True:
        out["uisp_estado"] = "en_linea"
    elif estado.online is False:
        out["uisp_estado"] = "fuera_de_linea"
    else:
        out["uisp_estado"] = "sin_dato"
    out["uisp_sitio"] = estado.sitio
    out["uisp_modelo"] = estado.modelo
    if estado.signal_dbm is not None:
        out["uisp_senal"] = f"{estado.signal_dbm:.0f}dBm/{estado.calidad_senal or 'sin_calidad'}"
    return out
