"""Cambio remoto de clave/SSID Wi‑Fi vía BCM (FTTH) para Eko N1.

Seguridad (no negociable):
- Solo con abonado identificado (id de padrón).
- El equipo destino se resuelve SOLO desde BillTrack/BCM del abonado
  (serial ONU o login Radius del servicio). Nunca un serial/radius arbitrario
  pegado en el chat.
- Si hay varios servicios FTTH elegibles, se listan y el abonado elige
  (mismo patrón que multi-cuenta internet).
- La contraseña/SSID del mensaje son el *valor* a aplicar, nunca el selector.
- No persistir la contraseña en el contexto de la conversación.

Reglas de negocio (v1):
- Solo fibra/FTTH.
- Misma clave (o SSID) en ambas bandas: wifi=2 (2.4) y wifi=5 (5 GHz).
- Preferir serial; si no hay, userRadius (login BillTrack).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.bcm.contract import ResultadoCambioWifi

logger = logging.getLogger("operations_hub")

QueWifi = Literal["clave", "ssid", "ambos", ""]
FaseWifi = Literal["", "detalle", "pedir_clave", "pedir_ssid", "hecho"]
KindDestino = Literal["serial", "user_radius"]

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


@dataclass(frozen=True)
class DestinoWifiBcm:
    kind: KindDestino
    valor: str

    def clave_cache(self) -> str:
        return f"{self.kind}:{self.valor}"


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


def gestion_remota_activa(ctx: dict | None) -> bool:
    return str((ctx or {}).get("wifi_bcm") or "") == "1"


def mensaje_remoto_disponible() -> str:
    return _MSG_DISPONIBLE


def mensaje_remoto_pedir_clave() -> str:
    return _MSG_PEDIR_CLAVE


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


def _servicios_abonado(db: Session | None, abonado: Any) -> list[Any]:
    try:
        from app.services import billtrack as bt

        dni = str(getattr(abonado, "dni", "") or "").strip()
        if not dni:
            return []
        return list(bt.lookup_servicios_conectividad_por_dni(dni=dni, db=db) or [])
    except Exception:
        logger.debug("wifi_bcm: BillTrack servicios falló", exc_info=True)
        return []


def _servicios_ftth_elegibles(servicios: list[Any]) -> list[Any]:
    from app.services.billtrack import servicio_habilitado
    from app.services.conexion_bcm import es_servicio_ftth

    out: list[Any] = []
    for svc in servicios or []:
        if not es_servicio_ftth(svc):
            continue
        if not servicio_habilitado(svc):
            continue
        out.append(svc)
    return out


def _logins_ftth(servicios_ftth: list[Any]) -> list[str]:
    seen: list[str] = []
    for svc in servicios_ftth:
        login = str(getattr(svc, "login", "") or "").strip()
        if login and login not in seen:
            seen.append(login)
    return seen


def _login_en_lista(login: str, logins: list[str]) -> str:
    want = (login or "").strip().lower()
    if not want:
        return ""
    for l in logins:
        if l.lower() == want:
            return l
    return ""


def _login_autorizado_desde_texto(
    texto: str, servicios_ftth: list[Any]
) -> str:
    """Solo logins del padrón FTTH del abonado (no regex libre)."""
    tl = (texto or "").lower()
    if not tl:
        return ""
    for svc in servicios_ftth:
        login = str(getattr(svc, "login", "") or "").strip()
        if login and login.lower() in tl:
            return login
    # Domicilio / localidad como en BillTrack
    try:
        from app.services import billtrack as bt

        login_dom = bt.extraer_login_por_domicilio(texto, servicios_ftth)
        if login_dom and _login_en_lista(login_dom, _logins_ftth(servicios_ftth)):
            return login_dom
    except Exception:
        pass
    return ""


def _candidatos_numero_para_svc(
    abonado: Any,
    svc: Any | None,
    *,
    db: Session | None,
) -> list[str]:
    from app.services.conexion_bcm import resolver_numero_cliente_bcm

    seen: list[str] = []

    def _add(raw: Any) -> None:
        s = str(raw or "").strip()
        if s and s not in seen:
            seen.append(s)

    if svc is not None:
        _add(getattr(svc, "base_account_number", ""))
    _add(getattr(abonado, "client_number", ""))
    _add(resolver_numero_cliente_bcm(abonado, db))
    return seen


def _buscar_serial(
    db: Session | None,
    abonado: Any,
    ctx: dict,
    svc: Any | None,
) -> str:
    from app.services.conexion_bcm import aplicar_bcm_a_ctx, consultar_onu_bcm

    for nro in _candidatos_numero_para_svc(abonado, svc, db=db):
        onu = consultar_onu_bcm(nro, db=db)
        if onu.encontrado and str(onu.serial or "").strip():
            aplicar_bcm_a_ctx(ctx, onu)
            return str(onu.serial).strip()
        if onu.encontrado:
            aplicar_bcm_a_ctx(ctx, onu)
    return ""


def mensaje_seleccion_servicio_wifi(servicios_ftth: list[Any]) -> str:
    from app.services import billtrack as bt

    return bt.mensaje_seleccion_cuenta_internet(
        servicios_ftth,
        repregunta=False,
    ).replace(
        "¿Con cuál tenés el problema?",
        "¿En cuál querés cambiar el Wi‑Fi?",
    ).replace(
        "¿Cuál de estas cuentas tiene el problema?",
        "¿En cuál de estas cuentas querés cambiar el Wi‑Fi?",
    )


def resolver_destino_wifi_bcm(
    db: Session | None,
    abonado: Any | None,
    ctx: dict,
    *,
    texto: str = "",
) -> tuple[DestinoWifiBcm | None, str, str]:
    """
    Resuelve destino TR Wi‑Fi atado al abonado.
    Retorna (destino|None, motivo, mensaje_si_seleccion).
    motivo especial: necesita_seleccion → mensaje listo para el abonado.
    """
    if abonado is None or not _abonado_id(abonado):
        return None, "sin_abonado", ""

    from app.services.conexion_bcm import resolve_bcm_client

    if resolve_bcm_client(db) is None:
        return None, "bcm_no_configurado", ""

    servicios = _servicios_abonado(db, abonado)
    ftth = _servicios_ftth_elegibles(servicios)
    logins = _logins_ftth(ftth)

    # Si hay servicios en padrón y ninguno es FTTH habilitado → no remoto.
    if servicios and not ftth:
        return None, "no_ftth", ""

    login_txt = _login_autorizado_desde_texto(texto, ftth)
    login_ctx = _login_en_lista(
        str(ctx.get("wifi_bcm_login") or ctx.get("login_seleccionado") or ""),
        logins,
    )
    login = login_txt or login_ctx

    if len(logins) > 1 and not login:
        msg = mensaje_seleccion_servicio_wifi(ftth)
        ctx["wifi_bcm_pendiente_cuenta"] = "1"
        return None, "necesita_seleccion", msg

    if login_txt:
        ctx["wifi_bcm_login"] = login_txt
        ctx["login_seleccionado"] = login_txt
        ctx.pop("wifi_bcm_pendiente_cuenta", None)

    svc_sel = None
    if login:
        for svc in ftth:
            if str(getattr(svc, "login", "") or "").strip() == login:
                svc_sel = svc
                break
    elif len(ftth) == 1:
        svc_sel = ftth[0]
        login = str(getattr(svc_sel, "login", "") or "").strip()
        if login:
            ctx["wifi_bcm_login"] = login
            ctx["login_seleccionado"] = login

    serial = _buscar_serial(db, abonado, ctx, svc_sel)
    if serial:
        return DestinoWifiBcm("serial", serial), "", ""
    if login:
        return DestinoWifiBcm("user_radius", login), "", ""

    # Sin FTTH en padrón pero tal vez ONU por client_number
    if not ftth:
        serial = _buscar_serial(db, abonado, ctx, None)
        if serial:
            return DestinoWifiBcm("serial", serial), "", ""
        return None, "sin_destino", ""

    return None, "sin_serial_ni_login", ""


def _destino_autorizado(
    db: Session | None,
    abonado: Any | None,
    ctx: dict,
    *,
    texto: str = "",
) -> tuple[DestinoWifiBcm | None, str, str]:
    aid = _abonado_id(abonado)
    if not aid:
        return None, "sin_abonado", ""

    bound = str(ctx.get("wifi_bcm_abonado_id") or "").strip()
    kind = str(ctx.get("wifi_bcm_destino_kind") or "").strip()
    valor = str(ctx.get("wifi_bcm_destino_valor") or "").strip()
    # Compat cache viejo solo-serial
    if not valor:
        valor = str(ctx.get("wifi_bcm_serial") or "").strip()
        if valor:
            kind = "serial"

    pendiente = str(ctx.get("wifi_bcm_pendiente_cuenta") or "") == "1"
    if (
        not pendiente
        and bound
        and bound == aid
        and kind in ("serial", "user_radius")
        and valor
        and str(ctx.get("wifi_bcm") or "") == "1"
        and not _login_autorizado_desde_texto(
            texto, _servicios_ftth_elegibles(_servicios_abonado(db, abonado))
        )
    ):
        return DestinoWifiBcm(kind, valor), "", ""  # type: ignore[arg-type]

    if bound and bound != aid:
        logger.warning(
            "wifi_bcm: abonado distinto al vinculado; se invalida destino cacheado"
        )
        for k in (
            "wifi_bcm_serial",
            "wifi_bcm_destino_kind",
            "wifi_bcm_destino_valor",
            "wifi_bcm_abonado_id",
            "wifi_bcm_login",
            "wifi_bcm_pendiente_cuenta",
        ):
            ctx.pop(k, None)
        ctx["wifi_bcm"] = ""

    dest, motivo, msg_sel = resolver_destino_wifi_bcm(
        db, abonado, ctx, texto=texto
    )
    if motivo == "necesita_seleccion":
        return None, motivo, msg_sel
    if dest is None:
        return None, motivo, ""
    ctx["wifi_bcm_abonado_id"] = aid
    ctx["wifi_bcm_destino_kind"] = dest.kind
    ctx["wifi_bcm_destino_valor"] = dest.valor
    if dest.kind == "serial":
        ctx["wifi_bcm_serial"] = dest.valor
        ctx["bcm_serial"] = dest.valor
    else:
        ctx["wifi_bcm_login"] = dest.valor
        ctx["login_seleccionado"] = dest.valor
    ctx.pop("wifi_bcm_pendiente_cuenta", None)
    return dest, "", ""


def _aplicar_password(
    db: Session | None, destino: DestinoWifiBcm, password: str
) -> tuple[bool, str]:
    from app.services.conexion_bcm import resolve_bcm_client

    client = resolve_bcm_client(db)
    if client is None:
        return False, "bcm no configurado"
    if not destino.valor:
        return False, "destino vacío"
    if destino.kind == "serial":
        resultados = client.modificar_wifi_password_ambas_bandas(
            destino.valor, password
        )
    else:
        resultados = client.modificar_wifi_password_ambas_bandas_por_user_radius(
            destino.valor, password
        )
    ok, err = _resumen_resultados(resultados)
    logger.info(
        "wifi_bcm password %s kind=%s dest=%s bandas=%s err=%s",
        "ok" if ok else "falló",
        destino.kind,
        destino.valor[:24],
        ",".join(r.banda for r in resultados),
        err,
    )
    return ok, err


def _aplicar_ssid(
    db: Session | None, destino: DestinoWifiBcm, ssid: str
) -> tuple[bool, str]:
    from app.services.conexion_bcm import resolve_bcm_client

    client = resolve_bcm_client(db)
    if client is None:
        return False, "bcm no configurado"
    if not destino.valor:
        return False, "destino vacío"
    if destino.kind == "serial":
        resultados = client.modificar_wifi_ssid_ambas_bandas(destino.valor, ssid)
    else:
        resultados = client.modificar_wifi_ssid_ambas_bandas_por_user_radius(
            destino.valor, ssid
        )
    ok, err = _resumen_resultados(resultados)
    logger.info(
        "wifi_bcm ssid %s kind=%s dest=%s bandas=%s err=%s",
        "ok" if ok else "falló",
        destino.kind,
        destino.valor[:24],
        ",".join(r.banda for r in resultados),
        err,
    )
    return ok, err


# Compat tests / callers antiguos
def resolver_serial_wifi_bcm(
    db: Session | None,
    abonado: Any | None,
    ctx: dict,
) -> tuple[str, str]:
    dest, motivo, _msg = resolver_destino_wifi_bcm(db, abonado, ctx, texto="")
    if dest and dest.kind == "serial":
        return dest.valor, ""
    if dest and dest.kind == "user_radius":
        # Serial no disponible; destino OK vía radius — exponer vacío con motivo ok_radius
        ctx["wifi_bcm_destino_kind"] = dest.kind
        ctx["wifi_bcm_destino_valor"] = dest.valor
        return "", "usar_user_radius"
    return "", motivo or "sin_serial"


def turno_cambio_wifi_bcm(
    *,
    db: Session | None,
    abonado: Any | None,
    ctx: dict,
    texto: str,
) -> dict[str, str] | None:
    """
    Un turno del flujo remoto. None = usar guía local (no FTTH / sin destino).

    Retorno: mensaje, paso_cubierto, motivo (y opcionalmente listo=1).
    """
    if abonado is None or not _abonado_id(abonado):
        return {
            "mensaje": _MSG_SIN_ABONADO,
            "paso_cubierto": "dato_reclamo",
            "motivo": "wifi_bcm_sin_abonado",
        }

    flag = str(ctx.get("wifi_bcm") or "").strip()
    if flag == "0":
        return None

    txt = (texto or "").strip()
    dest, motivo, msg_sel = _destino_autorizado(db, abonado, ctx, texto=txt)
    if motivo == "necesita_seleccion":
        # Conservar intención (clave/ssid/ambos) del mensaje que disparó la lista.
        if str(ctx.get("wifi_bcm_que") or "") not in ("clave", "ssid", "ambos"):
            q0 = interpretar_que_cambiar(txt)
            if q0:
                ctx["wifi_bcm_que"] = q0
        _marcar_paso(ctx, "seleccion_cuenta_wifi_bcm")
        return {
            "mensaje": msg_sel or "¿En cuál cuenta de fibra querés cambiar el Wi‑Fi?",
            "paso_cubierto": "seleccion_cuenta_wifi_bcm",
            "motivo": "wifi_bcm_seleccion_cuenta",
        }
    if dest is None:
        ctx["wifi_bcm"] = "0"
        logger.info("wifi_bcm remoto no disponible: %s", motivo or "sin_destino")
        return None
    ctx["wifi_bcm"] = "1"

    que: QueWifi = str(ctx.get("wifi_bcm_que") or "")  # type: ignore[assignment]
    if que not in ("clave", "ssid", "ambos"):
        que = ""
    fase: FaseWifi = str(ctx.get("wifi_bcm_fase") or "")  # type: ignore[assignment]
    if fase not in ("detalle", "pedir_clave", "pedir_ssid", "hecho"):
        fase = ""

    # --- Detalle: qué cambiar ---
    if not que:
        # Si el mensaje es solo la elección de cuenta, pedir detalle (no tomar login como clave).
        login_only = _login_autorizado_desde_texto(
            txt, _servicios_ftth_elegibles(_servicios_abonado(db, abonado))
        )
        if login_only and login_only.lower() == txt.lower().strip():
            ctx["wifi_bcm_fase"] = "detalle"
            _marcar_paso(ctx, "cambio_clave_wifi_detalle")
            return {
                "mensaje": _MSG_DISPONIBLE,
                "paso_cubierto": "cambio_clave_wifi_detalle",
                "motivo": "wifi_bcm_detalle",
            }
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
        dest_ok, _m, _s = _destino_autorizado(db, abonado, ctx, texto="")
        if dest_ok is None:
            ctx["wifi_bcm_fase"] = "hecho"
            return {
                "mensaje": _MSG_FALLO,
                "paso_cubierto": "derivar_clave_wifi",
                "motivo": "wifi_bcm_fallo",
            }
        ok, _err = _aplicar_password(db, dest_ok, txt.strip())
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
        dest_ok, _m, _s = _destino_autorizado(db, abonado, ctx, texto="")
        if dest_ok is None:
            ctx["wifi_bcm_fase"] = "hecho"
            return {
                "mensaje": _MSG_FALLO,
                "paso_cubierto": "derivar_clave_wifi",
                "motivo": "wifi_bcm_fallo",
            }
        ok, _err = _aplicar_ssid(db, dest_ok, txt.strip())
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

    return None
