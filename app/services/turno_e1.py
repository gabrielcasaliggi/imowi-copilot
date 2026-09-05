"""Contador de turnos E1 y lectura forzada OLT (BCM) / WIS (UISP).

Si el abonado y el bot intercambian más de MAX_TURNOS_E1_SIN_RESOLUCION
mensajes de diagnóstico de acceso sin cerrar el caso, el controlador deja de
preguntar a ciegas: lee la planta y, si el acceso está malo, deriva a N2.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.domain.flujos_abonado import indica_resuelto

logger = logging.getLogger("operations_hub")

MAX_TURNOS_E1_SIN_RESOLUCION = 3

INTENCIONES_E1_ACCESO = frozenset(
    {
        "internet",
        "internet_ftth",
        "internet_radio",
        "internet_lento",
        "internet_intermitente",
    }
)

MOTIVO_OLT_MALA = "e1_lectura_olt_mala"
MOTIVO_WIS_MALA = "e1_lectura_wis_mala"
MOTIVO_ACCESO_OK = "e1_lectura_acceso_ok"
MOTIVO_SIN_DATO = "e1_lectura_sin_dato"

VeredictoLectura = str  # acceso_malo | acceso_ok | sin_dato


@dataclass(frozen=True)
class LecturaForzadaE1:
    accion: str  # skip | ask | escalate
    motivo: str
    mensaje: str
    veredicto: VeredictoLectura
    tecnologia: str = ""


def es_intencion_e1_acceso(intencion: str) -> bool:
    return (intencion or "").strip() in INTENCIONES_E1_ACCESO


def turnos_e1(ctx: dict | None) -> int:
    c = ctx or {}
    return max(0, int(c.get("diag_turnos") or c.get("e1_turnos_sin_resolucion") or 0))


def acceso_planta_ya_ok(ctx: dict | None) -> bool:
    """Radius/BCM/UISP ya vieron el enlace de acceso OK: el resto es LAN/Wi‑Fi."""
    c = ctx or {}
    if str(c.get("pppoe_rama") or "") in ("wifi_lan", "recien_conectado"):
        return True
    if "onu_ftth_enlace_ok" in str(c.get("bcm_triage") or ""):
        return True
    if "cpe_radio_enlace_ok" in str(c.get("uisp_triage") or ""):
        return True
    return False


def debe_forzar_lectura_e1(
    ctx: dict | None,
    intencion: str,
    texto_cliente: str = "",
) -> bool:
    """True al superar 3 turnos E1 sin resolución técnica de acceso."""
    if not es_intencion_e1_acceso(intencion):
        return False
    if indica_resuelto(texto_cliente):
        return False
    c = ctx or {}
    if c.get("lectura_forzada_e1"):
        return False
    if c.get("wifi_rama_activada"):
        return False
    if acceso_planta_ya_ok(c):
        return False
    return turnos_e1(c) >= MAX_TURNOS_E1_SIN_RESOLUCION


def tecnologia_e1(ctx: dict | None, intencion: str) -> str:
    c = ctx or {}
    tech = str(c.get("tecnologia_acceso") or "").strip()
    intent = (intencion or "").strip()
    if tech in ("internet_ftth", "internet_radio", "internet_adsl"):
        return tech
    if intent in ("internet_ftth", "internet_radio", "internet_adsl"):
        return intent
    blob = " ".join(
        str(c.get(k) or "")
        for k in ("pppoe_producto", "pppoe_resumen", "bcm_triage", "uisp_triage")
    ).lower()
    if "intba" in blob or "inalambr" in blob or "cpe_radio" in blob:
        return "internet_radio"
    if "intfo" in blob or "fibra" in blob or "ftth" in blob or "onu_ftth" in blob:
        return "internet_ftth"
    if "intina" in blob or "adsl" in blob:
        return "internet_adsl"
    return intent or "internet"


def veredicto_desde_ctx(ctx: dict | None) -> VeredictoLectura:
    c = ctx or {}
    rama_bcm = str(c.get("bcm_rama") or "")
    triage_bcm = str(c.get("bcm_triage") or "")
    if rama_bcm in ("onu_offline", "potencia_mala") or any(
        k in triage_bcm for k in ("onu_ftth_offline", "onu_ftth_potencia_mala")
    ):
        return "acceso_malo"
    rama_uisp = str(c.get("uisp_rama") or "")
    triage_uisp = str(c.get("uisp_triage") or "")
    if rama_uisp in ("cpe_offline", "senal_mala") or any(
        k in triage_uisp for k in ("cpe_radio_offline", "senal_mala")
    ):
        return "acceso_malo"
    if rama_bcm == "enlace_ok" or "onu_ftth_enlace_ok" in triage_bcm:
        return "acceso_ok"
    if rama_uisp == "enlace_ok" or "cpe_radio_enlace_ok" in triage_uisp:
        return "acceso_ok"
    return "sin_dato"


def _consultar_olt(db: Session, abonado: Any, ctx: dict) -> VeredictoLectura:
    from app.bcm.contract import EstadoOnuBcm
    from app.services.conexion_bcm import (
        aplicar_bcm_a_ctx,
        clasificar_rama_bcm,
        consultar_onu_bcm_mejor_esfuerzo,
        resolve_bcm_client,
    )

    onu: EstadoOnuBcm | None = None
    if resolve_bcm_client(db) is not None and abonado is not None:
        try:
            onu = consultar_onu_bcm_mejor_esfuerzo(abonado, db=db, ctx=ctx)
        except Exception:
            logger.exception("E1: consulta BCM/OLT falló")
            onu = None
    if onu is not None and onu.encontrado and not onu.error:
        aplicar_bcm_a_ctx(ctx, onu)
        rama = clasificar_rama_bcm(onu)
        if rama in ("onu_offline", "potencia_mala"):
            return "acceso_malo"
        if rama == "enlace_ok":
            return "acceso_ok"
    return veredicto_desde_ctx(ctx)


def _consultar_wis(db: Session, abonado: Any, ctx: dict) -> VeredictoLectura:
    from app.services.conexion_uisp import (
        aplicar_uisp_a_ctx,
        clasificar_rama_uisp,
        consultar_cpe_uisp,
        resolve_uisp_client,
    )

    login = str(ctx.get("login_seleccionado") or ctx.get("pppoe_login") or "").strip()
    if not login and abonado is not None:
        try:
            from app.services.conexion_uisp import _login_desde_abonado

            login = _login_desde_abonado(abonado, db) or ""
        except Exception:
            logger.exception("E1: no se resolvió login UISP")
            login = ""
    if resolve_uisp_client(db) is not None and login:
        try:
            cpe = consultar_cpe_uisp(login, db=db)
        except Exception:
            logger.exception("E1: consulta UISP/WIS falló")
            cpe = None
        if cpe is not None and cpe.encontrado and not cpe.error:
            aplicar_uisp_a_ctx(ctx, cpe)
            rama = clasificar_rama_uisp(cpe)
            if rama in ("cpe_offline", "senal_mala"):
                return "acceso_malo"
            if rama == "enlace_ok":
                return "acceso_ok"
    return veredicto_desde_ctx(ctx)


def _mensaje_escalar(ctx: dict, tecnologia: str) -> tuple[str, str]:
    from app.bcm.contract import EstadoOnuBcm
    from app.services.conexion_bcm import mensaje_visita_onu_por_optica
    from app.services.conexion_uisp import mensaje_visita_antena_por_senal
    from app.uisp.contract import EstadoCpeUisp

    if tecnologia == "internet_radio":
        try:
            dbm = float(str(ctx.get("uisp_signal_dbm") or "") or "nan")
        except ValueError:
            dbm = None
        cpe = EstadoCpeUisp(
            login=str(ctx.get("pppoe_login") or ctx.get("login_seleccionado") or ""),
            encontrado=True,
            online=str(ctx.get("uisp_rama") or "") != "cpe_offline",
            signal_dbm=dbm,
            calidad_senal=str(ctx.get("uisp_calidad_senal") or ""),  # type: ignore[arg-type]
            sitio=str(ctx.get("uisp_sitio") or ""),
        )
        if str(ctx.get("uisp_rama") or "") == "cpe_offline":
            cpe.online = False
        return mensaje_visita_antena_por_senal(cpe), MOTIVO_WIS_MALA

    try:
        rx = float(str(ctx.get("bcm_rx_dbm") or "") or "nan")
    except ValueError:
        rx = None
    onu = EstadoOnuBcm(
        numero_cliente="",
        encontrado=True,
        online=str(ctx.get("bcm_rama") or "") != "onu_offline",
        rx_dbm=rx,
        calidad_optica=str(ctx.get("bcm_calidad_optica") or ""),  # type: ignore[arg-type]
        olt_nombre=str(ctx.get("bcm_olt") or ""),
    )
    if str(ctx.get("bcm_rama") or "") == "onu_offline":
        onu.online = False
    return mensaje_visita_onu_por_optica(onu), MOTIVO_OLT_MALA


def _mensaje_acceso_ok(tecnologia: str) -> str:
    if tecnologia == "internet_radio":
        return (
            "Revisé la antena en la red: el enlace con la torre está bien. "
            "Si no navega, el tema es en tu casa. "
            "¿No te anda en ningún dispositivo o solo por Wi-Fi?"
        )
    return (
        "Revisé tu ONT en la central: el acceso de fibra está bien. "
        "Si no navega, el tema es el Wi-Fi o el equipo. "
        "¿No te anda en ningún dispositivo o solo por Wi-Fi?"
    )


def ejecutar_lectura_forzada_e1(
    db: Session,
    abonado: Any | None,
    ctx: dict,
    intencion: str,
) -> LecturaForzadaE1:
    """Consulta OLT/WIS y decide ask (acceso OK) o escalate (planta mala)."""
    tech = tecnologia_e1(ctx, intencion)
    veredicto: VeredictoLectura = "sin_dato"

    if tech == "internet_adsl":
        return LecturaForzadaE1(
            accion="skip",
            motivo=MOTIVO_SIN_DATO,
            mensaje="",
            veredicto="sin_dato",
            tecnologia=tech,
        )

    if tech == "internet_radio":
        veredicto = _consultar_wis(db, abonado, ctx)
    else:
        veredicto = _consultar_olt(db, abonado, ctx)
        if veredicto == "sin_dato" and tech in ("internet", "internet_lento", "internet_intermitente"):
            alt = _consultar_wis(db, abonado, ctx)
            if alt != "sin_dato":
                tech = "internet_radio"
                veredicto = alt

    cub = [str(x) for x in (ctx.get("pasos_cubiertos") or []) if str(x).strip()]
    if "lectura_forzada_e1" not in cub:
        cub.append("lectura_forzada_e1")
    ctx["pasos_cubiertos"] = cub

    if veredicto == "acceso_malo":
        msg, motivo = _mensaje_escalar(ctx, tech)
        return LecturaForzadaE1(
            accion="escalate",
            motivo=motivo,
            mensaje=msg,
            veredicto=veredicto,
            tecnologia=tech,
        )
    if veredicto == "acceso_ok":
        ctx["wifi_rama_activada"] = True
        ctx["enlace_optico_ok"] = True
        if tech != "internet_radio":
            ctx["intencion"] = "wifi"
        return LecturaForzadaE1(
            accion="ask",
            motivo=MOTIVO_ACCESO_OK,
            mensaje=_mensaje_acceso_ok(tech),
            veredicto=veredicto,
            tecnologia=tech,
        )
    return LecturaForzadaE1(
        accion="skip",
        motivo=MOTIVO_SIN_DATO,
        mensaje="",
        veredicto="sin_dato",
        tecnologia=tech,
    )
