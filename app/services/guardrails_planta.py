"""La rama de planta manda el turno N1: el LLM no diagnostica el acceso.

BillTrack / Radius / BCM / UISP ya clasificaron. Este módulo solo impide
preguntas que contradicen ese veredicto, y enruta servicios que cuelgan
del acceso (Sensa) vs los que no (IMOWI, ADSL sin BCM/UISP).
"""

from __future__ import annotations

from typing import Any

INTENCIONES_MOVIL = frozenset({"movil", "movil_datos", "movil_llamadas"})

_PREGUNTA_WIFI = (
    "Sigamos en tu casa: ¿no te anda en ningún dispositivo o solo por Wi‑Fi? "
    "Si podés, conectá un cable al router y fijate si navega."
)

_PREGUNTA_LUCES_ONT = (
    "Revisé tu ONT: no está registrada en la central. "
    "¿El equipo tiene alguna lucecita prendida (PON o LOS)?"
)

_PREGUNTA_CABLE_AMARILLO = (
    "Revisé tu ONT: la potencia óptica figura fuera de rango en la central. "
    "¿El cablecito amarillo está firme, sin dobleces ni pisadas?"
)

_PREGUNTA_POE = (
    "El servicio de radio está activo, pero la antena no figura enlazada en la red. "
    "¿La fuente PoE (el inyectocito de la antena) tiene la lucecita prendida?"
)

_PREGUNTA_SENSA_NAVEGA = (
    "Tu internet hasta la red está bien. En el equipo donde ves Sensa, "
    "¿abrís alguna página de internet sin problema?"
)

_PREGUNTA_ADSL_TONO = "Vamos con ADSL. ¿El teléfono fijo tiene tono?"


def rama_bcm_desde_contexto(contexto_abonado: str) -> str:
    blob = contexto_abonado or ""
    if "onu_ftth_offline" in blob:
        return "onu_offline"
    if "onu_ftth_potencia_mala" in blob:
        return "potencia_mala"
    if "onu_ftth_enlace_ok" in blob:
        return "enlace_ok"
    return ""


def rama_uisp_desde_contexto(contexto_abonado: str) -> str:
    blob = contexto_abonado or ""
    if "cpe_radio_offline" in blob:
        return "cpe_offline"
    if "cpe_radio_senal_mala" in blob:
        return "senal_mala"
    if "cpe_radio_enlace_ok" in blob:
        return "enlace_ok"
    return ""


def planta_acceso_mala(contexto_abonado: str) -> bool:
    return _planta_mala(
        rama_bcm_desde_contexto(contexto_abonado),
        rama_uisp_desde_contexto(contexto_abonado),
    )


def _pregunta_luces_o_energia(mensaje: str) -> bool:
    t = (mensaje or "").lower()
    if not t:
        return False
    return any(
        k in t
        for k in (
            "lucecita",
            "luces",
            "luz pon",
            "la pon",
            "pon está",
            "pon esta",
            "los apagada",
            "cajita blanca",
            "cajita de la fibra",
            "inyecto",
            "fuente poe",
        )
    )


def _pide_reinicio_ont(mensaje: str) -> bool:
    t = (mensaje or "").lower()
    return "desenchuf" in t and any(k in t for k in ("ont", "onu", "cajita"))


def _pregunta_wifi_casa(mensaje: str) -> bool:
    t = (mensaje or "").lower().replace("\u2011", "-").replace("\u2013", "-")
    t = t.replace("wi-fi", "wifi").replace("wi‑fi", "wifi")
    return "wifi" in t and any(
        k in t for k in ("dispositivo", "cable", "solo", "ningún", "ningun")
    )


def _pregunta_fibra_o_radio(mensaje: str) -> bool:
    t = (mensaje or "").lower()
    return any(
        k in t
        for k in (
            "pon",
            " los",
            "cajita",
            " ont",
            "onu",
            "antena",
            "poe",
            "inyecto",
            "cablecito amarillo",
        )
    )


def _parece_sensa_app(mensaje: str) -> bool:
    t = (mensaje or "").lower()
    return any(
        k in t
        for k in (
            "usuario",
            "contraseña",
            "contrasena",
            "app de sensa",
            "actualizar sensa",
            "credencial",
            "pack",
        )
    )


def _planta_mala(rama_bcm: str, rama_uisp: str) -> bool:
    return rama_bcm in ("onu_offline", "potencia_mala") or rama_uisp in (
        "cpe_offline",
        "senal_mala",
    )


def _planta_ok(rama_bcm: str, rama_uisp: str) -> bool:
    return rama_bcm == "enlace_ok" or rama_uisp == "enlace_ok"


def _mensaje_planta_mala(rama_bcm: str, rama_uisp: str) -> tuple[str, str, str]:
    if rama_bcm == "onu_offline":
        return _PREGUNTA_LUCES_ONT, "bcm_onu_offline", "bloqueado_wifi_con_onu_offline"
    if rama_bcm == "potencia_mala":
        return _PREGUNTA_CABLE_AMARILLO, "bcm_potencia_mala", "bloqueado_wifi_con_potencia_mala"
    if rama_uisp == "cpe_offline":
        return _PREGUNTA_POE, "poe_antena", "bloqueado_wifi_con_cpe_offline"
    return _PREGUNTA_POE, "poe_antena", "bloqueado_wifi_con_senal_mala"


def _mensaje_sensa_acceso_malo(rama_bcm: str, rama_uisp: str) -> tuple[str, str, str]:
    if rama_bcm == "onu_offline":
        return (
            "Sensa se ve por tu internet de casa. Revisé la ONT y no está registrada "
            "en la central: en la TV o el box no va a reproducir hasta que eso vuelva. "
            "¿El equipo tiene alguna lucecita prendida (PON o LOS)?",
            "sensa_acceso_malo",
            "sensa_depende_acceso_malo",
        )
    if rama_bcm == "potencia_mala":
        return (
            "Sensa se ve por tu internet de casa. La potencia óptica de la ONT está "
            "fuera de rango: por eso no va a reproducir bien. "
            "¿El cablecito amarillo está firme, sin dobleces ni pisadas?",
            "sensa_acceso_malo",
            "sensa_depende_acceso_malo",
        )
    if rama_uisp == "cpe_offline":
        return (
            "Sensa se ve por tu internet de casa. La antena no figura enlazada: "
            "en la TV o el box no va a reproducir hasta que vuelva el acceso. "
            "¿La fuente PoE (el inyectocito) tiene la lucecita prendida?",
            "sensa_acceso_malo",
            "sensa_depende_acceso_malo",
        )
    return (
        "Sensa se ve por tu internet de casa. La señal de la antena está fuera de "
        "parámetro: por eso puede no reproducir. "
        "¿La fuente PoE tiene la lucecita prendida?",
        "sensa_acceso_malo",
        "sensa_depende_acceso_malo",
    )


def evaluar_turno_sensa_planta(
    *,
    contexto_abonado: str,
    mensaje_cliente: str = "",
    pasos_cubiertos: list[str] | None = None,
    intencion: str = "",
) -> dict[str, str] | None:
    """Sensa cuelga del acceso de casa. None si la planta está OK o ya se indagó internet en el equipo."""
    _ = mensaje_cliente
    if (intencion or "").strip() != "tv_sensa":
        return None
    pasos = {str(x) for x in (pasos_cubiertos or []) if str(x).strip()}
    # El abonado ya dijo que ese equipo navega → oficio Sensa (app/cuenta), no planta.
    if pasos & {"navega_en_disp", "internet_en_disp", "app_sensa"}:
        return None
    rama_b = rama_bcm_desde_contexto(contexto_abonado)
    rama_u = rama_uisp_desde_contexto(contexto_abonado)
    if not _planta_mala(rama_b, rama_u):
        return None
    if "sensa_acceso_malo" in pasos:
        return None
    msg, paso, mot = _mensaje_sensa_acceso_malo(rama_b, rama_u)
    return {
        "accion": "ask",
        "mensaje": msg,
        "paso_cubierto": paso,
        "motivo": mot,
    }


def aplicar_guardrails_planta(
    *,
    mensaje: str,
    contexto_abonado: str,
    mensaje_cliente: str = "",
    historial_mensajes: list[Any] | None = None,
    accion: str = "ask",
    paso_cubierto: str = "",
    motivo: str = "",
    intencion: str = "",
) -> dict[str, str]:
    """Corrige un acto N1 que contradice BCM/UISP o el servicio activo."""
    _ = (mensaje_cliente, historial_mensajes)
    out = {
        "accion": accion,
        "mensaje": mensaje,
        "paso_cubierto": paso_cubierto,
        "motivo": motivo,
    }
    if accion not in ("ask", "escalate"):
        return out

    intent = (intencion or "").strip()
    if intent in INTENCIONES_MOVIL:
        return out

    rama_b = rama_bcm_desde_contexto(contexto_abonado)
    rama_u = rama_uisp_desde_contexto(contexto_abonado)

    if intent == "tv_sensa":
        if _planta_mala(rama_b, rama_u) and accion == "ask" and (
            _parece_sensa_app(mensaje) or _pregunta_wifi_casa(mensaje)
        ):
            msg, paso, mot = _mensaje_sensa_acceso_malo(rama_b, rama_u)
            return {
                "accion": "ask",
                "mensaje": msg,
                "paso_cubierto": paso,
                "motivo": mot,
            }
        if _planta_ok(rama_b, rama_u) and accion == "ask" and (
            _pregunta_luces_o_energia(mensaje)
            or _pide_reinicio_ont(mensaje)
            or _pregunta_wifi_casa(mensaje)
        ):
            return {
                "accion": "ask",
                "mensaje": _PREGUNTA_SENSA_NAVEGA,
                "paso_cubierto": "navega_en_disp",
                "motivo": "bloqueado_luces_sensa_con_enlace_ok",
            }
        return out

    if intent == "internet_adsl":
        if accion == "ask" and _pregunta_fibra_o_radio(mensaje):
            return {
                "accion": "ask",
                "mensaje": _PREGUNTA_ADSL_TONO,
                "paso_cubierto": "tono_linea",
                "motivo": "bloqueado_fibra_en_adsl",
            }
        return out

    if _planta_mala(rama_b, rama_u) and accion == "ask" and _pregunta_wifi_casa(mensaje):
        msg, paso, mot = _mensaje_planta_mala(rama_b, rama_u)
        return {
            "accion": "ask",
            "mensaje": msg,
            "paso_cubierto": paso,
            "motivo": mot,
        }

    if _planta_ok(rama_b, rama_u) and accion == "ask" and (
        _pregunta_luces_o_energia(mensaje) or _pide_reinicio_ont(mensaje)
    ):
        return {
            "accion": "ask",
            "mensaje": _PREGUNTA_WIFI,
            "paso_cubierto": "wifi_vs_cable_ftth",
            "motivo": "bloqueado_luces_con_enlace_ok",
        }

    return out
