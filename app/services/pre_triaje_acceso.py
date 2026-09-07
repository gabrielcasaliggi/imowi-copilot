"""Pre-triaje N1: padrón (BillTrack) → Radius → BCM/UISP, y recién el cuestionario.

Política general (no es de un cliente): en un reclamo de internet el bot
consulta sistemas y **dice** lo que ve. Si algo ya está mal, lo informa.
Si todo se ve bien, lo demuestra y recién ahí pregunta en casa (cable/Wi‑Fi).
No arrancar por zona Wi‑Fi a ciegas.
"""

from __future__ import annotations

from typing import Any

from app.radius.contract import EstadoConexionPPPoE, ServicioConectividad


def _tipo_humano(svc: ServicioConectividad | None) -> str:
    if svc is None:
        return "internet"
    code = (svc.service_type_code or "").strip().upper()
    blob = f"{svc.service_type_label} {svc.product} {svc.label}".lower()
    if code == "INTFO" or "fibra" in blob or "ftth" in blob:
        return "fibra"
    if code == "INTBA" or "inalambr" in blob or "radio" in blob or "antena" in blob:
        return "radio"
    if code == "INTINA" or "adsl" in blob:
        return "ADSL"
    label = (svc.service_type_label or svc.product or svc.label or "").strip()
    return label or "internet"


def _producto(svc: ServicioConectividad | None) -> str:
    if svc is None:
        return ""
    return (svc.product or svc.label or "").strip()


def nota_administrativa(
    abonado: Any | None,
    svc: ServicioConectividad | None,
) -> str:
    """Corte/baja real del servicio vigente. Vacío si está Habilitado."""
    from app.services.billtrack import servicio_habilitado

    if svc is not None and servicio_habilitado(svc):
        return ""
    if svc is not None and svc.service_on is False:
        st = (svc.state or "").strip()
        extra = f" ({st})" if st else ""
        return (
            "En el sistema el servicio de internet figura apagado o dado de baja"
            f"{extra}. Eso es administrativo, no un fallo del Wi‑Fi."
        )
    st = (svc.state or "").strip().lower() if svc is not None else ""
    if st in ("baja", "cancelado", "cancelada", "inactivo", "inactiva", "suspendido", "corte"):
        return (
            f"En el sistema el servicio figura «{svc.state}». "
            "Puede ser un tema administrativo (corte o suspensión), no solo el equipo de casa."
        )
    est = str(getattr(abonado, "estado", "") or "").strip().lower() if abonado else ""
    if est in ("corte", "cortado", "suspendido", "suspendida", "baja"):
        return (
            f"La cuenta figura «{est}» en el sistema. "
            "Antes de una visita conviene confirmar si el servicio está habilitado."
        )
    return ""


def linea_padron(estado: EstadoConexionPPPoE, abonado: Any | None = None) -> str:
    svc = estado.servicio
    tipo = _tipo_humano(svc)
    prod = _producto(svc)
    plan = f" ({prod})" if prod else ""
    if svc and svc.login:
        return f"En el sistema figura internet por {tipo}{plan}."
    serv_abo = str(getattr(abonado, "servicio", "") or "").strip().lower() if abonado else ""
    if serv_abo in ("internet", "ambos"):
        return "En la base de datos figura internet fijo, pero no pude leer el detalle ahora."
    return ""


def linea_radius(estado: EstadoConexionPPPoE, *, con_detalle: bool = False) -> str:
    from app.services.conexion_pppoe import clasificar_rama_pppoe, formatear_uptime_humano

    rama = clasificar_rama_pppoe(estado)
    if estado.sesion is None:
        if estado.error:
            return (
                "No pude consultar si estás conectado en la red en este momento "
                f"({estado.error[:80]})."
            )
        return "No pude consultar si estás conectado en la red en este momento."
    if rama == "sin_sesion" or estado.online is False:
        return "En la red, ahora mismo tu usuario no figura conectado."
    if estado.online is True:
        extra = ""
        if con_detalle and estado.sesion:
            bits: list[str] = []
            if estado.sesion.public_ip:
                bits.append(f"IP {estado.sesion.public_ip}")
            if estado.sesion.uptime:
                bits.append(f"hace {formatear_uptime_humano(estado.sesion.uptime)}")
            if bits:
                extra = f" ({', '.join(bits)})"
        if rama == "recien_conectado":
            return f"En la red tu conexión está activa{extra}: recién reconectó."
        return f"En la red tu conexión está activa{extra}."
    return "No pude confirmar si la sesión en la red está activa."


def mensaje_antena_no_enlazada() -> str:
    return (
        "El servicio de radio está habilitado, pero la antena no figura enlazada en la red. "
        "Eso no es una baja. ¿La fuente PoE (el inyectocito de la antena) tiene la lucecita prendida?"
    )


def _planta_mala(onu: Any | None, cpe: Any | None, *, es_ftth: bool, es_radio: bool) -> str | None:
    from app.services.conexion_bcm import clasificar_rama_bcm, mensaje_abonado_bcm
    from app.services.conexion_uisp import clasificar_rama_uisp, mensaje_abonado_uisp

    if es_radio and cpe is not None:
        err = str(getattr(cpe, "error", "") or "").lower()
        if "no configurado" in err:
            return None
        if not getattr(cpe, "encontrado", False):
            return mensaje_antena_no_enlazada()
        rama = clasificar_rama_uisp(cpe)
        if rama in ("cpe_offline", "senal_mala"):
            return mensaje_abonado_uisp(cpe, es_radio=True)
    if (es_ftth or (onu is not None and getattr(onu, "encontrado", False))) and onu is not None:
        rama = clasificar_rama_bcm(onu)
        if rama in ("onu_offline", "potencia_mala"):
            return mensaje_abonado_bcm(onu, es_ftth=True)
    return None


def _siguiente_pregunta(*, rama_pppoe: str, planta_ok: bool, admin_mal: bool) -> str:
    if admin_mal:
        return (
            "¿Querés que te oriente con el pago o la reactivación, "
            "o seguimos revisando el equipo de casa?"
        )
    if rama_pppoe == "sin_sesion" or not planta_ok:
        return (
            "Como el acceso no se ve sano, no arranquemos por el Wi‑Fi. "
            "¿Las luces del equipo (cajita blanca o fuente de la antena) están prendidas? "
            "Si podés, desenchufá 30 segundos y avisame si vuelve a conectar."
        )
    if rama_pppoe == "recien_conectado":
        return "Dale uno o dos minutos y probá navegar. ¿Ya te anda o sigue igual?"
    return (
        "Hasta acá el acceso de la cooperativa se ve bien. Sigamos en tu casa: "
        "¿no te anda en ningún dispositivo o solo por Wi‑Fi? "
        "Si podés, conectá un cable al router y fijate si navega."
    )


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
    """Texto para el abonado. None solo si no hay nada que decir (sin internet)."""
    from app.services.conexion_bcm import clasificar_rama_bcm
    from app.services.conexion_pppoe import clasificar_rama_pppoe, mensaje_abonado_pppoe
    from app.services.conexion_uisp import clasificar_rama_uisp

    padron = linea_padron(estado, abonado)
    admin = nota_administrativa(abonado, estado.servicio)
    if not padron and not estado.servicio and not admin:
        return None

    rama = clasificar_rama_pppoe(estado)
    planta_msg = _planta_mala(onu, cpe, es_ftth=es_ftth, es_radio=es_radio)
    bcm_ok = False
    uisp_ok = False
    if onu is not None and getattr(onu, "encontrado", False):
        bcm_ok = clasificar_rama_bcm(onu) == "enlace_ok"
    if cpe is not None and getattr(cpe, "encontrado", False):
        uisp_ok = clasificar_rama_uisp(cpe) == "enlace_ok"
    planta_ok = True
    if es_radio and cpe is not None:
        err = str(getattr(cpe, "error", "") or "").lower()
        if "no configurado" not in err:
            planta_ok = bool(getattr(cpe, "encontrado", False) and uisp_ok)
    elif (es_ftth or (onu is not None and getattr(onu, "encontrado", False))) and onu is not None:
        if getattr(onu, "encontrado", False):
            planta_ok = bcm_ok

    if planta_msg:
        partes = [p for p in (padron, linea_radius(estado, con_detalle=False), admin, planta_msg) if p]
        return "\n".join(partes)

    msg_ppp = mensaje_abonado_pppoe(estado, deuda_positiva=deuda_positiva)
    if msg_ppp and rama in ("wifi_lan", "recien_conectado") and planta_ok:
        if padron and "en el sistema figura" not in msg_ppp.lower():
            msg_ppp = f"{padron} {msg_ppp}"
        if admin and admin not in msg_ppp:
            idx = msg_ppp.find("¿")
            if idx >= 0:
                return f"{msg_ppp[:idx].rstrip()} {admin} {msg_ppp[idx:]}"
            return f"{msg_ppp} {admin}"
        return msg_ppp

    if msg_ppp:
        if admin and admin not in msg_ppp:
            idx = msg_ppp.find("¿")
            if idx >= 0:
                return f"{msg_ppp[:idx].rstrip()} {admin} {msg_ppp[idx:]}"
            return f"{msg_ppp} {admin}"
        return msg_ppp

    # Fallback: había servicio o padrón, pero Radius/BCM/UISP no armaron copy.
    radio_txt = linea_radius(estado, con_detalle=True)
    pregunta = _siguiente_pregunta(
        rama_pppoe=rama,
        planta_ok=planta_ok,
        admin_mal=bool(admin),
    )
    partes = [p for p in (padron, radio_txt, admin) if p]
    partes.append(pregunta)
    return " ".join(partes) if partes else None
