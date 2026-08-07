"""Orquestación BillTrack (api_service) + API Radius/NAS → estado PPPoE para el bot."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.radius.client import RadiusNasClient
from app.radius.contract import EstadoConexionPPPoE, ServicioConectividad

logger = logging.getLogger("operations_hub")


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
        # Igual intentamos enriquecer tipo de servicio si hay dni/client_number
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
    }
    if abonado is None:
        return empty

    dni = str(getattr(abonado, "dni", "") or "").strip()
    client_number = str(getattr(abonado, "client_number", "") or "").strip()
    if not dni and not client_number:
        return empty

    # Evitar llamadas si radius está off
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
    return out
