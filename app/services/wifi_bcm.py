"""Cambio remoto de clave/SSID Wi‑Fi vía BCM (FTTH) para Eko N1.

Seguridad (no negociable):
- Solo con abonado identificado (id de padrón).
- El equipo destino se resuelve SOLO desde la identidad del abonado → BCM
  (client_number / BillTrack). Nunca desde el texto del chat ni desde un
  serial/radius arbitrario del contexto sin vínculo al abonado.
- La contraseña/SSID del mensaje son el *valor* a aplicar, nunca el selector
  del CPE.
- No persistir la contraseña en el contexto de la conversación.

Reglas de negocio (v1):
- Solo fibra/FTTH con serial ONU en BCM.
- Misma clave (o SSID) en ambas bandas: wifi=2 (2.4) y wifi=5 (5 GHz).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.bcm.contract import ResultadoCambioWifi

logger = logging.getLogger("operations_hub")

QueWifi = Literal["clave", "ssid", "ambos", ""]
FaseWifi = Literal["", "detalle", "pedir_clave", "pedir_ssid", "hecho"]

_MSG_DISPONIBLE = (
    "Puedo cambiarlo desde acá en tu equipo de fibra (2.4 y 5 GHz). "
    "¿Querés cambiar la contraseña, el nombre de la red, o las dos cosas?"
)
_MSG_PEDIR_CLAVE = (
    "Escribí la *clave nueva* (mínimo 8 caracteres). "
    "La voy a aplicar solo en tu equipo, en 2.4 GHz y en 5 GHz."
)
_MSG_PEDIR_SSID = (
    "Escribí el *nombre nuevo* de la red (SSID), hasta 32 caracteres. "
    "Lo aplico solo en tu equipo, en 2.4 GHz y en 5 GHz."
)
_MSG_CLAVE_INVALIDA = (
    "Esa clave no sirve: usá entre 8 y 63 caracteres "
    "(letras, números o símbolos; sin espacios al inicio/final)."
)
_MSG_SSID_INVALIDO = (
    "Ese nombre no sirve: usá entre 1 y 32 caracteres, sin solo espacios."
)
_MSG_CIERRE_OLVIDAR = (
    "En el celular u otros dispositivos: *olvidá* esa red Wi‑Fi, "
    "volvé a buscarla en redes disponibles y conectate de nuevo."
)
_MSG_OK_CLAVE = (
    "Listo: el cambio de clave Wi‑Fi ya quedó aplicado en *tu* equipo "
    "(2.4 GHz y 5 GHz). "
    + _MSG_CIERRE_OLVIDAR
)
_MSG_OK_SSID = (
    "Listo: el nombre de la red ya quedó aplicado en *tu* equipo "
    "(2.4 GHz y 5 GHz). "
    + _MSG_CIERRE_OLVIDAR
)
_MSG_OK_AMBOS = (
    "Listo: nombre y clave Wi‑Fi ya quedaron aplicados en *tu* equipo "
    "(2.4 GHz y 5 GHz). "
    + _MSG_CIERRE_OLVIDAR
)
_MSG_FALLO = (
    "No pude aplicar el cambio en el equipo desde acá. "
    "Podés intentarlo en el módem/router con la etiqueta, "
    "o te derivo con un agente. ¿Preferís que te derive?"
)
_MSG_SIN_ABONADO = (
    "Para cambiar el Wi‑Fi desde acá necesito identificarte primero "
    "(DNI o N.º de socio). ¿Me pasás el dato?"
)

_RE_SOLO_DETALLE = re.compile(
    r"^(la\s+)?(clave|contrase[nñ]a|password|ssid|nombre|"
    r"ambas|los\s+dos|las\s+dos|las\s+dos\s+cosas)(\s+del?\s+wifi)?$",
    re.IGNORECASE,
)


def validar_password_wifi(password: str) -> str:
    """Devuelve mensaje de error o '' si es válida (WPA2-PSK 8–63)."""
    pwd = (password or "").strip()
    if not (8 <= len(pwd) <= 63):
        return _MSG_CLAVE_INVALIDA
    if any(c in pwd for c in ("\n", "\r", "\t")):
        return _MSG_CLAVE_INVALIDA
    return ""


def validar_ssid_wifi(ssid: str) -> str:
    nombre = (ssid or "").strip()
    if not (1 <= len(nombre) <= 32):
        return _MSG_SSID_INVALIDO
    if any(c in nombre for c in ("\n", "\r", "\t")):
        return _MSG_SSID_INVALIDO
    return ""


def interpretar_que_cambiar(texto: str) -> QueWifi:
    t = (texto or "").strip().lower()
    if not t:
        return ""
    if any(
        k in t
        for k in (
            "ambas",
            "los dos",
            "las dos",
            "los 2",
            "las 2",
            "clave y nombre",
            "nombre y clave",
            "ssid y clave",
            "clave y ssid",
            "contraseña y nombre",
            "nombre y contraseña",
        )
    ):
        return "ambos"
    if any(
        k in t
        for k in (
            "ssid",
            "nombre de la red",
            "nombre de red",
            "nombre del wifi",
            "nombre wifi",
            "solo el nombre",
            "el nombre",
        )
    ) and not any(k in t for k in ("clave", "contraseña", "password")):
        return "ssid"
    if t in ("nombre", "ssid"):
        return "ssid"
    if any(k in t for k in ("clave", "contraseña", "password", "pass")):
        return "clave"
    if t in ("la clave", "la contraseña"):
        return "clave"
    return ""


def mensaje_remoto_detalle() -> str:
    return _MSG_DISPONIBLE


def mensaje_remoto_pedir_clave() -> str:
    return _MSG_PEDIR_CLAVE


def gestion_remota_activa(ctx: dict | None) -> bool:
    return str((ctx or {}).get("wifi_bcm") or "") == "1"


def _abonado_id(abonado: Any | None) -> str:
    return str(getattr(abonado, "id", "") or "").strip()


def _marcar_paso(ctx: dict, paso: str) -> None:
    cub = [str(x) for x in (ctx.get("pasos_cubiertos") or []) if str(x).strip()]
    if paso and paso not in cub:
        cub.append(paso)
    ctx["pasos_cubiertos"] = cub


def _resumen_resultados(resultados: list[ResultadoCambioWifi]) -> tuple[bool, str]:
    if not resultados:
        return False, "sin respuesta BCM"
    if all(r.ok for r in resultados):
        return True, ""
    errores = [r.error or f"banda {r.banda} falló" for r in resultados if not r.ok]
    return False, "; ".join(errores)[:160]


def _candidatos_numero_solo_abonado(
    abonado: Any,
    *,
    db: Session | None,
) -> list[str]:
    """Números ERP del abonado identificado. No usa ctx (evita inyección)."""
    from app.services.conexion_bcm import resolver_numero_cliente_bcm

    seen: list[str] = []

    def _add(raw: Any) -> None:
        s = str(raw or "").strip()
        if s and s not in seen:
            seen.append(s)

    _add(getattr(abonado, "client_number", ""))
    _add(resolver_numero_cliente_bcm(abonado, db))
    dni = str(getattr(abonado, "dni", "") or "").strip()
    if dni:
        try:
            from app.services import billtrack as bt

            servicios = bt.lookup_servicios_conectividad_por_dni(dni=dni, db=db) or []
            for svc in servicios:
                _add(getattr(svc, "base_account_number", ""))
        except Exception:
            logger.debug("wifi_bcm: BillTrack candidatos falló", exc_info=True)
    return seen


def resolver_serial_wifi_bcm(
    db: Session | None,
    abonado: Any | None,
    ctx: dict,
) -> tuple[str, str]:
    """
    Resuelve serial ONU para TR Wi‑Fi atado al abonado.
    Retorna (serial, motivo_si_no). Ignora seriales sueltos del ctx.
    """
    if abonado is None or not _abonado_id(abonado):
        return "", "sin_abonado"

    from app.services.conexion_bcm import (
        aplicar_bcm_a_ctx,
        consultar_onu_bcm,
        es_servicio_ftth,
        resolve_bcm_client,
    )

    if resolve_bcm_client(db) is None:
        return "", "bcm_no_configurado"

    servicio = None
    try:
        from app.services import billtrack as bt

        dni = str(getattr(abonado, "dni", "") or "").strip()
        if dni:
            servicios = bt.lookup_servicios_conectividad_por_dni(dni=dni, db=db) or []
            servicio = bt.elegir_servicio_principal(servicios)
    except Exception:
        logger.debug("wifi_bcm: no se pudo leer servicios BillTrack", exc_info=True)

    if servicio is not None and not es_servicio_ftth(servicio):
        return "", "no_ftth"

    candidatos = _candidatos_numero_solo_abonado(abonado, db=db)
    if not candidatos:
        return "", "sin_numero_cliente"

    last = None
    for nro in candidatos:
        onu = consultar_onu_bcm(nro, db=db)
        last = onu
        if onu.encontrado and str(onu.serial or "").strip():
            aplicar_bcm_a_ctx(ctx, onu)
            return str(onu.serial).strip(), ""
        if onu.encontrado:
            aplicar_bcm_a_ctx(ctx, onu)

    if last is not None and not last.encontrado:
        return "", "onu_no_encontrada"
    return "", "sin_serial"


def _serial_autorizado(
    db: Session | None,
    abonado: Any | None,
    ctx: dict,
    *,
    forzar_resolver: bool = False,
) -> tuple[str, str]:
    """Serial cacheado solo si está vinculado al mismo abonado_id."""
    aid = _abonado_id(abonado)
    if not aid:
        return "", "sin_abonado"

    bound = str(ctx.get("wifi_bcm_abonado_id") or "").strip()
    cached = str(ctx.get("wifi_bcm_serial") or "").strip()
    if (
        not forzar_resolver
        and bound
        and bound == aid
        and cached
        and str(ctx.get("wifi_bcm") or "") == "1"
    ):
        return cached, ""

    # Abonado distinto o sin vínculo: invalidar cache y resolver de nuevo.
    if bound and bound != aid:
        logger.warning(
            "wifi_bcm: abonado distinto al vinculado; se invalida serial cacheado"
        )
        ctx.pop("wifi_bcm_serial", None)
        ctx.pop("wifi_bcm_abonado_id", None)
        ctx["wifi_bcm"] = ""

    serial, motivo = resolver_serial_wifi_bcm(db, abonado, ctx)
    if not serial:
        return "", motivo
    ctx["wifi_bcm_abonado_id"] = aid
    ctx["wifi_bcm_serial"] = serial
    ctx["bcm_serial"] = serial
    return serial, ""


def _aplicar_password(
    db: Session | None, serial: str, password: str
) -> tuple[bool, str]:
    from app.services.conexion_bcm import resolve_bcm_client

    client = resolve_bcm_client(db)
    if client is None:
        return False, "bcm no configurado"
    sn = (serial or "").strip()
    if not sn:
        return False, "serial vacío"
    resultados = client.modificar_wifi_password_ambas_bandas(sn, password)
    ok, err = _resumen_resultados(resultados)
    if not ok:
        logger.info(
            "wifi_bcm password falló serial=%s bandas=%s err=%s",
            sn[:24],
            ",".join(r.banda for r in resultados),
            err,
        )
    else:
        logger.info(
            "wifi_bcm password ok serial=%s bandas=%s",
            sn[:24],
            ",".join(r.banda for r in resultados),
        )
    return ok, err


def _aplicar_ssid(db: Session | None, serial: str, ssid: str) -> tuple[bool, str]:
    from app.services.conexion_bcm import resolve_bcm_client

    client = resolve_bcm_client(db)
    if client is None:
        return False, "bcm no configurado"
    sn = (serial or "").strip()
    if not sn:
        return False, "serial vacío"
    resultados = client.modificar_wifi_ssid_ambas_bandas(sn, ssid)
    ok, err = _resumen_resultados(resultados)
    if not ok:
        logger.info(
            "wifi_bcm ssid falló serial=%s bandas=%s err=%s",
            sn[:24],
            ",".join(r.banda for r in resultados),
            err,
        )
    else:
        logger.info(
            "wifi_bcm ssid ok serial=%s bandas=%s",
            sn[:24],
            ",".join(r.banda for r in resultados),
        )
    return ok, err


def turno_cambio_wifi_bcm(
    *,
    db: Session | None,
    abonado: Any | None,
    ctx: dict,
    texto: str,
) -> dict[str, str] | None:
    """
    Un turno del flujo remoto. None = usar guía local (no FTTH / sin serial).

    Retorno: mensaje, paso_cubierto, motivo (y opcionalmente listo=1).
    """
    if abonado is None or not _abonado_id(abonado):
        # No abrir remoto anónimo: el canal debe identificar antes.
        return {
            "mensaje": _MSG_SIN_ABONADO,
            "paso_cubierto": "dato_reclamo",
            "motivo": "wifi_bcm_sin_abonado",
        }

    flag = str(ctx.get("wifi_bcm") or "").strip()
    if flag == "0":
        return None

    serial, motivo = _serial_autorizado(db, abonado, ctx)
    if not serial:
        ctx["wifi_bcm"] = "0"
        logger.info("wifi_bcm remoto no disponible: %s", motivo or "sin_serial")
        return None
    ctx["wifi_bcm"] = "1"

    que: QueWifi = str(ctx.get("wifi_bcm_que") or "")  # type: ignore[assignment]
    if que not in ("clave", "ssid", "ambos"):
        que = ""
    fase: FaseWifi = str(ctx.get("wifi_bcm_fase") or "")  # type: ignore[assignment]
    if fase not in ("detalle", "pedir_clave", "pedir_ssid", "hecho"):
        fase = ""

    txt = (texto or "").strip()

    # --- Detalle: qué cambiar ---
    if not que:
        interpretado = interpretar_que_cambiar(txt)
        if interpretado:
            que = interpretado
            ctx["wifi_bcm_que"] = que
            _marcar_paso(ctx, "cambio_clave_wifi_detalle")
        else:
            ctx["wifi_bcm_fase"] = "detalle"
            _marcar_paso(ctx, "cambio_clave_wifi_detalle")
            return {
                "mensaje": _MSG_DISPONIBLE,
                "paso_cubierto": "cambio_clave_wifi_detalle",
                "motivo": "wifi_bcm_detalle",
            }

    # Arranque: pedir el primer valor
    if fase in ("", "detalle"):
        if que == "ssid":
            ctx["wifi_bcm_fase"] = "pedir_ssid"
            return {
                "mensaje": _MSG_PEDIR_SSID,
                "paso_cubierto": "wifi_bcm_pedir_ssid",
                "motivo": "wifi_bcm_pedir_ssid",
            }
        ctx["wifi_bcm_fase"] = "pedir_clave"
        return {
            "mensaje": _MSG_PEDIR_CLAVE,
            "paso_cubierto": "wifi_bcm_pedir_clave",
            "motivo": "wifi_bcm_pedir_clave",
        }

    # --- Pedir / aplicar clave ---
    if fase == "pedir_clave":
        if _RE_SOLO_DETALLE.match(txt) and interpretar_que_cambiar(txt):
            ctx["wifi_bcm_que"] = interpretar_que_cambiar(txt)
            que = ctx["wifi_bcm_que"]  # type: ignore[assignment]
            if que == "ssid":
                ctx["wifi_bcm_fase"] = "pedir_ssid"
                return {
                    "mensaje": _MSG_PEDIR_SSID,
                    "paso_cubierto": "wifi_bcm_pedir_ssid",
                    "motivo": "wifi_bcm_pedir_ssid",
                }
            return {
                "mensaje": _MSG_PEDIR_CLAVE,
                "paso_cubierto": "wifi_bcm_pedir_clave",
                "motivo": "wifi_bcm_pedir_clave",
            }
        err = validar_password_wifi(txt)
        if err:
            return {
                "mensaje": err,
                "paso_cubierto": "wifi_bcm_pedir_clave",
                "motivo": "wifi_bcm_clave_invalida",
            }
        # Revalidar vínculo abonado→serial justo antes de escribir.
        serial_ok, _m = _serial_autorizado(db, abonado, ctx)
        if not serial_ok:
            ctx["wifi_bcm_fase"] = "hecho"
            return {
                "mensaje": _MSG_FALLO,
                "paso_cubierto": "derivar_clave_wifi",
                "motivo": "wifi_bcm_fallo",
            }
        ok, _err = _aplicar_password(db, serial_ok, txt.strip())
        if not ok:
            ctx["wifi_bcm_fase"] = "hecho"
            _marcar_paso(ctx, "derivar_clave_wifi")
            return {
                "mensaje": _MSG_FALLO,
                "paso_cubierto": "derivar_clave_wifi",
                "motivo": "wifi_bcm_fallo",
            }
        _marcar_paso(ctx, "wifi_bcm_clave_ok")
        if que == "ambos":
            ctx["wifi_bcm_fase"] = "pedir_ssid"
            return {
                "mensaje": (
                    "Clave actualizada en 2.4 y 5 GHz. "
                    + _MSG_PEDIR_SSID
                ),
                "paso_cubierto": "wifi_bcm_pedir_ssid",
                "motivo": "wifi_bcm_pedir_ssid",
            }
        ctx["wifi_bcm_fase"] = "hecho"
        _marcar_paso(ctx, "aviso_reconexion")
        return {
            "mensaje": _MSG_OK_CLAVE,
            "paso_cubierto": "aviso_reconexion",
            "motivo": "wifi_bcm_ok",
            "listo": "1",
        }

    # --- Pedir / aplicar SSID ---
    if fase == "pedir_ssid":
        err = validar_ssid_wifi(txt)
        if err:
            return {
                "mensaje": err,
                "paso_cubierto": "wifi_bcm_pedir_ssid",
                "motivo": "wifi_bcm_ssid_invalido",
            }
        serial_ok, _m = _serial_autorizado(db, abonado, ctx)
        if not serial_ok:
            ctx["wifi_bcm_fase"] = "hecho"
            return {
                "mensaje": _MSG_FALLO,
                "paso_cubierto": "derivar_clave_wifi",
                "motivo": "wifi_bcm_fallo",
            }
        ok, _err = _aplicar_ssid(db, serial_ok, txt.strip())
        if not ok:
            ctx["wifi_bcm_fase"] = "hecho"
            _marcar_paso(ctx, "derivar_clave_wifi")
            return {
                "mensaje": _MSG_FALLO,
                "paso_cubierto": "derivar_clave_wifi",
                "motivo": "wifi_bcm_fallo",
            }
        ctx["wifi_bcm_fase"] = "hecho"
        _marcar_paso(ctx, "wifi_bcm_ssid_ok")
        _marcar_paso(ctx, "aviso_reconexion")
        msg = _MSG_OK_AMBOS if que == "ambos" else _MSG_OK_SSID
        return {
            "mensaje": msg,
            "paso_cubierto": "aviso_reconexion",
            "motivo": "wifi_bcm_ok",
            "listo": "1",
        }

    # Fase hecho: dejar que el playbook local valide / derive
    return None
