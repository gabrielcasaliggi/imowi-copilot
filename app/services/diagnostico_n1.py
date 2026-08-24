"""Diagnóstico N1 dirigido por IA — el playbook es checklist, no guión rígido."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import BOT_DISPLAY_NAME
from app.domain.flujos_abonado import PasoPlaybook, intencion_es_facturacion

logger = logging.getLogger("operations_hub")

# Intenciones donde la IA diagnostica como técnico (playbook = guía).
INTENCIONES_DIAGNOSTICO = frozenset({
    "internet",
    "internet_ftth",
    "internet_adsl",
    "internet_radio",
    "internet_lento",
    "internet_intermitente",
    "wifi",
    "cambio_clave_wifi",
    "movil",
    "movil_datos",
    "movil_llamadas",
    "telefono_fija",
    "tv_sensa",
    "no_tecnico",
    "ecolan_b2b",
    "facturacion",
    "facturacion_pago",
    "facturacion_descarga",
    "facturacion_informar_pago",
    "facturacion_factura",
    "facturacion_estado_cuenta",
    "facturacion_reclamo",
    "reactivacion_pago",
})

# Heurísticas PON/LOS / cable amarillo: solo fibra. Nunca en TV OTT, móvil, factura, etc.
INTENCIONES_OPTICAS = frozenset({
    "internet_ftth",
    "internet",
})

_MOTIVOS_OPTICOS = frozenset({
    "fibra_danada",
    "los_con_chequeo_fibra",
    "los_y_fibra_danada",
    "los_confirmada",
    "bloqueado_wifi_post_los",
    "pon_verde_enlace_ok",
})

_MSG_APN_ANDROID = (
    "En Android andá a Ajustes > Redes móviles o Conexiones > "
    "Nombres de punto de acceso (APN). Creá o editá uno con Nombre = imowi y "
    "APN = apn1.catel.org.ar (el resto en blanco). Guardalo, seleccioná ese APN "
    "y reiniciá los datos. ¿Navega?"
)

_MSG_APN_IOS = (
    "En iPhone 11 en adelante o con eSIM el APN suele ser automático. "
    "Si es un modelo más viejo: Configuración > Datos celulares > Opciones > "
    "Red de datos celulares → Punto de acceso = apn1.catel.org.ar y Usuario = imowi. "
    "¿Quedó bien?"
)


def detectar_so_movil(
    mensaje_cliente: str,
    historial_mensajes: list[Any] | None = None,
) -> str | None:
    """Detecta Android / iOS declarado por el abonado. No asume por apps."""
    chunks: list[str] = [str(mensaje_cliente or "")]
    for m in historial_mensajes or []:
        autor = getattr(m, "autor", None) or (m.get("autor") if isinstance(m, dict) else "")
        texto = getattr(m, "texto", None) or (m.get("texto") if isinstance(m, dict) else "")
        if not texto and isinstance(m, dict):
            texto = m.get("contenido") or m.get("mensaje") or ""
        a = str(autor or "").lower()
        if a in ("cliente", "abonado", "user", "usuario") or a.startswith("abon"):
            chunks.append(str(texto or ""))
        dire = getattr(m, "direccion", None) or (m.get("direccion") if isinstance(m, dict) else "")
        if str(dire or "").lower() in ("in", "inbound", "entrada"):
            chunks.append(str(texto or ""))

    t = " ".join(chunks).lower()
    if any(
        k in t
        for k in (
            "no es iphone",
            "no es un iphone",
            "no es ios",
            "no tengo iphone",
            "no uso iphone",
        )
    ):
        return "android"

    ios_hit = any(
        k in t
        for k in (
            "iphone",
            "ios",
            "es un iphone",
            "tengo iphone",
            "mi iphone",
        )
    )
    android_hit = any(
        k in t
        for k in (
            "android",
            "es android",
            "moto g",
            "moto e",
            "moto ",
            "motorola",
            "samsung",
            "galaxy",
            "xiaomi",
            "redmi",
            "huawei",
            "honor",
            "tcl",
            "nokia",
            "pixel",
            "oneplus",
        )
    )
    if android_hit and not ios_hit:
        return "android"
    if ios_hit and not android_hit:
        return "ios"
    if android_hit and ios_hit:
        t_now = (mensaje_cliente or "").lower()
        if any(k in t_now for k in ("android", "moto", "samsung", "xiaomi", "no es iphone")):
            return "android"
        if any(k in t_now for k in ("iphone", "ios")):
            return "ios"
    return None


def _mensaje_apn_para_otro_so(mensaje: str, so: str) -> bool:
    """True si el bot habla de APN/pasos del SO contrario."""
    m = (mensaje or "").lower()
    if so == "android":
        return any(
            k in m
            for k in (
                "iphone",
                "datos celulares",
                "punto de acceso",
                "red de datos celulares",
                "si es un iphone",
                "es un iphone",
                "modelo 11",
                "iphone anteriores",
                "iphone 11",
                "esim",
            )
        )
    if so == "ios":
        return any(
            k in m
            for k in (
                "android",
                "nombres de punto de acceso",
                "ajustes > redes",
                "ajustes > conexiones",
                "nombre = imowi",
            )
        )
    return False


def _corregir_apn_segun_so(mensaje: str, so: str | None) -> tuple[str, str | None]:
    if not so or not _mensaje_apn_para_otro_so(mensaje, so):
        return mensaje, None
    if so == "android":
        return _MSG_APN_ANDROID, "bloqueado_apn_so_android"
    return _MSG_APN_IOS, "bloqueado_apn_so_ios"


_MSG_PACK_ACREDITADO = (
    "Si el APN de Android ya está bien y cargaste un pack (el sistema te dio el OK) "
    "pero igual no navega, no se arregla tocando más el celular. "
    "Te derivo con un agente para que revisen la línea en el sistema. "
    "Quedate en este chat."
)

_MSG_PACK_CHEQUEO = (
    "El APN de Android ya quedó. ¿Cargaste un pack o bono de datos, el sistema te dio el OK "
    "y igual no los tenés disponibles para navegar?"
)


def _blob_cliente_movil(
    mensaje_cliente: str,
    historial_mensajes: list[Any] | None = None,
) -> str:
    partes = [str(mensaje_cliente or "")]
    for m in historial_mensajes or []:
        autor, texto = _autor_texto(m)
        a = (autor or "").lower()
        if a in ("cliente", "abonado", "user", "usuario") or a.startswith("abon"):
            partes.append(texto)
        dire = getattr(m, "direccion", None) or (
            m.get("direccion") if isinstance(m, dict) else ""
        )
        if str(dire or "").lower() in ("in", "inbound", "entrada"):
            partes.append(texto)
    return " ".join(partes).lower()


def pack_acreditado_sin_datos(
    mensaje_cliente: str,
    historial_mensajes: list[Any] | None = None,
) -> bool:
    """Pack/bono cargado (sistema OK) pero los datos no aparecen: N2, no más taps al celular."""
    blob = _blob_cliente_movil(mensaje_cliente, historial_mensajes)
    cargo = any(
        k in blob
        for k in (
            "cargue un pack",
            "cargué un pack",
            "cargue pack",
            "cargué pack",
            "compre un pack",
            "compré un pack",
            "recargue",
            "recargué",
            "me cargo el pack",
            "me cargó el pack",
            "pack de datos",
            "cargue un bono",
            "cargué un bono",
            "bono cargado",
        )
    )
    ok_sistema = any(
        k in blob
        for k in (
            "dio el ok",
            "dio ok",
            "me dio el ok",
            "el sistema me dio",
            "acredito",
            "acreditó",
            "quedo cargado",
            "quedó cargado",
        )
    )
    no_anda = any(
        k in blob
        for k in (
            "no los tengo",
            "no los tengo disponibles",
            "no tengo datos",
            "no me figuran",
            "no disponible",
            "no me aparecen",
            "sigue sin",
            "no navega",
            "sin internet",
            "no me funciona",
        )
    )
    return cargo and (ok_sistema or no_anda)


def _pregunta_tipo_red_inventada(mensaje: str) -> bool:
    m = (mensaje or "").lower()
    return any(
        k in m
        for k in (
            "pasar a 3g",
            "cambiar a 3g",
            "probar en 3g",
            "tipo de red preferida",
            "red preferida",
            "preferida a 3g",
            "forzá 3g",
            "forza 3g",
            "3g por un momento",
            "cambiar a 2g",
        )
    )


def _pregunta_so_otra_vez(mensaje: str, so: str | None) -> bool:
    if not so:
        return False
    m = (mensaje or "").lower()
    return any(
        k in m
        for k in (
            "android o iphone",
            "android o un iphone",
            "es android o",
            "es un iphone",
            "¿es iphone",
            "modelo 11 en adelante",
            "usás esim",
            "usas esim",
        )
    )


def _enriquecer_pasos_movil(
    pasos_cubiertos: list[str],
    so: str | None,
    mensaje_cliente: str,
    historial_mensajes: list[Any] | None = None,
) -> list[str]:
    out = [str(x) for x in (pasos_cubiertos or []) if str(x).strip()]
    if so and "so_dispositivo" not in out:
        out.append("so_dispositivo")
    blob = _blob_cliente_movil(mensaje_cliente, historial_mensajes)
    if so == "android" and any(
        k in blob
        for k in (
            "ya esta asi",
            "ya está así",
            "esta asi",
            "está así",
            "si, esta",
            "sí, está",
            "apn ya",
            "ya lo tengo",
            "ya esta puesto",
            "ya está puesto",
        )
    ):
        if "apn_datos" not in out:
            out.append("apn_datos")
    return out


def aplicar_guardrails_movil(
    *,
    mensaje: str,
    mensaje_cliente: str,
    historial_mensajes: list[Any] | None = None,
    pasos_cubiertos: list[str] | None = None,
    accion: str = "ask",
    so: str | None = None,
) -> dict[str, str]:
    """Corta desvíos típicos: iPhone a un Android, 3G inventado, pack acreditado."""
    so = so or detectar_so_movil(mensaje_cliente, historial_mensajes)
    cubiertos = _enriquecer_pasos_movil(
        list(pasos_cubiertos or []), so, mensaje_cliente, historial_mensajes
    )
    motivo = ""
    paso = ""
    acc = accion or "ask"
    msg = mensaje or ""

    if pack_acreditado_sin_datos(mensaje_cliente, historial_mensajes):
        return {
            "accion": "escalate",
            "mensaje": _MSG_PACK_ACREDITADO,
            "paso_cubierto": "derivar_datos",
            "motivo": "pack_acreditado_sin_datos",
        }

    if acc == "ask" and so:
        msg, motivo_so = _corregir_apn_segun_so(msg, so)
        if motivo_so:
            motivo = motivo_so
            paso = "apn_datos"
        if _pregunta_so_otra_vez(mensaje, so):
            if "apn_datos" in cubiertos:
                msg = _MSG_PACK_CHEQUEO
                motivo = "bloqueado_repregunta_so"
                paso = "consumo_paquete"
            else:
                msg = _MSG_APN_ANDROID if so == "android" else _MSG_APN_IOS
                motivo = "bloqueado_repregunta_so"
                paso = "apn_datos"

    if acc == "ask" and _pregunta_tipo_red_inventada(msg):
        if pack_acreditado_sin_datos(mensaje_cliente, historial_mensajes):
            return {
                "accion": "escalate",
                "mensaje": _MSG_PACK_ACREDITADO,
                "paso_cubierto": "derivar_datos",
                "motivo": "pack_acreditado_sin_datos",
            }
        msg = _MSG_PACK_CHEQUEO
        motivo = "bloqueado_tipo_red_inventada"
        paso = "consumo_paquete"

    return {
        "accion": acc,
        "mensaje": msg,
        "paso_cubierto": paso,
        "motivo": motivo,
    }

MIN_TURNOS_ANTES_ESCALAR = 4

_AFIRMACIONES = (
    "si",
    "sí",
    "sip",
    "correcto",
    "exacto",
    "afirmativo",
    "tal cual",
    "claro",
    "eso",
    "asi es",
    "así es",
    "confirmo",
)

_DANO_FIBRA = (
    "daño",
    "dano",
    "dañado",
    "danado",
    "roto",
    "rota",
    "partido",
    "cortado",
    "quebrado",
    "doblado",
    "quemado",
    "rajado",
    "fisura",
    "roto el cable",
    "cable roto",
)

_WIFI_MARKERS = (
    "wifi",
    "wi-fi",
    "wi fi",
    "por cable",
    "cable directo",
    "saturación",
    "saturacion",
    "canal",
    "solo wifi",
)


def es_intencion_diagnostico(intencion: str) -> bool:
    return (intencion or "").strip() in INTENCIONES_DIAGNOSTICO


def es_intencion_optica(intencion: str) -> bool:
    """True si aplica detección/escalado de fibra (PON/LOS), no TV/móvil/etc."""
    return (intencion or "").strip() in INTENCIONES_OPTICAS


def _parece_diagnostico_optica_fuera_de_lugar(mensaje: str) -> bool:
    """True si el texto parece diagnóstico FTTH (LOS/fibra/cajita) fuera de contexto."""
    tl = (mensaje or "").lower()
    if any(
        k in tl
        for k in (
            "luz los",
            "los en rojo",
            "los apagada",
            "los prendida",
            "cable amarillo",
            "cajita blanca",
            "enlace óptico",
            "enlace optico",
            "pon en verde",
            "luz pon",
        )
    ):
        return True
    return "fibra" in tl and any(
        k in tl for k in ("cajita", "ont", "los", "pon", "óptic", "optic", "visita")
    )


def _motivo_es_optico(motivo: str) -> bool:
    m = (motivo or "").strip().lower()
    if not m:
        return False
    if m in _MOTIVOS_OPTICOS:
        return True
    return any(k in m for k in ("los", "fibra", "optic", "óptic", "pon_verde"))


def _autor_texto(m: Any) -> tuple[str, str]:
    autor = getattr(m, "autor", None) or (m.get("autor") if isinstance(m, dict) else "")
    texto = getattr(m, "texto", None) or (m.get("texto") if isinstance(m, dict) else "")
    if not texto and isinstance(m, dict):
        texto = m.get("contenido") or m.get("mensaje") or ""
    return str(autor or ""), str(texto or "")


def _es_afirmacion(texto: str) -> bool:
    t = (texto or "").lower().strip()
    if not t:
        return False
    if any(k in t for k in ("luz roja", "roja", "encendida", "prendida", "sigue")):
        # "tengo una luz roja" / "sigue en rojo" cuenta como evidencia óptica
        if any(k in t for k in ("roja", "rojo", "los", "pon")):
            return True
    if t in _AFIRMACIONES:
        return True
    return any(t == a or t.startswith(a + " ") or t.startswith(a + ",") for a in _AFIRMACIONES)


def _bot_menciona_los(texto: str) -> bool:
    t = texto or ""
    tl = t.lower()
    if "LOS" in t:
        return True
    return any(
        k in tl
        for k in (
            "luz los",
            "la los",
            "led los",
            "los'",
            "'los",
            "los en",
            "los apagada",
            "los prendida",
            "pon está",
            "pon esta",
        )
    )


def _bot_pregunta_fibra(texto: str) -> bool:
    tl = (texto or "").lower()
    return any(
        k in tl
        for k in (
            "fibra",
            "cable amarillo",
            "dobleces",
            "daños visibles",
            "danos visibles",
            "enchufado en la ont",
            "cable de fibra",
        )
    )


def _tiene_dano_fibra(texto: str) -> bool:
    tl = (texto or "").lower()
    return any(k in tl for k in _DANO_FIBRA)


def _bot_pregunta_pon_los(texto: str) -> bool:
    tl = (texto or "").lower()
    return any(
        k in tl
        for k in (
            "luz pon",
            "la pon",
            "pon está",
            "pon esta",
            "pon en verde",
            "los apagada",
            "los está",
            "los esta",
            "qué colores",
            "que colores",
            "qué luces",
            "que luces",
        )
    ) or (_bot_menciona_los(texto) and "pon" in tl)


def _cliente_confirma_pon_verde(texto: str) -> bool:
    """True si reporta PON/enlace en verde (capa óptica OK)."""
    t = (texto or "").lower()
    if any(k in t for k in ("roja", "rojo")) and "verde" not in t:
        return False
    if "los" in t and any(k in t for k in ("roja", "rojo", "prendida", "encendida")):
        return False
    return any(
        k in t
        for k in (
            "verde fija",
            "verde fijo",
            "luz verde",
            "pon verde",
            "verde la pon",
            "pon en verde",
            "todo verde",
            "luces verdes",
            "luz pon verde",
            "está verde",
            "esta verde",
            "verde ok",
            "verde bien",
        )
    )


def _afirmacion_corta_ok(texto: str) -> bool:
    t = (texto or "").lower().strip()
    t = re.sub(r"[¡!.,¿?]+", "", t).strip()
    if t in _AFIRMACIONES or t in ("sisi", "sipi", "ok", "dale", "listo", "perfecto"):
        return True
    return _es_afirmacion(texto)


def detectar_enlace_optico_ok(
    mensaje_cliente: str,
    historial_mensajes: list[Any] | None,
) -> bool:
    """True si el cliente confirmó PON verde / enlace óptico bien (no hay LOS roja)."""
    if detectar_falla_optica_escalar(mensaje_cliente, historial_mensajes):
        return False
    parts = [_autor_texto(m) for m in (historial_mensajes or [])]
    last = (mensaje_cliente or "").strip()
    if last and (not parts or parts[-1][1].strip() != last):
        parts.append(("cliente", last))
    recent = parts[-14:]
    if not recent:
        return False
    if _cliente_confirma_pon_verde(last):
        return True
    for i, (autor, texto) in enumerate(recent):
        if autor != "bot" or not _bot_pregunta_pon_los(texto):
            continue
        for autor2, texto2 in recent[i + 1 :]:
            if autor2 != "cliente":
                continue
            t2 = (texto2 or "").lower()
            if any(k in t2 for k in ("roja", "rojo")) and "verde" not in t2:
                return False
            if "los" in t2 and any(k in t2 for k in ("roja", "rojo", "prendida")):
                return False
            if _cliente_confirma_pon_verde(t2) or _afirmacion_corta_ok(texto2):
                return True
            break
    return False


def detectar_falla_optica_escalar(
    mensaje_cliente: str,
    historial_mensajes: list[Any] | None,
) -> str | None:
    """Si hay LOS confirmada + chequeo de fibra (o fibra dañada), hay que escalar.

    No seguir con WiFi / saturación de canal: es capa óptica.
    """
    parts = [_autor_texto(m) for m in (historial_mensajes or [])]
    last = (mensaje_cliente or "").strip()
    if last and (not parts or parts[-1][1].strip() != last):
        parts.append(("cliente", last))
    recent = parts[-14:]
    if not recent:
        return None

    bot_hablo_los = False
    cliente_confirmo_los = False
    bot_pregunto_fibra = False
    for i, (autor, texto) in enumerate(recent):
        if autor == "bot" and _bot_menciona_los(texto):
            bot_hablo_los = True
            for autor2, texto2 in recent[i + 1 :]:
                if autor2 == "cliente":
                    if _es_afirmacion(texto2) or _bot_menciona_los(texto2) or "roja" in texto2.lower():
                        cliente_confirmo_los = True
                    break
        if autor == "bot" and _bot_pregunta_fibra(texto):
            bot_pregunto_fibra = True

    last_l = last.lower()
    dano = _tiene_dano_fibra(last_l)
    cliente_dice_los = any(
        k in last_l
        for k in (
            "luz los",
            "los roja",
            "los en rojo",
            "tengo los",
            "led los",
            "la los",
            "roja de los",
            "rojo de los",
            "luz de los",
        )
    ) or (
        "los" in last_l
        and any(k in last_l for k in ("roja", "rojo", "luz"))
    )

    if dano and (bot_pregunto_fibra or bot_hablo_los or cliente_confirmo_los):
        return "fibra_danada"
    if cliente_confirmo_los and bot_pregunto_fibra and last:
        return "los_con_chequeo_fibra"
    if cliente_dice_los and dano:
        return "los_y_fibra_danada"
    if cliente_confirmo_los and dano:
        return "los_y_fibra_danada"
    if cliente_dice_los:
        # Declaró LOS en rojo: visita técnica (no seguir a WiFi)
        return "los_confirmada"
    return None


def los_confirmada_en_historial(
    mensaje_cliente: str,
    historial_mensajes: list[Any] | None,
) -> bool:
    """True si el cliente ya confirmó LOS / luz óptica en rojo."""
    if detectar_falla_optica_escalar(mensaje_cliente, historial_mensajes):
        return True
    parts = [_autor_texto(m) for m in (historial_mensajes or [])]
    last = (mensaje_cliente or "").strip()
    if last and (not parts or parts[-1][1].strip() != last):
        parts.append(("cliente", last))
    recent = parts[-14:]
    for i, (autor, texto) in enumerate(recent):
        if autor == "bot" and _bot_menciona_los(texto):
            for autor2, texto2 in recent[i + 1 :]:
                if autor2 == "cliente":
                    if _es_afirmacion(texto2) or "roja" in (texto2 or "").lower():
                        return True
                    break
    last_l = last.lower()
    return any(
        k in last_l
        for k in ("luz los", "los roja", "los en rojo", "tengo los", "led los")
    )


def _extract_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Respuesta vacía")
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        raw = fence.group(1).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("JSON inválido") from None
        data = json.loads(raw[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("JSON raíz debe ser objeto")
    return data


def _historial_texto(mensajes: list[Any], *, limit: int = 16) -> str:
    lines: list[str] = []
    for m in (mensajes or [])[-limit:]:
        autor = getattr(m, "autor", None) or (m.get("autor") if isinstance(m, dict) else "x")
        texto = getattr(m, "texto", None) or (m.get("texto") if isinstance(m, dict) else "")
        rol = "Cliente" if autor == "cliente" else (BOT_DISPLAY_NAME if autor == "bot" else str(autor))
        t = (texto or "").strip()
        if t:
            lines.append(f"{rol}: {t[:400]}")
    return "\n".join(lines) if lines else "(sin historial)"


def _checklist_texto(pasos: list[PasoPlaybook] | list[dict], cubiertos: list[str]) -> str:
    done = set(cubiertos or [])
    rows: list[str] = []
    for p in pasos or []:
        if isinstance(p, PasoPlaybook):
            pid, preg = p.id, p.pregunta
        elif isinstance(p, dict):
            pid = str(p.get("id") or "")
            preg = str(p.get("pregunta") or "")
        else:
            continue
        mark = "x" if pid in done else " "
        rows.append(f"- [{mark}] {pid}: {preg}")
    return "\n".join(rows) if rows else "(sin checklist)"


def _fallback_ask(
    pasos: list[PasoPlaybook] | list[dict],
    cubiertos: list[str],
    mensaje_cliente: str,
    *,
    saltar_wifi: bool = False,
) -> dict[str, str]:
    done = set(cubiertos or [])
    for p in pasos or []:
        if isinstance(p, PasoPlaybook):
            pid, preg = p.id, p.pregunta
        elif isinstance(p, dict):
            pid = str(p.get("id") or "paso")
            preg = str(p.get("pregunta") or "")
        else:
            continue
        if pid in done or not preg:
            continue
        if pid == "so_dispositivo" and detectar_so_movil(mensaje_cliente):
            continue
        if saltar_wifi and (
            "wifi" in pid.lower()
            or any(k in preg.lower() for k in _WIFI_MARKERS)
        ):
            continue
        if _parece_dump_pagos(preg) and not _cliente_pide_pagar(mensaje_cliente):
            continue
        # Si la óptica ya está OK (PON verde), no pedir cable amarillo
        if pid in ("cable_fibra",) and "luces_los" in done:
            continue
        return {
            "accion": "ask",
            "mensaje": preg,
            "paso_cubierto": pid,
            "motivo": "fallback_playbook",
        }
    # Checklist agotado (o solo quedaban pasos WiFi irrelevantes)
    return {
        "accion": "escalate",
        "mensaje": (
            "Con lo que me contaste ya no lo resolvemos a distancia. "
            "¿Querés que te derive con un agente?"
        ),
        "paso_cubierto": "",
        "motivo": "fallback_checklist_agotado",
    }


def _cliente_pide_pagar(texto: str) -> bool:
    t = (texto or "").lower()
    return any(
        k in t
        for k in (
            "como pago",
            "cómo pago",
            "quiero pagar",
            "necesito pagar",
            "para abonar",
            "quiero abonar",
            "para pagar",
            "pagar la",
            "abonar",
            "medio de pago",
            "qr",
            "fiserv",
            "mercado pago",
            "modo",
            "saldo pendiente",
            "me cortaron",
            "sin servicio por",
            "datos de la cuenta",
            "cuenta bancaria",
            "cbu",
            "transferencia",
            "realizar el pago",
            "realizar pago",
            "formas de pago",
            "cómo abonar",
            "como abonar",
            "donde pago",
            "dónde pago",
        )
    )


def _cliente_pide_oficina_virtual(texto: str) -> bool:
    t = (texto or "").lower()
    return any(
        k in t
        for k in (
            "oficina virtual",
            "ofocina virtual",  # typo frecuente
            "oficiana virtual",
            "ov.batan",
            "ov batan",
            "portal de pagos",
            "pagina de pago",
            "página de pago",
            "web de pago",
            "web para pagar",
            "sitio para pagar",
            "tienen una oficina",
            "tienen oficina",
            "hay oficina virtual",
        )
    )


def _cliente_consulta_saldo(texto: str) -> bool:
    t = (texto or "").lower().strip()
    t = re.sub(r"[¡!.,¿?]+", "", t).strip()
    if not t:
        return False
    # Respuestas cortas típicas tras “¿qué necesitás?”
    if t in (
        "saldo",
        "el saldo",
        "mi saldo",
        "deuda",
        "la deuda",
        "mi deuda",
        "el monto",
        "monto",
        "la factura",
        "factura",
    ):
        return True
    if "saldo" in t and any(
        k in t for k in ("quiero", "necesito", "solo", "decime", "pasame", "saber", "consultar", "ver")
    ):
        return True
    return any(
        k in t
        for k in (
            "cuanto me vino",
            "cuánto me vino",
            "cuanto debo",
            "cuánto debo",
            "ultima factura",
            "última factura",
            "ultimo monto",
            "último monto",
            "importe de la factura",
            "monto de la factura",
            "saldo de la factura",
            "saldo de mi",
            "saldo de cuenta",
            "saldo de la cuenta",
            "qué me vino",
            "que me vino",
            "cuanto me cobraron",
            "cuánto me cobraron",
            "cuanto es la factura",
            "cuánto es la factura",
        )
    )


def _pide_cbu_o_adjunto(texto: str) -> bool:
    t = (texto or "").lower()
    return any(
        k in t
        for k in (
            "cbu",
            "cuenta bancaria",
            "transferencia",
            "alias bancario",
            "adjunt",
            "mandame el qr",
            "pasame el qr",
            "enviame el qr",
            "pegame el qr",
        )
    )


def _cierra_consulta_facturacion(texto: str) -> bool:
    """El abonado ya obtuvo el dato (saldo/pago) y cierra la consulta."""
    t = (texto or "").lower().strip()
    if not t:
        return False
    if any(
        k in t
        for k in (
            "no anda",
            "problema",
            "sigue",
            "falla",
            "aument",
            "reclamo",
            "necesito agente",
            "quiero agente",
            # "ya pagué pero…" → aviso de pago, no cierre
            "no se acredita",
            "no figura",
            "no aparece",
            "no reflej",
            "pagué pero",
            "pague pero",
            "ya pagué",
            "ya pague",
            "avise el pago",
            "aviso de pago",
        )
    ):
        return False
    return any(
        k in t
        for k in (
            "gracias",
            "graciass",
            "listo",
            "perfecto",
            "solo queria",
            "solo quería",
            "ya me lo dijiste",
            "no hace falta",
            "eso era todo",
            "nada mas",
            "nada más",
            "muchas gracias",
            "quedó ok",
            "quedo ok",
        )
    )


def _parece_invento_pago(mensaje: str) -> bool:
    """Respuestas que inventan CBU, adjuntos o pasos web inexistentes."""
    t = (mensaje or "").lower()
    return any(
        k in t
        for k in (
            "cbu",
            "insertar cbu",
            "te adjunto",
            "te paso el código qr",
            "te paso el codigo qr",
            "adjunto el código",
            "adjunto el codigo",
            "cuenta bancaria es",
            "número de cbu",
            "numero de cbu",
            "sección de 'pagos'",
            'seccion de "pagos"',
            "generarlo desde nuestra web",
            "ingresá tu número de asociado",
            "ingresa tu numero de asociado",
        )
    )


def _parece_desvio_tecnico(mensaje: str) -> bool:
    t = (mensaje or "").lower()
    return any(
        k in t
        for k in (
            "fibra óptica",
            "fibra optica",
            "cable amarillo",
            "cajita blanca",
            "antena en el techo",
            "línea telefónica",
            "linea telefonica",
            "luces del ont",
            "reiniciá el módem",
            "reinicia el modem",
        )
    )


def _saldo_desde_contexto(contexto_abonado: str) -> str | None:
    import re

    m = re.search(r"deuda_monto:\s*([^\n]+)", contexto_abonado or "", flags=re.I)
    if not m:
        return None
    val = (m.group(1) or "").strip()
    if not val or "sin dato" in val.lower():
        return None
    return val.strip().lstrip("$").strip()


def _facturacion_deterministica(
    mensaje_cliente: str,
    *,
    contexto_abonado: str,
    historial_mensajes: list | None,
) -> dict | None:
    """Respuestas fijas con saldo real; sin inventar CBU/QR adjunto/web."""
    from app.services.eco_voice import (
        PLANTILLA_PAGO_QR,
        mensaje_saldo_padron,
        servicio_cortado_desde_contexto,
        texto_ov_aviso_pago,
    )

    identificado = "modo: identificado" in (contexto_abonado or "")
    saldo = _saldo_desde_contexto(contexto_abonado) if identificado else None
    cortado = servicio_cortado_desde_contexto(contexto_abonado) if identificado else False
    t = (mensaje_cliente or "").lower().strip()

    # Invitado: sin cuenta no hay saldo; pedir DNI (no llamar al LLM).
    if not identificado and (
        _cliente_consulta_saldo(mensaje_cliente)
        or any(k in t for k in ("deuda", "saldo", "factura", "cuanto debo", "cuánto debo"))
    ):
        return {
            "accion": "ask",
            "mensaje": (
                "En modo invitado no veo tu cuenta. "
                "Pasame tu DNI (solo el número) y te digo el saldo de la última factura."
            ),
            "paso_cubierto": "pedir_dni_saldo",
            "motivo": "facturacion_invitado_pide_dni",
        }

    if identificado and _cierra_consulta_facturacion(mensaje_cliente):
        return {
            "accion": "resolved",
            "mensaje": "",  # canal_abonado usa cierre cálido con nombre
            "paso_cubierto": "cierre_facturacion",
            "motivo": "facturacion_cierre_cliente",
            "cierre_calido": True,
        }

    # Ya pagó / no se refleja → link de aviso de pago (sin inventar comprobantes).
    if identificado and any(
        k in t
        for k in (
            "ya pague",
            "ya pagué",
            "ya abone",
            "ya aboné",
            "hoy pague",
            "hoy pagué",
            "la pague",
            "la pagué",
            "lo pague",
            "lo pagué",
            "pague hoy",
            "pagué hoy",
            "avise el pago",
            "avisar el pago",
            "aviso de pago",
            "pague pero",
            "pagué pero",
            "pague y no",
            "pagué y no",
            "sigue figurando",
            "sigue con deuda",
            "sigo con deuda",
            "sigue apareciendo",
            "no se acredita",
            "no se refleja",
            "no se actualiz",
            "sigue la deuda",
            "todavia figura",
            "todavía figura",
        )
    ):
        pref = ""
        if saldo is not None:
            pref = mensaje_saldo_padron(saldo, incluir_ov=False) + "\n"
        cierre = (
            "¿Pudiste cargar el aviso?"
            if cortado
            else "¿Te quedó claro lo de la demora, o querés cargar el aviso igual?"
        )
        return {
            "accion": "ask",
            "mensaje": f"{pref}{texto_ov_aviso_pago(cortado=cortado)}\n{cierre}",
            "paso_cubierto": "aviso_pago_ov",
            "motivo": "facturacion_aviso_pago_ov",
        }

    # Siempre hay oficina virtual: nunca dejar que el LLM la niegue.
    if identificado and _cliente_pide_oficina_virtual(mensaje_cliente):
        pref = ""
        if saldo is not None:
            pref = mensaje_saldo_padron(saldo, incluir_ov=False) + "\n"
        return {
            "accion": "ask",
            "mensaje": (
                f"{pref}Sí: la oficina virtual está acá.\n"
                f"{PLANTILLA_PAGO_QR}"
            ),
            "paso_cubierto": "guia_oficina_virtual",
            "motivo": "facturacion_oficina_virtual",
        }

    if identificado and saldo is not None and _cliente_consulta_saldo(mensaje_cliente):
        web = any(
            k in t
            for k in (
                "web",
                "pagina",
                "página",
                "link",
                "sitio",
                "ov.batan",
                "oficina virtual",
                "donde pago",
                "dónde pago",
                "para abonar",
                "abonar",
            )
        )
        if web or _cliente_pide_pagar(mensaje_cliente):
            return {
                "accion": "ask",
                "mensaje": (
                    f"{mensaje_saldo_padron(saldo, incluir_ov=False)}\n{PLANTILLA_PAGO_QR}"
                ),
                "paso_cubierto": "informar_saldo_y_pago",
                "motivo": "facturacion_saldo_y_web_pago",
            }
        return {
            "accion": "ask",
            "mensaje": mensaje_saldo_padron(saldo),
            "paso_cubierto": "informar_saldo",
            "motivo": "facturacion_saldo_real",
        }

    hist_txt = " ".join(
        _autor_texto(m)[1] for m in (historial_mensajes or [])[-8:]
    ).lower()
    oferta_pago_previa = any(
        k in hist_txt
        for k in (
            "qr",
            "fiserv",
            "pagar",
            "pago",
            "abonar",
            "mercado pago",
            "oficina virtual",
            "ov.batan",
            "cómo podés",
            "como podes",
            "realizar el pago",
        )
    )

    if identificado and (
        _pide_cbu_o_adjunto(mensaje_cliente)
        or (
            t in ("ambas", "los dos", "las dos", "si", "sí")
            and oferta_pago_previa
            and any(k in hist_txt for k in ("cbu", "bancaria", "qr", "cuenta"))
        )
    ):
        extra = ""
        if saldo is not None:
            extra = mensaje_saldo_padron(saldo, incluir_ov=False) + "\n"
        return {
            "accion": "ask",
            "mensaje": (
                f"{extra}Por este chat no te puedo pasar CBU ni adjuntar un QR.\n"
                f"{PLANTILLA_PAGO_QR}"
            ),
            "paso_cubierto": "guia_pago_fiserv",
            "motivo": "facturacion_sin_invento_cbu",
        }

    if identificado and (
        _cliente_pide_pagar(mensaje_cliente)
        or (t in ("ambas", "si", "sí", "dale", "ok", "dale si") and oferta_pago_previa)
    ):
        pref = ""
        if saldo is not None:
            pref = mensaje_saldo_padron(saldo, incluir_ov=False) + "\n"
        return {
            "accion": "ask",
            "mensaje": f"{pref}{PLANTILLA_PAGO_QR}",
            "paso_cubierto": "guia_pago_fiserv",
            "motivo": "facturacion_pago_plantilla",
        }

    return None


def _parece_niega_oficina_virtual(mensaje: str) -> bool:
    t = (mensaje or "").lower()
    if "oficina virtual" not in t and "ov.batan" not in t:
        return False
    return any(
        k in t
        for k in (
            "no contamos",
            "no tenemos",
            "no hay",
            "por el momento",
            "no disponemos",
            "todavía no",
            "todavia no",
        )
    )


def _parece_dump_pagos(mensaje: str) -> bool:
    """Detecta respuestas tipo manual (QR + varios medios) en vez de indagar."""
    t = (mensaje or "").lower()
    hits = sum(
        1
        for k in (
            "fiserv",
            "mercado pago",
            "modo",
            "qr",
            "copia de factura",
            "identific",
            "portal",
        )
        if k in t
    )
    return hits >= 3 or (hits >= 2 and len(t) > 280)


def _ofrece_handoff_prematuro(mensaje: str) -> bool:
    """True si el mensaje invita a asesor/llamada/ticket en vez de seguir N1."""
    t = (mensaje or "").lower()
    return any(
        k in t
        for k in (
            "asesor",
            "te contacte",
            "te contactemos",
            "preferís que te llam",
            "preferis que te llam",
            "que te llamen",
            "te llame",
            "área de cuentas",
            "area de cuentas",
            "abra un ticket",
            "abro un ticket",
            "generé el ticket",
            "genere el ticket",
            "te derive",
            "un agente te",
        )
    )


def _pregunta_pago_fuera_de_lugar(mensaje: str, mensaje_cliente: str) -> bool:
    """Preguntas de medio/fecha de pago cuando el cliente no dijo que pagó."""
    if _cliente_pide_pagar(mensaje_cliente):
        return False
    t = (mensaje or "").lower()
    return any(
        k in t
        for k in (
            "medio de pago",
            "fecha realizó",
            "fecha realizo",
            "fecha del pago",
            "qué fecha",
            "que fecha",
            "realizó el movimiento",
            "realizo el movimiento",
        )
    )


def diagnosticar_turno(
    *,
    intencion: str,
    checklist: list[PasoPlaybook] | list[dict],
    historial_mensajes: list[Any],
    mensaje_cliente: str,
    turnos_diagnostico: int,
    pasos_cubiertos: list[str],
    kb_fragmento: str = "",
    forzar_agente: bool = False,
    contexto_abonado: str = "",
) -> dict[str, str]:
    """Pide a la IA el próximo acto de diagnóstico. Fallback = siguiente paso del playbook."""
    if forzar_agente:
        return {
            "accion": "escalate",
            "mensaje": (
                "Dale, te derivo con un agente y le paso el historial. "
                "Quedate en este chat."
            ),
            "paso_cubierto": "",
            "motivo": "pedido_humano",
        }

    motivo_optico = None
    linea_ya_ok = "linea_ok" in (contexto_abonado or "") or "NO pedir reinicio de ONT" in (
        contexto_abonado or ""
    )
    # Si PPPoE/triage ya dijo línea OK, no correr heurísticas ópticas ni preguntar PON.
    aplica_optica_turno = es_intencion_optica(intencion) and not linea_ya_ok

    if aplica_optica_turno:
        motivo_optico = detectar_falla_optica_escalar(mensaje_cliente, historial_mensajes)
    if motivo_optico:
        if motivo_optico == "fibra_danada" and "los" not in (mensaje_cliente or "").lower():
            msg_optico = (
                "Con daño visible en el cable de fibra ya no lo resolvemos a distancia: "
                "hace falta una visita técnica. Te derivo con un agente para coordinarla."
            )
        else:
            msg_optico = (
                "La luz LOS en rojo indica que la fibra no está llegando bien a la cajita. "
                "Eso ya no lo resolvemos reiniciando: hace falta una visita técnica. "
                "Te derivo con un agente para coordinarla."
            )
        return {
            "accion": "escalate",
            "mensaje": msg_optico,
            "paso_cubierto": "",
            "motivo": motivo_optico,
        }

    # PON verde fijo = enlace óptico OK → no preguntar cable amarillo
    if aplica_optica_turno and detectar_enlace_optico_ok(
        mensaje_cliente, historial_mensajes
    ):
        return {
            "accion": "ask",
            "mensaje": (
                "Perfecto: con la PON en verde fijo el enlace de fibra está bien. "
                "¿Ya te anda internet o sigue sin servicio?"
            ),
            "paso_cubierto": "luces_los",
            "motivo": "pon_verde_enlace_ok",
        }

    from app.services.eco_voice import (
        HISTORIAL_CHAT_MAX_MSGS,
        TEMPERATURE_N1,
        historial_canal_a_mensajes_chat,
        system_prompt_eco_n1,
    )
    from app.services.prompt_safety import (
        looks_like_jailbreak,
        sanitize_user_text,
        strip_instruction_phrases,
        with_anti_injection,
        wrap_untrusted,
    )

    # Inyección / jailbreak: no dejar que el LLM elija escalate/resolved
    if looks_like_jailbreak(mensaje_cliente):
        fb = _fallback_ask(checklist, pasos_cubiertos, mensaje_cliente)
        return {**fb, "motivo": "bloqueado_prompt_injection"}

    checklist_txt = _checklist_texto(checklist, pasos_cubiertos)
    kb = strip_instruction_phrases((kb_fragmento or "").strip()[:800])
    kb_block = f"\nConocimiento útil (opcional):\n{wrap_untrusted('KB', kb, max_chars=800)}\n" if kb else ""
    turnos = max(0, int(turnos_diagnostico or 0))
    msg_safe = sanitize_user_text(mensaje_cliente)
    es_facturacion = intencion_es_facturacion(intencion)
    es_tv_sensa = (intencion or "").strip() == "tv_sensa"
    es_movil = (intencion or "").strip() in ("movil", "movil_datos", "movil_llamadas")
    aplica_optica = aplica_optica_turno
    so_movil = detectar_so_movil(mensaje_cliente, historial_mensajes) if es_movil else None
    if es_movil:
        pasos_cubiertos = _enriquecer_pasos_movil(
            pasos_cubiertos, so_movil, mensaje_cliente, historial_mensajes
        )
        if pack_acreditado_sin_datos(mensaje_cliente, historial_mensajes):
            return {
                "accion": "escalate",
                "mensaje": _MSG_PACK_ACREDITADO,
                "paso_cubierto": "derivar_datos",
                "motivo": "pack_acreditado_sin_datos",
            }

    if es_facturacion:
        det = _facturacion_deterministica(
            mensaje_cliente,
            contexto_abonado=contexto_abonado,
            historial_mensajes=historial_mensajes,
        )
        if det:
            return det

    reglas_facturacion = ""
    if es_facturacion:
        reglas_facturacion = (
            "\nReglas EXTRA — facturación/cuenta (prioridad alta):\n"
            "- Primero INDAGÁ el problema real con UNA pregunta. No sueltes un manual de pagos.\n"
            "- Si habla de aumento, tarifa más cara o factura distinta: preguntá mes, montos "
            "(antes vs ahora) o si hubo cambio de plan/servicios. NUNCA preguntes medio de pago "
            "ni fecha de un pago salvo que diga que pagó y no figura.\n"
            "- Si no reconoce un cobro: pedí mes/importe/concepto; no asumas que es un pago fallido.\n"
            "- Solo explicá cómo pagar si pide pagar, QR, oficina virtual, saldo a abonar, o tiene corte.\n"
            "- SIEMPRE existe la oficina virtual: https://ov.batan.coop y pago con DNI "
            "https://ov.batan.coop/#/pagar — NUNCA digas que no hay oficina virtual.\n"
            "- Al explicar pagos, incluí esos links + QR Fiserv de la factura (Mercado Pago/MODO).\n"
            "- NUNCA inventes CBU, alias, cuenta bancaria ni adjuntos de QR.\n"
            "- Si CONTEXTO_ABONADO trae deuda_monto, usá SOLO ese valor; no inventes montos.\n"
            "- deuda_monto está en pesos argentinos (ARS). NUNCA digas dólares ni USD.\n"
            "- En consulta de saldo/pago NO preguntes por fibra, antena, módem ni tipo de conexión.\n"
            "- En modo invitado (sin cuenta): pedí DNI/N.º de socio; no inventes saldos.\n"
            "- Si el cliente agradece y dice que solo quería el saldo: accion=resolved.\n"
            "- No ofrezcas asesor/ticket hasta indagar al menos "
            f"{MIN_TURNOS_ANTES_ESCALAR} turnos, salvo que pida agente.\n"
            "- escalate cuando ya pediste el detalle y hace falta sistema interno, o si pide agente.\n"
        )

    reglas_tv = ""
    if es_tv_sensa:
        reglas_tv = (
            "\nReglas EXTRA — TV OTT Sensa (prioridad alta):\n"
            "- Sensa corre sobre internet del dispositivo. Si NO hay internet → enfocá "
            "conectividad; si HAY internet y navega, el problema es de la app/cuenta Sensa.\n"
            "- NUNCA menciones luz LOS, PON, ONT, cable amarillo, cajita blanca ni visita "
            "por fibra. Eso es otro servicio.\n"
            "- Error de usuario/cuenta/credenciales: pedí confirmar usuario/contraseña y "
            "dispositivo; no inventes si el servicio está habilitado en CRM. "
            "Si ya confirmó credenciales y sigue el error → escalate (agente con acceso interno).\n"
            "- Al escalate por cuenta: mencioná dispositivo + mensaje de error; no digas "
            "falla de fibra ni visita técnica de obras.\n"
            "- Buffering/calidad: WiFi/velocidad en ese equipo; no inventes potencias ONT.\n"
        )

    reglas_movil = ""
    if es_movil:
        so_txt = so_movil or "desconocido"
        reglas_movil = (
            "\nReglas EXTRA — móvil IMOWI (prioridad alta):\n"
            f"- Sistema operativo YA declarado por el abonado: {so_txt}.\n"
            "- Si dijo Android / Moto / Samsung / Xiaomi / etc.: NUNCA des pasos de iPhone "
            "(Datos celulares, Punto de acceso, eSIM iPhone, modelo 11). "
            "Usá solo APN Android: Nombre imowi / APN apn1.catel.org.ar.\n"
            "- Si dijo iPhone/iOS: NUNCA des pasos de Android (Ajustes > Redes/Conexiones > APN).\n"
            "- Si el SO aún es desconocido, preguntá UNA sola vez Android o iPhone; "
            "después no vuelvas a preguntar.\n"
            "- Si el abonado corrige («no es iPhone, es Android»), pedí perdón en una frase "
            "y continuá SOLO con el SO correcto.\n"
            "- NUNCA pidas cambiar el tipo de red a 3G/2G. No inventes pasos de iPhone.\n"
            "- Si el APN del SO correcto ya está OK y sigue sin datos: preguntá si cargó "
            "un pack/bono (sistema OK) y no le aparecen. Eso es escalate (sistema/línea), "
            "no más toqueteo del celular.\n"
            "- Si reitera «siguen sin andar los datos», NO reinicies el cuestionario "
            "(avión/señal/modelo). Seguí desde el último paso cubierto o derivá.\n"
            "- No inventes cobertura de zona ni estado de la línea en el core.\n"
        )

    system = with_anti_injection(
        system_prompt_eco_n1(
            intencion=intencion,
            turnos=turnos,
            min_turnos_antes_escalar=MIN_TURNOS_ANTES_ESCALAR,
            reglas_extra=reglas_facturacion + reglas_tv + reglas_movil,
            contexto_abonado=contexto_abonado,
        )
    )

    chat_hist = historial_canal_a_mensajes_chat(
        historial_mensajes,
        max_msgs=HISTORIAL_CHAT_MAX_MSGS,
    )
    so_line = f"- SO móvil detectado: {so_movil}\n" if so_movil else ""
    # Instrucción estructurada al final (el historial ya trae el último mensaje del cliente)
    task = (
        f"Estado del diagnóstico (interno):\n"
        f"- Intención: {sanitize_user_text(intencion, max_chars=80)}\n"
        f"- Turnos de diagnóstico ya hechos: {turnos}\n"
        f"- Pasos ya cubiertos: {', '.join(pasos_cubiertos) or '(ninguno)'}\n"
        f"{so_line}"
        f"- Checklist guía:\n{checklist_txt}\n"
        f"{kb_block}"
        f"Último mensaje del cliente (referencia):\n"
        f"{wrap_untrusted('ULTIMO_MENSAJE_CLIENTE', msg_safe)}\n"
        "Decidí el próximo acto y respondé SOLO el JSON pedido."
    )

    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    messages.extend(chat_hist)
    messages.append({"role": "user", "content": task})

    try:
        from app.llm import chat_completion

        try:
            raw = chat_completion(
                messages,
                temperature=TEMPERATURE_N1,
                json_mode=True,
            )
        except Exception:
            raw = chat_completion(
                messages,
                temperature=TEMPERATURE_N1,
                json_mode=False,
            )
        data = _extract_json(raw)
        accion = str(data.get("accion") or "ask").strip().lower()
        if accion not in ("ask", "resolved", "escalate"):
            accion = "ask"
        mensaje = str(data.get("mensaje") or "").strip()
        paso = str(data.get("paso_cubierto") or "").strip()
        motivo = str(data.get("motivo") or "ia").strip()[:200]
        forzar_optico = bool(
            aplica_optica
            and (
                detectar_falla_optica_escalar(mensaje_cliente, historial_mensajes)
                or (
                    los_confirmada_en_historial(mensaje_cliente, historial_mensajes)
                    and any(k in mensaje.lower() for k in _WIFI_MARKERS)
                )
            )
        )

        # Si la IA pregunta WiFi con LOS ya confirmada → forzar escalate óptico
        if (
            aplica_optica
            and accion == "ask"
            and los_confirmada_en_historial(mensaje_cliente, historial_mensajes)
            and any(k in mensaje.lower() for k in _WIFI_MARKERS)
        ):
            accion = "escalate"
            motivo = "bloqueado_wifi_post_los"
            mensaje = (
                "La luz LOS en rojo indica un problema de fibra/señal óptica; "
                "no se arregla mirando el WiFi. Te derivo para coordinar una visita técnica."
            )

        # Guardrails
        if (
            accion == "escalate"
            and turnos < MIN_TURNOS_ANTES_ESCALAR
            and not forzar_agente
            and not forzar_optico
            and motivo not in (
                "fibra_danada",
                "los_con_chequeo_fibra",
                "los_y_fibra_danada",
                "los_confirmada",
                "bloqueado_wifi_post_los",
                "pack_acreditado_sin_datos",
            )
        ):
            accion = "ask"
            motivo = "bloqueado_min_turnos"
            if not mensaje or "?" not in mensaje:
                fb = _fallback_ask(checklist, pasos_cubiertos, mensaje_cliente)
                mensaje = fb["mensaje"]
                paso = fb.get("paso_cubierto") or paso

        # Escalate por IA solo si el checklist está casi agotado (evita inyección → ticket)
        if (
            accion == "escalate"
            and not forzar_agente
            and not forzar_optico
            and motivo not in (
                "fibra_danada",
                "los_con_chequeo_fibra",
                "los_y_fibra_danada",
                "los_confirmada",
                "bloqueado_wifi_post_los",
                "pack_acreditado_sin_datos",
            )
        ):
            ids = []
            for p in checklist or []:
                pid = p.get("id") if isinstance(p, dict) else getattr(p, "id", "")
                if pid:
                    ids.append(str(pid))
            cubiertos = {str(x) for x in (pasos_cubiertos or [])}
            restantes = [i for i in ids if i not in cubiertos]
            if len(restantes) > 1 and turnos < max(MIN_TURNOS_ANTES_ESCALAR + 1, 5):
                accion = "ask"
                motivo = "bloqueado_escalate_sin_agotamiento"
                if not mensaje or "?" not in mensaje:
                    fb = _fallback_ask(checklist, pasos_cubiertos, mensaje_cliente)
                    mensaje = fb["mensaje"]
                    paso = fb.get("paso_cubierto") or paso

        # Re-chequeo óptico por si la IA ignoró evidencia (solo FTTH/internet)
        if aplica_optica:
            opt2 = detectar_falla_optica_escalar(mensaje_cliente, historial_mensajes)
            if opt2 and accion != "escalate":
                accion = "escalate"
                motivo = opt2
                mensaje = (
                    "La luz LOS en rojo indica que la fibra no está llegando bien a la cajita. "
                    "Eso ya no lo resolvemos reiniciando: hace falta una visita técnica. "
                    "Te derivo con un agente para coordinarla."
                )

        # Bloquear diagnóstico óptico inventado fuera de internet/FTTH (p.ej. Sensa)
        if not aplica_optica and (
            _motivo_es_optico(motivo)
            or _parece_diagnostico_optica_fuera_de_lugar(mensaje)
        ):
            if accion == "escalate" or _motivo_es_optico(motivo):
                accion = "escalate"
                motivo = "bloqueado_optica_fuera_de_intencion"
                if es_tv_sensa:
                    mensaje = (
                        "Con ese error de usuario/cuenta de Sensa hace falta revisarlo "
                        "adentro. Te derivo con un agente; le paso el dispositivo y el "
                        "mensaje que te aparece."
                    )
                else:
                    mensaje = (
                        "Con lo que me contaste hace falta un agente con acceso interno. "
                        "Te derivo y le paso el historial."
                    )
            else:
                motivo = "bloqueado_optica_fuera_de_intencion"
                fb = _fallback_ask(checklist, pasos_cubiertos, mensaje_cliente)
                mensaje = fb["mensaje"]
                paso = fb.get("paso_cubierto") or paso
                accion = "ask"

        # Línea/PPPoE OK: la IA no debe volver a preguntar ONT/PON/LOS
        if (
            linea_ya_ok
            and accion == "ask"
            and _parece_diagnostico_optica_fuera_de_lugar(mensaje)
        ):
            accion = "ask"
            motivo = "bloqueado_ont_post_linea_ok"
            mensaje = (
                "Como la línea ya está OK, sigamos con el Wi‑Fi. "
                "¿Les pasa a todos los equipos o solo a uno?"
            )
            paso = "otros_dispositivos_wifi"

        if accion == "resolved":
            from app.domain.flujos_abonado import confirma_contacto_sin_servicio

            t = (mensaje_cliente or "").lower()
            if confirma_contacto_sin_servicio(mensaje_cliente):
                accion = "ask"
                motivo = "bloqueado_resolved_solo_contacto"
                mensaje = (
                    "Buenísimo que te hayan contestado. "
                    "¿Ya te anda el servicio o seguís con el mismo problema?"
                )
                paso = "confirmar_servicio_post_contacto"
            elif any(
                k in t
                for k in (
                    "no anda", "no funciona", "sigue", "problema", "falla",
                    "sin internet", "no me", "quisiera", "consultar",
                )
            ):
                accion = "ask"
                motivo = "bloqueado_resolved_con_sintoma"
                if not mensaje or "¿" not in mensaje:
                    fb = _fallback_ask(checklist, pasos_cubiertos, mensaje_cliente)
                    mensaje = fb["mensaje"]
                    paso = fb.get("paso_cubierto") or paso

        # Si la IA pregunta cable amarillo con PON ya verde → saltar a WiFi/cable
        if (
            aplica_optica
            and accion == "ask"
            and any(
                k in mensaje.lower()
                for k in ("cable amarillo", "dobleces", "daños visibles", "danos visibles")
            )
            and (
                "luces_los" in {str(x) for x in (pasos_cubiertos or [])}
                or detectar_enlace_optico_ok(mensaje_cliente, historial_mensajes)
            )
        ):
            accion = "ask"
            motivo = "bloqueado_cable_post_pon_verde"
            mensaje = (
                "Con la PON en verde el enlace de fibra está bien. "
                "¿El problema es solo WiFi o también falla por cable al router?"
            )
            paso = "wifi_vs_cable_ftth"

        # Facturación: no soltar manual de pagos si el cliente no pidió pagar
        if (
            es_facturacion
            and accion == "ask"
            and _parece_dump_pagos(mensaje)
            and not _cliente_pide_pagar(mensaje_cliente)
            and not _cliente_pide_pagar(
                " ".join(_autor_texto(m)[1] for m in (historial_mensajes or [])[-6:])
            )
        ):
            mensaje = (
                "Dale, contame un poco más: ¿es por un aumento respecto al mes anterior, "
                "un cobro que no reconocés, o necesitás copia/saldo o cómo pagar?"
            )
            paso = "triaje_motivo"
            motivo = "bloqueado_dump_pagos"

        # Facturación: bloquear inventos (CBU, adjunto QR falso, web inventada) y desvío técnico
        if es_facturacion and accion in ("ask", "resolved") and (
            _parece_invento_pago(mensaje)
            or _parece_desvio_tecnico(mensaje)
            or _parece_niega_oficina_virtual(mensaje)
        ):
            saldo = _saldo_desde_contexto(contexto_abonado)
            from app.services.eco_voice import PLANTILLA_PAGO_QR, mensaje_saldo_padron

            pref = f"{mensaje_saldo_padron(saldo, incluir_ov=False)}\n" if saldo else ""
            if (
                _cliente_pide_pagar(mensaje_cliente)
                or _pide_cbu_o_adjunto(mensaje_cliente)
                or _cliente_pide_oficina_virtual(mensaje_cliente)
                or _parece_niega_oficina_virtual(mensaje)
            ):
                mensaje = (
                    f"{pref}Sí, tenemos oficina virtual. "
                    f"Por este chat no te paso CBU ni adjunto QR.\n"
                    f"{PLANTILLA_PAGO_QR}"
                )
                paso = "guia_pago_fiserv"
            elif saldo and _cliente_consulta_saldo(mensaje_cliente):
                mensaje = mensaje_saldo_padron(saldo)
                paso = "informar_saldo"
            else:
                mensaje = (
                    f"{pref}Sí tenemos oficina virtual para pagos y gestiones.\n"
                    f"{PLANTILLA_PAGO_QR}"
                )
                paso = "guia_oficina_virtual"
            motivo = "bloqueado_invento_pago_o_desvio"
            if accion == "resolved":
                accion = "ask"

        # No ofrecer asesor/llamada antes del mínimo de turnos N1
        if (
            accion == "ask"
            and turnos < MIN_TURNOS_ANTES_ESCALAR
            and _ofrece_handoff_prematuro(mensaje)
            and not forzar_agente
        ):
            if es_facturacion:
                if "modo: identificado" in (contexto_abonado or ""):
                    from app.services.eco_voice import (
                        mensaje_saldo_padron,
                        servicio_cortado_desde_contexto,
                        texto_ov_aviso_pago,
                    )

                    saldo = _saldo_desde_contexto(contexto_abonado)
                    pref = ""
                    if saldo is not None:
                        pref = mensaje_saldo_padron(saldo, incluir_ov=False) + "\n"
                    cortado = servicio_cortado_desde_contexto(contexto_abonado)
                    mensaje = (
                        f"{pref}{texto_ov_aviso_pago(cortado=cortado)}\n"
                        "¿Pudiste cargar el aviso?"
                    )
                    paso = "aviso_pago_ov"
                else:
                    mensaje = (
                        "Para confirmar si hubo ajuste de tarifa o cambio de plan necesito "
                        "mirar tu cuenta. ¿Me pasás el DNI del titular o N.º de socio?"
                    )
                    paso = "identificar_cuenta"
            else:
                fb = _fallback_ask(checklist, pasos_cubiertos, mensaje_cliente)
                mensaje = fb["mensaje"]
                paso = fb.get("paso_cubierto") or paso
            motivo = "bloqueado_handoff_prematuro"

        # No preguntar medio/fecha de pago si no dijo que pagó
        if accion == "ask" and _pregunta_pago_fuera_de_lugar(mensaje, mensaje_cliente):
            if es_facturacion:
                if "modo: identificado" in (contexto_abonado or ""):
                    from app.services.eco_voice import (
                        servicio_cortado_desde_contexto,
                        texto_ov_aviso_pago,
                    )

                    cortado = servicio_cortado_desde_contexto(contexto_abonado)
                    mensaje = (
                        f"{texto_ov_aviso_pago(cortado=cortado)}\n"
                        "¿Pudiste cargar el aviso?"
                    )
                    paso = "aviso_pago_ov"
                else:
                    mensaje = (
                        "Perfecto. Para ver si hubo un ajuste necesito ubicarte: "
                        "¿me pasás DNI del titular o N.º de socio?"
                    )
                    paso = "identificar_cuenta"
            else:
                fb = _fallback_ask(checklist, pasos_cubiertos, mensaje_cliente)
                mensaje = fb["mensaje"]
                paso = fb.get("paso_cubierto") or paso
            motivo = "bloqueado_pregunta_pago"

        if not mensaje:
            fb = _fallback_ask(checklist, pasos_cubiertos, mensaje_cliente)
            return {**fb, "motivo": f"ia_sin_mensaje:{motivo}"}

        # Una sola pregunta
        if accion == "ask" and mensaje.count("?") > 1:
            # quedarse con hasta la primera pregunta
            idx = mensaje.find("?")
            mensaje = mensaje[: idx + 1].strip()
            if len(mensaje) < 8:
                fb = _fallback_ask(checklist, pasos_cubiertos, mensaje_cliente)
                mensaje = fb["mensaje"]

        if es_movil:
            g = aplicar_guardrails_movil(
                mensaje=mensaje,
                mensaje_cliente=mensaje_cliente,
                historial_mensajes=historial_mensajes,
                pasos_cubiertos=pasos_cubiertos,
                accion=accion,
                so=so_movil,
            )
            accion = g["accion"] or accion
            mensaje = g["mensaje"] or mensaje
            if g.get("motivo"):
                motivo = g["motivo"]
            if g.get("paso_cubierto"):
                paso = g["paso_cubierto"]

        if len(mensaje) > 420:
            mensaje = mensaje[:417] + "…"

        return {
            "accion": accion,
            "mensaje": mensaje,
            "paso_cubierto": paso,
            "motivo": motivo,
        }
    except Exception:
        logger.warning("diagnostico_n1 IA falló; fallback playbook", exc_info=True)
        return _fallback_ask(checklist, pasos_cubiertos, mensaje_cliente)
