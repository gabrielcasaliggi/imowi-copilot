"""Pre-triaje N1: fachada del protocolo de mesa (cuenta → sondas → diálogo)."""

from __future__ import annotations

from typing import Any

from app.radius.contract import EstadoConexionPPPoE, ServicioConectividad
from app.services.protocolo_mesa import (
    clasificar_cuenta,
    decidir_mensaje_mesa,
    mensaje_antena_no_enlazada,
    mensaje_comercial,
)


def nota_administrativa(
    abonado: Any | None,
    svc: ServicioConectividad | None,
) -> str:
    """Corte/baja real del servicio vigente. Vacío si está activo."""
    cuenta = clasificar_cuenta(abonado, svc)
    if cuenta in ("baja", "corte"):
        return mensaje_comercial(cuenta)
    return ""


def linea_padron(estado: EstadoConexionPPPoE, abonado: Any | None = None) -> str:
    """Detalle interno de plan/tecnología. No va al abonado como apertura."""
    svc = estado.servicio
    if svc is None:
        return ""
    code = (svc.service_type_code or "").strip().upper()
    blob = f"{svc.service_type_label} {svc.product} {svc.label}".lower()
    if code == "INTFO" or "fibra" in blob or "ftth" in blob:
        tipo = "fibra"
    elif code == "INTBA" or "inalambr" in blob or "radio" in blob or "antena" in blob:
        tipo = "radio"
    elif code == "INTINA" or "adsl" in blob:
        tipo = "ADSL"
    else:
        tipo = (svc.service_type_label or svc.product or "internet").strip()
    prod = (svc.product or svc.label or "").strip()
    plan = f" ({prod})" if prod else ""
    if svc.login:
        return f"internet por {tipo}{plan}"
    serv_abo = str(getattr(abonado, "servicio", "") or "").strip().lower() if abonado else ""
    if serv_abo in ("internet", "ambos"):
        return "internet fijo (detalle no leído)"
    return ""


def mensaje_pre_triaje_acceso(
    estado: EstadoConexionPPPoE,
    *,
    abonado: Any | None = None,
    onu: Any | None = None,
    cpe: Any | None = None,
    es_ftth: bool = False,
    es_radio: bool = False,
    deuda_positiva: bool = False,
) -> str | None:
    """Texto para el abonado según protocolo de mesa."""
    return decidir_mensaje_mesa(
        estado,
        abonado=abonado,
        onu=onu,
        cpe=cpe,
        es_ftth=es_ftth,
        es_radio=es_radio,
        deuda_positiva=deuda_positiva,
    )


__all__ = [
    "linea_padron",
    "mensaje_antena_no_enlazada",
    "mensaje_pre_triaje_acceso",
    "nota_administrativa",
]
