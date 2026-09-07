"""Protocolo de mesa N1 — el oficio del técnico, no un parte de NOC.

Orden fijo (no se salta):

1. Cuenta y plan vigentes (BillTrack, en silencio).
2. Baja o corte por pago → se informa y se indica cómo proceder. No se abren
   BCM / UISP / Radius de planta.
3. Si está activo → consultar Radius, BCM (fibra) o UISP (radio).
   - Acceso sano → **demostrar** al abonado (sesión activa, potencia o señal)
     y recién preguntar en casa.
   - Acceso mal o sin dato → pregunta de mesa (luces/PoE); no Wi‑Fi primero.
4. Wi‑Fi solo cuando el acceso ya se vio sano.

Botmaker enseña cómo hablan y qué es resoluble en N1. No se nombran las
herramientas (Radius/BCM/UISP); sí se muestran los números útiles.
"""

from __future__ import annotations

from typing import Any, Literal

from app.radius.contract import EstadoConexionPPPoE, ServicioConectividad

RamaMesa = Literal[
    "comercial",
    "planta",
    "sin_sesion",
    "recien_conectado",
    "acceso_ok",
    "",
]


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


def clasificar_cuenta(
    abonado: Any | None,
    svc: ServicioConectividad | None,
) -> Literal["activa", "baja", "corte", ""]:
    """Vigencia de la cuenta/servicio. No usa substring (Habilitado ≠ Baja)."""
    from app.services.billtrack import servicio_habilitado

    if svc is not None and servicio_habilitado(svc):
        return "activa"
    if svc is not None:
        st = (svc.state or "").strip().lower()
        if st in ("baja", "cancelado", "cancelada", "inactivo", "inactiva"):
            return "baja"
        if st in ("suspendido", "suspendida", "corte", "cortado"):
            return "corte"
        if svc.service_on is False:
            return "baja"
    est = str(getattr(abonado, "estado", "") or "").strip().lower() if abonado else ""
    if est in ("baja",):
        return "baja"
    if est in ("corte", "cortado", "suspendido", "suspendida"):
        return "corte"
    if svc is not None:
        return "activa"
    return ""


def rama_comercial(
    abonado: Any | None,
    svc: ServicioConectividad | None,
) -> bool:
    """True: no abrir sondas de planta. Baja o corte administrativo."""
    return clasificar_cuenta(abonado, svc) in ("baja", "corte")


def mensaje_comercial(cuenta: Literal["baja", "corte", "activa", ""]) -> str:
    from app.services.eco_voice import PLANTILLA_PAGO_QR

    if cuenta == "corte":
        intro = (
            "Tu servicio figura restringido por un tema de cuenta (corte o suspensión), "
            "no por el Wi‑Fi de casa. Con el pago o el aviso en la oficina virtual "
            "se rehabilita."
        )
    else:
        intro = (
            "Tu servicio de internet figura dado de baja. No es un fallo del equipo "
            "de casa: hay que regularizar la cuenta para volver a habilitarlo."
        )
    return f"{intro} {PLANTILLA_PAGO_QR}"


def _pregunta_luces(*, es_radio: bool, es_ftth: bool) -> str:
    if es_radio:
        return (
            "¿La fuente PoE (el inyectocito de la antena) tiene la lucecita prendida? "
            "Si podés, desenchufala 30 segundos y avisame si vuelve a conectar."
        )
    if es_ftth:
        return (
            "¿La ONT (cajita de la fibra) tiene luces? Decime si ves la PON en verde "
            "o alguna LOS en rojo/alarma. Si podés, desenchufala 30 segundos y avisame "
            "si vuelve a conectar."
        )
    return (
        "¿Las luces del módem o router están prendidas? "
        "Si podés, desenchufá 30 segundos y avisame si vuelve a conectar."
    )


def _pregunta_wifi() -> str:
    return (
        "Sigamos en tu casa: ¿no te anda en ningún dispositivo o solo por Wi‑Fi? "
        "Si podés, conectá un cable al router y fijate si navega."
    )


def _mensaje_sin_sesion_planta_ok(
    onu: Any | None,
    cpe: Any | None,
    *,
    es_ftth: bool,
    es_radio: bool,
) -> str:
    """Planta OK pero sin sesión PPP: demostrar potencia/señal; no preguntar si está prendida."""
    from app.services.barra_senal import (
        anexar_antes_de_preguntas,
        bloque_potencia_onu,
        bloque_senal_antena,
        veredicto_optica,
        veredicto_radio,
    )

    partes: list[str] = []
    barra = ""
    if es_radio and cpe is not None and getattr(cpe, "encontrado", False):
        ver = veredicto_radio(getattr(cpe, "signal_dbm", None)) or "se ve bien"
        dbm = getattr(cpe, "signal_dbm", None)
        extra = f" ({int(round(dbm))} dBm)" if isinstance(dbm, (int, float)) else ""
        partes.append(
            f"Revisé tu antena: está en línea y el enlace con la torre {ver}{extra}."
        )
        barra = bloque_senal_antena(getattr(cpe, "signal_dbm", None))
    elif es_ftth and onu is not None and getattr(onu, "encontrado", False):
        from app.services.barra_senal import formatear_dbm_optica

        rx = getattr(onu, "rx_dbm", None)
        if isinstance(rx, (int, float)):
            ver = veredicto_optica(rx) or "se ve bien"
            partes.append(
                f"Revisé tu ONT: está en línea y la potencia óptica {ver} "
                f"({formatear_dbm_optica(rx)} dBm)."
            )
            barra = bloque_potencia_onu(rx)
        else:
            partes.append(
                "Revisé tu ONT: figura en línea en la central, pero no pude leer "
                "la potencia óptica en este momento."
            )
    partes.append(
        "Igual, ahora mismo tu usuario no figura conectado en la red. "
        "Si podés, desenchufá el router/ONT 30 segundos y avisame si vuelve a conectar."
    )
    msg = " ".join(partes)
    if barra:
        return anexar_antes_de_preguntas(msg, barra)
    return msg


def _enlace_planta_demostrable(
    onu: Any | None,
    cpe: Any | None,
    *,
    es_ftth: bool,
    es_radio: bool,
) -> bool:
    """True solo si BCM/UISP vieron el equipo en línea con enlace OK."""
    from app.services.conexion_bcm import clasificar_rama_bcm
    from app.services.conexion_uisp import clasificar_rama_uisp

    if es_radio and cpe is not None and getattr(cpe, "encontrado", False):
        return clasificar_rama_uisp(cpe) == "enlace_ok"
    if es_ftth and onu is not None and getattr(onu, "encontrado", False):
        return clasificar_rama_bcm(onu) == "enlace_ok"
    return False


def mensaje_antena_no_enlazada() -> str:
    return (
        "El servicio de radio está activo, pero la antena no figura enlazada en la red. "
        "¿La fuente PoE (el inyectocito de la antena) tiene la lucecita prendida?"
    )


def _detalle_sesion(estado: EstadoConexionPPPoE) -> str:
    from app.services.conexion_pppoe import formatear_uptime_humano

    ses = estado.sesion
    if ses is None:
        return ""
    bits: list[str] = []
    if ses.public_ip:
        bits.append(f"IP {ses.public_ip}")
    if ses.uptime:
        bits.append(f"hace {formatear_uptime_humano(ses.uptime)}")
    if not bits:
        return ""
    return f" ({', '.join(bits)})"


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


def _planta_ok(onu: Any | None, cpe: Any | None, *, es_ftth: bool, es_radio: bool) -> bool:
    from app.services.conexion_bcm import clasificar_rama_bcm
    from app.services.conexion_uisp import clasificar_rama_uisp

    if es_radio and cpe is not None:
        err = str(getattr(cpe, "error", "") or "").lower()
        if "no configurado" in err:
            return True
        if not getattr(cpe, "encontrado", False):
            return False
        return clasificar_rama_uisp(cpe) == "enlace_ok"
    if (es_ftth or (onu is not None and getattr(onu, "encontrado", False))) and onu is not None:
        if not getattr(onu, "encontrado", False):
            return True
        return clasificar_rama_bcm(onu) == "enlace_ok"
    return True


def _mensaje_acceso_ok(
    estado: EstadoConexionPPPoE,
    onu: Any | None,
    cpe: Any | None,
    *,
    es_ftth: bool,
    es_radio: bool,
    deuda_positiva: bool = False,
) -> str:
    """Acceso sano: demostrar sesión / potencia / señal y recién preguntar Wi‑Fi."""
    from app.services.barra_senal import (
        anexar_antes_de_preguntas,
        bloque_potencia_onu,
        bloque_senal_antena,
        veredicto_optica,
        veredicto_radio,
    )
    from app.services.conexion_bcm import clasificar_rama_bcm
    from app.services.conexion_uisp import clasificar_rama_uisp

    partes: list[str] = []
    detalle = _detalle_sesion(estado)
    if estado.online is True and estado.sesion is not None:
        nota_deuda = ""
        if deuda_positiva:
            nota_deuda = (
                " Aunque figura saldo pendiente, tu sesión sigue activa: "
                "no parece un corte por mora."
            )
        partes.append(
            f"Tu conexión está activa{detalle}.{nota_deuda} "
            "La línea hasta la red está bien."
        )

    barra = ""
    if es_radio and cpe is not None and getattr(cpe, "encontrado", False):
        if clasificar_rama_uisp(cpe) == "enlace_ok":
            ver = veredicto_radio(getattr(cpe, "signal_dbm", None)) or "se ve bien"
            dbm = getattr(cpe, "signal_dbm", None)
            extra = f" ({int(round(dbm))} dBm)" if isinstance(dbm, (int, float)) else ""
            partes.append(
                f"Revisé tu antena: está en línea y el enlace con la torre {ver}{extra}."
            )
            barra = bloque_senal_antena(getattr(cpe, "signal_dbm", None))
    elif es_ftth and onu is not None and getattr(onu, "encontrado", False):
        if clasificar_rama_bcm(onu) == "enlace_ok":
            from app.services.barra_senal import formatear_dbm_optica

            rx = getattr(onu, "rx_dbm", None)
            if isinstance(rx, (int, float)):
                ver = veredicto_optica(rx) or "se ve bien"
                partes.append(
                    f"Revisé tu ONT: está en línea y la potencia óptica {ver} "
                    f"({formatear_dbm_optica(rx)} dBm)."
                )
                barra = bloque_potencia_onu(rx)
            else:
                partes.append(
                    "Revisé tu ONT: figura en línea, pero no pude leer la potencia "
                    "óptica ahora. Si el problema sigue, pedime que la vuelva a chequear."
                )
        elif getattr(onu, "encontrado", False):
            partes.append(
                "Tu sesión está activa, pero no confirmé la potencia de la ONT en la red."
            )

    if not partes:
        partes.append("El acceso hasta la red se ve bien.")

    # FTTH con sesión OK pero sin lectura BCM: no fingir que la potencia está bien.
    if (
        es_ftth
        and not barra
        and estado.online is True
        and (onu is None or not getattr(onu, "encontrado", False))
    ):
        partes.append(
            "No pude leer la potencia de tu ONT en este momento; si querés, pedime "
            "«qué potencia tiene» y la vuelvo a consultar."
        )

    cuerpo = " ".join(partes)
    msg = f"{cuerpo} {_pregunta_wifi()}"
    if barra:
        return anexar_antes_de_preguntas(msg, barra)
    return msg


def decidir_mensaje_mesa(
    estado: EstadoConexionPPPoE,
    *,
    abonado: Any | None = None,
    onu: Any | None = None,
    cpe: Any | None = None,
    es_ftth: bool = False,
    es_radio: bool = False,
    deuda_positiva: bool = False,
) -> str | None:
    """Texto al abonado según el oficio de mesa. None si no hay internet que tratar."""
    from app.services.conexion_pppoe import clasificar_rama_pppoe

    svc = estado.servicio
    cuenta = clasificar_cuenta(abonado, svc)
    if cuenta in ("baja", "corte"):
        return mensaje_comercial(cuenta)

    if not svc and not str(getattr(abonado, "servicio", "") or "").strip():
        return None
    serv_abo = str(getattr(abonado, "servicio", "") or "").strip().lower() if abonado else ""
    if not svc and serv_abo not in ("internet", "ambos"):
        return None

    if not es_radio and not es_ftth and svc is not None:
        tipo = _tipo_humano(svc)
        es_radio = tipo == "radio"
        es_ftth = tipo == "fibra"

    planta_msg = _planta_mala(onu, cpe, es_ftth=es_ftth, es_radio=es_radio)
    if planta_msg:
        return planta_msg

    planta_ok = _planta_ok(onu, cpe, es_ftth=es_ftth, es_radio=es_radio)
    rama = clasificar_rama_pppoe(estado)

    if not planta_ok:
        return _pregunta_luces(es_radio=es_radio, es_ftth=es_ftth)

    if rama == "sin_sesion" or estado.online is False:
        if _enlace_planta_demostrable(onu, cpe, es_ftth=es_ftth, es_radio=es_radio):
            return _mensaje_sin_sesion_planta_ok(
                onu, cpe, es_ftth=es_ftth, es_radio=es_radio
            )
        extra = ""
        if deuda_positiva:
            extra = (
                " Si hay un saldo pendiente a veces hay corte; también puede ser el equipo. "
            )
        return extra + _pregunta_luces(es_radio=es_radio, es_ftth=es_ftth)

    if rama == "recien_conectado":
        detalle = _detalle_sesion(estado)
        return (
            f"Tu conexión está activa{detalle}: recién reconectó. "
            "Dale uno o dos minutos y probá navegar. ¿Ya te anda o sigue igual?"
        )

    evidencia_ok = rama == "wifi_lan" or estado.online is True
    if es_radio and cpe is not None and getattr(cpe, "encontrado", False):
        from app.services.conexion_uisp import clasificar_rama_uisp

        evidencia_ok = evidencia_ok or clasificar_rama_uisp(cpe) == "enlace_ok"
    if es_ftth and onu is not None and getattr(onu, "encontrado", False):
        from app.services.conexion_bcm import clasificar_rama_bcm

        evidencia_ok = evidencia_ok or clasificar_rama_bcm(onu) == "enlace_ok"
    if evidencia_ok:
        return _mensaje_acceso_ok(
            estado,
            onu,
            cpe,
            es_ftth=es_ftth,
            es_radio=es_radio,
            deuda_positiva=deuda_positiva,
        )

    # Radius sin dato y sin lectura de planta: preguntar luces, no Wi‑Fi.
    return _pregunta_luces(es_radio=es_radio, es_ftth=es_ftth)
