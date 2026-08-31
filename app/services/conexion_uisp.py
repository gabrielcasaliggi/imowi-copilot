"""Orquestación UISP NMS → estado del CPE radio para el bot.

El CPE se busca por `identification.name` = username Radius (login BillTrack).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.uisp.client import UispNmsClient
from app.uisp.contract import EstadoCpeUisp, RamaUisp

logger = logging.getLogger("operations_hub")


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
    if estado.online is True and estado.calidad_senal == "mala":
        return "senal_mala"
    if estado.online is True:
        return "enlace_ok"
    return ""


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
            "Revisé tu antena: está en línea con la torre, pero la señal está baja. "
            "¿Sigue con vista libre, sin árboles, chapas o cosas nuevas adelante?"
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
