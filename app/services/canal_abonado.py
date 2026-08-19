"""Motor N1 del canal abonado (WhatsApp / Telegram / web / app / simulador) + escalamiento N2."""

from __future__ import annotations

import logging
import re
import time

from sqlalchemy.orm import Session

from app.config import BOT_DISPLAY_NAME_SHORT
from app.domain.canales import enviar_externo as _enviar_externo
from app.domain.flujos_abonado import (
    ajustar_intencion_a_padron,
    clasificar_intencion,
    contiene_sintoma_canal,
    declara_solo_movil_sin_fijo,
    detecta_frustracion,
    detectar_temas_duales,
    es_escape_agente,
    es_paso_derivacion,
    es_saludo_corto,
    es_saludo_solo,
    indica_resuelto,
    intencion_desde_tema,
    intencion_es_facturacion,
    intencion_es_internet,
    misma_queja,
    niega_producto_internet,
    parece_consulta_nueva,
    parse_menu_servicio,
    parse_menu_tipo_consulta,
    pide_humano,
    pide_humano_en_flujo_activo,
    refinar_intencion_internet,
    registrar_queja,
    resolver_prioridad_tema,
    respuesta_paso_ok,
    resumen_handoff,
    tag_para_intencion,
    texto_menu_consulta,
    texto_menu_tipo_consulta,
    texto_sin_internet_contratado,
    tiene_internet_fijo,
)
from app.estate import canal_repo as crepo
from app.estate.models import Abonado, ConversacionCanal
from app.services import ticket_bridge
from app.services.diagnostico_n1 import diagnosticar_turno, es_intencion_diagnostico
from app.services.eco_voice import mensaje_saldo_padron
from app.services.encuesta_satisfaccion import (
    ORIGEN_BOT,
    enviar_encuesta_cierre,
    intentar_capturar_voto,
)
from app.services.platform_settings import playbooks_as_pasos, resolve_canal_diagnostico_ia
from app.services.telegram_client import enviar_texto as enviar_texto_tg
from app.services.whatsapp_client import enviar_texto as enviar_texto_wa

logger = logging.getLogger("operations_hub")

# Reexport compat: plantilla de pagos Fiserv (único origen: eco_voice).

_INTENCIONES_PPPOE = frozenset({
    "internet",
    "internet_ftth",
    "internet_adsl",
    "internet_radio",
    "internet_lento",
    "internet_intermitente",
    "wifi",
})


def _cliente_indica_solo_wifi(texto: str) -> bool:
    """True si el abonado acota el problema a Wi‑Fi (no a toda la línea)."""
    t = (texto or "").lower().strip()
    if not t:
        return False
    if any(
        k in t
        for k in (
            "solo wifi",
            "solo el wifi",
            "solo wi-fi",
            "solo wi fi",
            "solo falla el wifi",
            "solo falla wifi",
            "falla solo el wifi",
            "falla solo wifi",
            "nada mas el wifi",
            "nada más el wifi",
            "unicamente wifi",
            "únicamente wifi",
            "solo inalambr",
            "solo inalámbr",
            "el wifi nomas",
            "el wifi nomás",
            "wifi nomas",
            "wifi nomás",
        )
    ):
        return True
    # "solo falla el wifi" variants already covered; "falla el wifi" alone is weaker
    if "wifi" in t or "wi-fi" in t or "wi fi" in t:
        if any(k in t for k in ("solo", "nomas", "nomás", "unicamente", "únicamente")):
            return True
    return False


def _cliente_cable_ok(texto: str) -> bool:
    """Por cable anda / TV por cable funciona."""
    t = (texto or "").lower()
    if not t:
        return False
    # Word-boundary: evita falso positivo «impecable» ⊃ «cable»
    if not re.search(r"\bcable\b", t):
        return False
    if any(
        k in t
        for k in (
            "por cable funciona",
            "cable funciona",
            "cable anda",
            "anda por cable",
            "funciona por cable",
            "con cable anda",
            "con cable funciona",
            "cable y funciona",
            "conectado por cable y funciona",
        )
    ):
        return True
    if any(k in t for k in ("bien", "anda", "funciona", "ok", "perfecto")):
        if not any(k in t for k in ("no ", "mal", "falla", "sin ")):
            return True
    return False


def _limpiar_ctx_outage(ctx: dict, *, preservar_resuelto_avisado: bool = False) -> None:
    avisado = ctx.get("outage_resuelto_avisado")
    for k in (
        "outage_id",
        "outage_nas",
        "outage_informado",
        "outage_interceptado",
        "outage_ack",
        "outage_resuelto_avisado",
    ):
        ctx.pop(k, None)
    if preservar_resuelto_avisado and avisado:
        ctx["outage_resuelto_avisado"] = avisado


def _talvez_respuesta_outage(
    db: Session,
    org_id: str,
    conv: ConversacionCanal,
    abonado: Abonado | None,
    ctx: dict,
    *,
    canal: str,
    texto: str = "",
) -> dict | None:
    """Si el NAS del abonado tiene incidente masivo activo, responde canned y no crea ticket."""
    if abonado is None:
        return None
    intent = str(ctx.get("intencion") or "").strip()
    from app.estate import repository as repo
    from app.services.outages import (
        buscar_outage_para_abonado,
        cliente_indica_problema_individual,
        es_ack_outage,
        intencion_bloquea_outage,
        mensaje_ack_outage,
        mensaje_ack_outage_corto,
        mensaje_para_conversacion,
        mensaje_resolucion_outage,
        pide_estado_outage,
    )

    if intencion_bloquea_outage(intent):
        return None

    cached_id = str(ctx.get("outage_id") or "").strip()
    was_informed = bool(ctx.get("outage_informado"))

    try:
        outage, nas = buscar_outage_para_abonado(db, org_id, abonado, ctx)
    except Exception:
        logger.exception("Error buscando outage masivo")
        return None

    def _pack(msg: str, **extra):
        crepo.set_contexto(conv, ctx)
        db.commit()
        _enviar_respuesta(db, org_id, conv, msg, enviar_externo=_enviar_externo(canal))
        payload = {
            "ok": True,
            "modo": "bot",
            "conversacion_id": conv.id,
            "respuesta": msg,
            "estado": conv.estado,
            "abonado": crepo.abonado_to_dict(abonado),
            "intencion": intent or None,
        }
        payload.update(extra)
        return payload

    if not outage:
        # Tras avisar resolución: "sí gracias" / ok → cerrar hilo (evita deuda/N1 al volver)
        if ctx.get("outage_resuelto_avisado") and es_ack_outage(texto):
            from app.services.outages import mensaje_cierre_post_resolucion

            _reset_ctx_diagnostico(ctx)
            _limpiar_ctx_outage(ctx)
            crepo.set_contexto(conv, ctx)
            db.commit()
            return _cerrar_consulta_resuelta(
                db,
                org_id,
                conv,
                canal=canal,
                mensaje=mensaje_cierre_post_resolucion(
                    _primer_nombre_cliente(abonado)
                ),
                nota_ticket="[Outage] Abonado confirmó post-resolución de incidente masivo.",
            )

        # Incidente que teníamos cacheado fue resuelto → avisar una vez
        if cached_id and was_informed and not ctx.get("outage_resuelto_avisado"):
            prev = repo.get_network_outage(db, org_id, cached_id)
            if prev is not None and prev.estado == "resuelto":
                msg = mensaje_resolucion_outage(prev)
                _reset_ctx_diagnostico(ctx)
                _limpiar_ctx_outage(ctx)
                ctx["outage_resuelto_avisado"] = prev.id
                if hasattr(conv, "servicio_detectado"):
                    conv.servicio_detectado = ""
                return _pack(msg, outage_resuelto=prev.id)
        if cached_id or was_informed:
            _limpiar_ctx_outage(ctx)
            crepo.set_contexto(conv, ctx)
            db.commit()
        return None

    # Falla aparentemente individual → diagnóstico N1 (no insistir con plantilla masiva)
    if ctx.get("outage_individual") or cliente_indica_problema_individual(texto):
        if cliente_indica_problema_individual(texto):
            ctx["outage_individual"] = True
        crepo.set_contexto(conv, ctx)
        db.commit()
        return None

    ya = was_informed and str(cached_id or "") == outage.id
    ctx["outage_id"] = outage.id
    ctx["outage_nas"] = nas or outage.nas_shortname
    ctx["outage_interceptado"] = True
    ctx.pop("outage_resuelto_avisado", None)

    # Primer aviso
    if not ya:
        msg = mensaje_para_conversacion(outage, ya_informado=False)
        ctx["outage_informado"] = True
        return _pack(
            msg,
            outage_id=outage.id,
            outage_nas=nas or outage.nas_shortname,
        )

    # Ya informado: no insistir ante ok/gracias
    if es_ack_outage(texto):
        if ctx.get("outage_ack"):
            msg = mensaje_ack_outage_corto()
        else:
            msg = mensaje_ack_outage()
            ctx["outage_ack"] = True
        # No dejar intención técnica previa viva (evita aviso_deuda al reabrir)
        _reset_ctx_diagnostico(ctx)
        if hasattr(conv, "servicio_detectado"):
            conv.servicio_detectado = ""
        return _pack(
            msg,
            outage_id=outage.id,
            outage_nas=nas or outage.nas_shortname,
        )

    # Pregunta por estado / sigue sin servicio → recordatorio suave (sin nombre técnico)
    if pide_estado_outage(texto) or contiene_sintoma_canal(texto):
        msg = mensaje_para_conversacion(outage, ya_informado=True)
        return _pack(
            msg,
            outage_id=outage.id,
            outage_nas=nas or outage.nas_shortname,
        )

    # Otros mensajes cortos mientras el incidente está activo: no soltar deuda/N1
    t = (texto or "").strip()
    if t and len(t) <= 60 and not parece_consulta_nueva(texto):
        msg = (
            "Seguimos con la incidencia validada por operaciones en tu zona. "
            "Te avisaremos si cambia el estado; no hace falta otro reclamo. "
            "Si ya te anda, avisame."
        )
        return _pack(
            msg,
            outage_id=outage.id,
            outage_nas=nas or outage.nas_shortname,
        )

    # Consultas nuevas de otro tema: dejar pasar (p. ej. factura)
    return None


def _talvez_mensaje_pppoe(
    db: Session,
    abonado: Abonado | None,
    ctx: dict,
    intencion: str,
) -> str | None:
    """Consulta Radius una vez por conversación en reclamos de internet."""
    if (intencion or "").strip() not in _INTENCIONES_PPPOE:
        return None
    if not tiene_internet_fijo(_servicio_abonado(abonado)):
        return None
    if ctx.get("pppoe_informado"):
        return None
    if abonado is None or not str(getattr(abonado, "dni", "") or "").strip():
        return None
    try:
        from app.services.conexion_pppoe import (
            clasificar_rama_pppoe,
            consultar_conexion_pppoe,
            mensaje_abonado_pppoe,
            triage_pppoe_para_prompt,
        )

        estado = consultar_conexion_pppoe(
            dni=str(abonado.dni),
            client_number=str(getattr(abonado, "client_number", "") or ""),
            db=db,
        )
        msg = mensaje_abonado_pppoe(
            estado,
            deuda_positiva=_deuda_positiva(abonado),
        )
        if msg:
            rama = clasificar_rama_pppoe(estado)
            ctx["pppoe_rama"] = rama
            ctx["pppoe_triage"] = triage_pppoe_para_prompt(estado)
            ctx["pppoe_resumen"] = estado.resumen_prompt()
            if estado.sesion:
                ctx["pppoe_ip"] = estado.sesion.public_ip or ""
                ctx["pppoe_uptime"] = estado.sesion.uptime or ""
        else:
            logger.info(
                "PPPoE sin mensaje útil dni=***%s err=%s online=%s",
                str(abonado.dni)[-3:],
                (estado.error or "")[:80],
                estado.online,
            )
        return msg
    except Exception:
        logger.exception("PPPoE check falló en canal")
        return None


def _playbooks(db: Session):
    return playbooks_as_pasos(db)


# Whisper en español suele oír "nueve"/"9" como "no" entre números.
_DNI_NO_COMO_NUEVE = re.compile(r"(?<=\d)[\s.,\-;/]*\bno\b[\s.,\-;/]*(?=\d)", re.IGNORECASE)
_DNI_STT_RELLENO = re.compile(
    r"\b(eh+|este|bueno|mm+|ah|oh|um+|y|e)\b",
    re.IGNORECASE,
)
_DNI_PALABRAS = {
    "cero": "0",
    "uno": "1",
    "una": "1",
    "dos": "2",
    "tres": "3",
    "cuatro": "4",
    "cinco": "5",
    "seis": "6",
    "siete": "7",
    "ocho": "8",
    "nueve": "9",
}
# Whisper a veces escribe el dígito en letras compostas sueltas
_DNI_COMPUESTOS = {
    "diez": "10",
    "once": "11",
    "doce": "12",
    "trece": "13",
    "catorce": "14",
    "quince": "15",
    "dieciseis": "16",
    "dieciséis": "16",
    "diecisiete": "17",
    "dieciocho": "18",
    "diecinueve": "19",
    "veinte": "20",
    "veintiuno": "21",
    "veintiuna": "21",
    "veintidos": "22",
    "veintidós": "22",
    "veintitres": "23",
    "veintitrés": "23",
    "veinticuatro": "24",
    "veinticinco": "25",
    "veintiseis": "26",
    "veintiséis": "26",
    "veintisiete": "27",
    "veintiocho": "28",
    "veintinueve": "29",
}


def _dni_desde_palabras(texto: str) -> str:
    """Convierte dictado en palabras ('dos cuatro nueve…' / 'veinticuatro…') a DNI."""
    t = (texto or "").lower()
    t = (
        t.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    t = _DNI_STT_RELLENO.sub(" ", t)
    t = re.sub(r"[^\w\s]", " ", t)
    tokens = [x for x in t.split() if x]
    if not tokens:
        return ""
    # Permitir muletillas de documento alrededor
    ignorar = {
        "mi",
        "dni",
        "documento",
        "numero",
        "número",
        "es",
        "el",
        "la",
        "de",
        "ene",
        "i",
        "soy",
        "tengo",
        "mando",
        "envio",
        "envío",
        "pasar",
        "paso",
        "te",
        "digo",
    }
    digits: list[str] = []
    for tok in tokens:
        if tok in ignorar:
            continue
        if tok.isdigit() and 1 <= len(tok) <= 2:
            digits.append(tok)
            continue
        if tok in _DNI_PALABRAS:
            digits.append(_DNI_PALABRAS[tok])
            continue
        if tok in _DNI_COMPUESTOS:
            digits.append(_DNI_COMPUESTOS[tok])
            continue
        # token raro: si ya juntamos algo, abortar; si no, seguir
        if digits and not tok.isdigit():
            # no romper si es conector
            if tok in {"con", "punto", "coma", "guion", "guión"}:
                continue
            return ""
    joined = "".join(digits)
    if len(joined) in (7, 8):
        return joined
    return ""


def _dni_desde_digitos_sueltos(texto: str) -> str:
    """Junta DNI dictado dígito a dígito (típico de Whisper): '24, 9, 14, 8, 6, 7'."""
    t = (texto or "").strip()
    if not t:
        return ""
    # Primero muletillas ("y"), después "no"→9 (Whisper: nueve)
    t = _DNI_STT_RELLENO.sub(" ", t)
    t = _DNI_NO_COMO_NUEVE.sub(" 9 ", t)
    t = t.strip()
    # Solo dígitos y separadores comunes de STT/teclado (sin otras letras)
    if not re.fullmatch(r"[\d\s.,\-;/]+", t):
        return ""
    digits = re.sub(r"\D+", "", t)
    if len(digits) in (7, 8):
        return digits
    return ""


def _dni_formato_ar_en_texto(texto: str) -> str:
    """Busca DNI con separadores AR/EN en cualquier parte del mensaje: 24.914.867 / 24,914,867."""
    t = texto or ""
    # Evitar confusión con fechas dd/mm/yyyy
    t = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", " ", t)
    m = re.search(r"\b(\d{1,2})[.\s,](\d{3})[.\s,](\d{3})\b", t)
    if not m:
        return ""
    d = f"{m.group(1)}{m.group(2)}{m.group(3)}"
    return d if len(d) in (7, 8) else ""


def _extraer_dni(texto: str) -> str:
    t = texto or ""
    nums = re.findall(r"\b\d{7,8}\b", t)
    if nums:
        return nums[0]
    ar = _dni_formato_ar_en_texto(t)
    if ar:
        return ar
    spoken = _dni_desde_palabras(t)
    if spoken:
        return spoken
    loose = _dni_desde_digitos_sueltos(t)
    if loose:
        return loose
    # Último recurso: si al sacar fechas quedan exactamente 7–8 dígitos en todo el mensaje
    t2 = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", " ", t)
    only = re.sub(r"\D+", "", t2)
    if len(only) in (7, 8):
        return only
    return ""


def _es_solo_dni(texto: str) -> bool:
    """True si el mensaje es (casi) solo un DNI — no es 'queja' ni frustración."""
    t = (texto or "").strip()
    if re.fullmatch(r"\d{7,8}", t):
        return True
    if re.fullmatch(r"\d{1,2}[.\s,]\d{3}[.\s,]\d{3}", t):
        return True
    if _dni_desde_digitos_sueltos(t):
        return True
    dni = _extraer_dni(t)
    if not dni:
        return False
    # Mensaje corto cuyo único dato útil es el DNI (audio: “mi dni es …”)
    resto = t.lower()
    for w in (
        "mi",
        "dni",
        "documento",
        "numero",
        "número",
        "es",
        "el",
        "la",
        "de",
        "ene",
        "i",
        "paso",
        "mando",
        "envio",
        "envío",
        "te",
        "digo",
        "soy",
        "tengo",
    ):
        resto = re.sub(rf"\b{re.escape(w)}\b", " ", resto)
    resto = re.sub(r"[\d\s.,\-;/]+", " ", resto)
    # quitar palabras numéricas usadas en el DNI
    for w in list(_DNI_PALABRAS) + list(_DNI_COMPUESTOS):
        resto = re.sub(rf"\b{re.escape(w)}\b", " ", resto, flags=re.IGNORECASE)
    resto = re.sub(r"\s+", " ", resto).strip()
    return len(resto) <= 2


def _mensaje_pedi_saldo_reciente(db: Session, conv_id: str) -> bool:
    """True si el cliente pidió saldo/deuda poco antes (p. ej. antes del DNI)."""
    from app.services.diagnostico_n1 import _cliente_consulta_saldo

    for m in crepo.list_mensajes(db, conv_id)[-10:]:
        direccion = getattr(m, "direccion", "") or ""
        autor = getattr(m, "autor", "") or ""
        texto = getattr(m, "texto", "") or ""
        es_cliente = direccion == "in" or autor in ("cliente", "user", "abonado")
        if not es_cliente:
            continue
        if _cliente_consulta_saldo(texto) or "saldo" in texto.lower() or "deuda" in texto.lower():
            return True
    return False


def _intentar_identificar_por_dni(
    db: Session,
    org_id: str,
    texto: str,
) -> Abonado | None:
    dni = _extraer_dni(texto)
    if not dni:
        return None
    # BillTrack es la fuente de verdad del saldo/estado: refrescar siempre
    # (el padrón local puede quedar desfasado o con el signo viejo).
    try:
        from app.estate import repository as org_repo
        from app.services.billtrack import ensure_local_abonado, lookup_abonado_por_dni

        org = org_repo.get_org_by_id(db, org_id)
        slug = org.slug if org else ""
        hit = lookup_abonado_por_dni(dni, org_slug=slug, db=db)
        # Incluye cuentas de baja / inactivas: se identifican igual
        if hit:
            return ensure_local_abonado(db, org_id, hit)
    except Exception:
        logger.debug("BillTrack lookup DNI falló", exc_info=True)
    return crepo.find_abonado_por_dni(db, org_id, dni)


def _deuda_positiva(abonado: Abonado) -> bool:
    """True si el padrón indica deuda. BillTrack: balance positivo = debe."""
    from app.services.eco_voice import parse_monto

    m = parse_monto(getattr(abonado, "deuda_monto", None))
    if m is None:
        return abonado.estado in ("corte", "suspendido")
    return m > 0

def _pide_pago_o_reactivar(texto: str) -> bool:
    t = (texto or "").lower()
    return any(
        k in t
        for k in (
            "me cortaron",
            "cortaron por",
            "falta de pago",
            "reactivar",
            "reactivación",
            "reactivacion",
            "sin servicio por deuda",
        )
    )


def _deberia_priorizar_corte_deuda(
    abonado: Abonado | None,
    texto: str,
    intencion_clasificada: str,
) -> bool:
    """Solo cobro/QR si el usuario habla de pagar/corte, o la cuenta está cortada.

    Un saldo distinto de 0 en BillTrack (billing_balance) NO alcanza: puede ser
    factura vigente o un reclamo de aumento, no un corte por mora.
    """
    if not abonado:
        return False
    if _pide_pago_o_reactivar(texto):
        return True
    estado = (abonado.estado or "").lower()
    if estado in ("corte", "suspendido") and (
        intencion_es_facturacion(intencion_clasificada)
        or intencion_clasificada in ("", "general")
    ):
        return True
    return False


def _intencion_es_tecnica(intencion: str) -> bool:
    intent = (intencion or "").strip()
    if not intent or intent in ("general", "multi_tema", "aviso_deuda") or intencion_es_facturacion(intent):
        return False
    return es_intencion_diagnostico(intent)


def _elige_pago_o_tecnico(texto: str) -> str | None:
    """Tras aviso de deuda: 'pago' | 'tecnico' | None si no se entiende."""
    t = (texto or "").lower().strip()
    if not t:
        return None
    # Ya pagó → seguir con el diagnóstico técnico (vino por el servicio)
    if any(
        k in t
        for k in (
            "ya pagué",
            "ya pague",
            "ya lo pagué",
            "ya lo pague",
            "ya aboné",
            "ya abone",
            "ya lo aboné",
            "ya lo abone",
        )
    ):
        return "tecnico"
    paga = any(
        k in t
        for k in (
            "pagar",
            "pago",
            "deuda",
            "saldo",
            "qr",
            "factura",
            "boleta",
            "abonar",
            "fiserv",
            "primero pagar",
            "la deuda",
            "quiero pagar",
            "ayudame a pagar",
            "ayúdame a pagar",
        )
    )
    tecnico = any(
        k in t
        for k in (
            "seguí",
            "segui",
            "seguir",
            "seguimos",
            "diagnóstico",
            "diagnostico",
            "wifi",
            "wi-fi",
            "conexión",
            "conexion",
            "el problema",
            "un problema",
            "tengo un problema",
            "problema con",
            "el servicio",
            "móvil",
            "movil",
            "imowi",
            "después pago",
            "despues pago",
            "pago después",
            "pago despues",
            "más tarde",
            "mas tarde",
            "ahora no",
            "después",
            "despues",
            "técnico",
            "tecnico",
            "fibra",
        )
    )
    # "no tengo internet" menciona internet pero no elige diagnóstico
    if "internet" in t and not niega_producto_internet(t):
        tecnico = True
    pospone_pago = any(
        k in t
        for k in (
            "después pago",
            "despues pago",
            "pago después",
            "pago despues",
            "la pago después",
            "la pago despues",
            "pago más tarde",
            "pago mas tarde",
            "más tarde",
            "mas tarde",
            "ahora no",
            "ahora tengo",
            "ahora el problema",
            "después la factura",
            "despues la factura",
            "la factura después",
            "la factura despues",
        )
    )
    if paga and not tecnico:
        return "pago"
    if tecnico and not paga:
        return "tecnico"
    if paga and tecnico:
        # "la pago después / ahora el servicio" → técnico; "primero pagar" → pago
        if pospone_pago or any(
            k in t
            for k in (
                "problema",
                "diagnóstico",
                "diagnostico",
                "seguí",
                "segui",
                "seguir",
                "el servicio",
            )
        ):
            return "tecnico"
        if any(k in t for k in ("primero", "antes", "pagar y", "pago y")):
            return "pago"
        return "pago"
    return None


def _cliente_salir_aviso_deuda(texto: str) -> bool:
    """No quiere pagar ni diagnosticar / servicio OK / desiste."""
    if _cliente_desiste_o_resuelto(texto) or indica_resuelto(texto):
        return True
    t = (texto or "").lower().strip()
    t = re.sub(r"[¡!.,¿?]+", " ", t)
    t = " ".join(t.split())
    if not t:
        return False
    if any(
        k in t
        for k in (
            "funciona todo",
            "todo funciona",
            "todo bien",
            "ya anda",
            "ya anduvo",
            "ya volvió",
            "ya volvio",
            "anda bien",
            "no necesito",
            "no hace falta",
            "ninguna de las",
            "ninguna opcion",
            "ninguna opción",
            "las dos no",
            "ni una ni otra",
        )
    ):
        return True
    return t in {
        "no",
        "no gracias",
        "no nada",
        "nada",
        "nada gracias",
        "ninguno",
        "ninguna",
        "dejar",
        "dejá",
        "deja",
        "cancelar",
    }


def _reset_ctx_diagnostico(ctx: dict) -> None:
    """Limpia intención/pasos de un flujo N1 previo (p. ej. post-incidente masivo)."""
    for k in (
        "intencion",
        "intencion_tecnica_pendiente",
        "paso_idx",
        "diag_turnos",
        "pasos_cubiertos",
        "pppoe_informado",
        "pppoe_rama",
        "pppoe_triage",
        "aviso_deuda_ofrecido",
        "temas_pendientes",
        "texto_multi_tema",
        "prioridad_elegida",
    ):
        ctx.pop(k, None)


def _texto_aviso_deuda_tecnico(abonado: Abonado, intencion_tecnica: str) -> str:
    from app.services.eco_voice import texto_monto_ars

    monto = texto_monto_ars(getattr(abonado, "deuda_monto", None))
    if (intencion_tecnica or "").startswith("movil"):
        tema = "del móvil"
    elif (intencion_tecnica or "").startswith("wifi"):
        tema = "del WiFi"
    else:
        tema = "de internet"
    return (
        f"Antes de seguir: en tu cuenta figura un saldo pendiente de {monto}. "
        f"¿Querés que te ayude primero a pagar, o seguimos con el diagnóstico {tema}?"
    )


def _servicio_abonado(abonado: Abonado | None) -> str:
    return str(getattr(abonado, "servicio", "") or "").strip().lower() if abonado else ""


def _intencion_compatible_padron(intencion: str, abonado: Abonado | None, texto: str = "") -> str:
    return ajustar_intencion_a_padron(intencion, _servicio_abonado(abonado), texto)


def _debe_explicar_sin_internet(abonado: Abonado | None, texto: str, intencion: str = "") -> bool:
    if _servicio_abonado(abonado) != "movil":
        return False
    if niega_producto_internet(texto):
        return True
    return intencion_es_internet(intencion)


def _kb_fragmento(
    db: Session | None,
    org_id: str,
    consulta: str,
    *,
    max_chars: int = 1200,
) -> str:
    """Fragmento de conocimiento (tenant + RAG) para enriquecer la respuesta N1."""
    if db is None or not org_id or not (consulta or "").strip():
        return ""
    try:
        from app.services import knowledge_unified

        kb = knowledge_unified.buscar_unificado(db, org_id, consulta, limit_tenant=3)
        ctx = (kb.get("kb_contexto") or "").strip()
        if not ctx:
            return ""
        return ctx[:max_chars]
    except Exception:
        logger.debug("KB no disponible para redacción N1", exc_info=True)
        return ""


def _redactar_con_llama(
    borrador: str,
    contexto: str,
    *,
    db: Session | None = None,
    org_id: str = "",
    consulta: str = "",
) -> str:
    """Reescribe el paso del playbook con la IA admin, estilo agente humano breve."""
    try:
        from app.llm import chat_completion
        from app.services.eco_voice import TEMPERATURE_N1, system_prompt_eco_rewrite
        from app.services.prompt_safety import (
            looks_like_jailbreak,
            sanitize_user_text,
            strip_instruction_phrases,
            with_anti_injection,
            wrap_untrusted,
        )

        if looks_like_jailbreak(consulta):
            return borrador.strip()

        kb_ctx = strip_instruction_phrases(_kb_fragmento(db, org_id, consulta or contexto, max_chars=600))
        kb_block = (
            f"\n\nDato de KB (opcional, máximo una frase si aporta):\n"
            f"{wrap_untrusted('KB', kb_ctx, max_chars=600)}"
            if kb_ctx
            else ""
        )
        out = chat_completion(
            [
                {
                    "role": "system",
                    "content": with_anti_injection(system_prompt_eco_rewrite()),
                },
                {
                    "role": "user",
                    "content": (
                        f"Contexto: {sanitize_user_text(contexto, max_chars=400)}\n"
                        f"{kb_block}"
                        f"{wrap_untrusted('CLIENTE_DIJO', (consulta or '').strip() or '(n/a)')}\n"
                        f"Borrador (reescribilo breve, una pregunta; no inventes acciones):\n"
                        f"{sanitize_user_text(borrador, max_chars=500)}"
                    ),
                },
            ],
            temperature=TEMPERATURE_N1,
        )
        texto = (out or "").strip() or borrador
        # Si el modelo se va de mambo, volver al playbook corto
        if len(texto) > 320 or texto.count("?") > 1:
            return borrador.strip()
        return texto
    except Exception:
        return borrador


def _label_tema_pendiente(tema: str) -> str:
    return {
        "facturacion": "aumento/factura",
        "tecnico": "conexión/internet",
    }.get((tema or "").strip(), tema or "otro tema")


def _append_evidencia_ticket(
    db: Session,
    org_id: str,
    ticket_id: str,
    nota: str,
) -> None:
    if not ticket_id or not (nota or "").strip():
        return
    try:
        from app.estate import repository as repo

        t = repo.get_ticket(db, org_id, ticket_id)
        if not t:
            return
        bloque = nota.strip()[:800]
        ev = (t.evidencia or "").strip()
        if bloque in ev:
            return
        t.evidencia = f"{ev}\n{bloque}".strip() if ev else bloque
        desc = (t.descripcion_falla or "").strip()
        if bloque[:120] not in desc:
            t.descripcion_falla = f"{desc} | {bloque}".strip(" |")[:2000]
        db.commit()
    except Exception:
        logger.debug("No se pudo anotar evidencia en ticket %s", ticket_id, exc_info=True)


def _crear_ticket_n2(
    db: Session,
    org_id: str,
    conv: ConversacionCanal,
    abonado: Abonado | None,
    motivo: str,
    *,
    intencion: str = "",
    paso_idx: int = 0,
    ctx: dict | None = None,
) -> str:
    if conv.ticket_id:
        return conv.ticket_id
    mensajes = crepo.list_mensajes(db, conv.id)
    evidencia = "\n".join(f"[{m.autor}] {m.texto}" for m in mensajes[-12:])
    nombre = abonado.nombre if abonado else conv.telefono
    linea = (abonado.linea_msisdn if abonado else "") or conv.telefono
    intent = intencion or conv.servicio_detectado or (abonado.servicio if abonado else "general")
    tag = tag_para_intencion(str(intent))
    handoff = resumen_handoff(
        abonado=abonado,
        telefono=conv.telefono,
        intencion=str(intent),
        motivo=motivo,
        paso_idx=paso_idx,
    )
    ctx = ctx if isinstance(ctx, dict) else {}
    pendientes = [str(x) for x in (ctx.get("temas_pendientes") or []) if str(x).strip()]
    extra_temas = ""
    if pendientes:
        labels = ", ".join(_label_tema_pendiente(p) for p in pendientes)
        extra_temas = f" Temas pendientes del abonado (aún sin cerrar en N1): {labels}."
        evidencia = f"{evidencia}\n[Temas pendientes] {labels}".strip()
    descripcion = (
        f"[ORIGEN: {BOT_DISPLAY_NAME_SHORT}] {tag} Escalamiento N2 canal abonado ({nombre}): "
        f"{motivo}.{extra_temas} {handoff}"
    )
    t = ticket_bridge.crear_ticket(
        db,
        org_id,
        linea=linea,
        dispositivo="Canal abonado",
        descripcion_falla=descripcion[:2000],
        origen=_origen_ticket(conv.canal),
        categoria=str(intent).replace("_", " ").title() if intent else "Canal Abonado",
        creado_por=f"bot:{conv.telefono}",
        nivel="N2",
        destino="imowi_noc",
        proveedor="NOC",
        motivo_escalamiento=f"{tag} {motivo}",
        evidencia=evidencia,
        acciones_n1_realizadas=handoff,
        regla_clasificacion="canal_abonado_n2",
    )
    conv.ticket_id = t.id
    prev_estado = conv.estado or ""
    conv.estado = "espera_agente"
    if pendientes:
        ctx["temas_anotados_ticket"] = list(
            dict.fromkeys(list(ctx.get("temas_anotados_ticket") or []) + pendientes)
        )
        crepo.set_contexto(conv, ctx)
    db.commit()
    try:
        from app.services.handoff_notify import notify_espera_agente

        notify_espera_agente(db, conv, prev_estado=prev_estado)
    except Exception:
        logger.warning("Fallo notify handoff tras ticket N2", exc_info=True)
    return t.id


def _nota_temas_pendientes(ctx: dict | None) -> str:
    pendientes = [str(x) for x in ((ctx or {}).get("temas_pendientes") or []) if str(x).strip()]
    if not pendientes:
        return ""
    labels = " y ".join(_label_tema_pendiente(p) for p in pendientes)
    return f" También dejé anotado el tema de {labels} para el agente."


def _tema_desde_mensaje(texto: str) -> str | None:
    t = (texto or "").lower().replace("fatura", "factura")
    if any(
        k in t
        for k in (
            "factura",
            "factur",
            "aumento",
            "boleta",
            "tarifa",
            "cobro",
            "saldo",
            "plata",
            "precio",
        )
    ):
        return "facturacion"
    if any(
        k in t
        for k in (
            "internet",
            "wifi",
            "conexión",
            "conexion",
            "fibra",
            "los",
            "router",
            "ont",
            "señal",
            "senal",
        )
    ):
        return "tecnico"
    return None


def _cliente_desiste_o_resuelto(texto: str) -> bool:
    """True si el abonado dice que ya está / no necesita seguir (ni agente)."""
    if indica_resuelto(texto):
        return True
    t = (texto or "").lower().strip()
    if not t:
        return False
    # Confusión ≠ cierre (Whisper: «no entiendo nada»)
    if any(
        k in t
        for k in (
            "no entiendo",
            "no te entiendo",
            "no comprendo",
            "qué dijiste",
            "que dijiste",
            "no me queda claro",
            "no entendí",
            "no entendi",
        )
    ):
        return False
    if any(
        k in t
        for k in (
            "no necesito más",
            "no necesito mas",
            "no necesito nada",
            "no hace falta",
            "ya está todo",
            "ya esta todo",
            "todo solucionado",
            "está solucionado",
            "esta solucionado",
            "nada más",
            "nada mas",
            "no gracias",
            "dejá así",
            "deja asi",
            "dejalo así",
            "dejalo asi",
        )
    ):
        return True
    # "no, ya está solucionado" — no matchear «no … nada» suelto
    if re.match(r"^no[\s,.]", t) and any(
        k in t
        for k in (
            "solucion",
            "no necesito",
            "agente",
            "nada más",
            "nada mas",
            "está todo",
            "esta todo",
        )
    ):
        return True
    return False


def _primer_nombre_cliente(abonado: Abonado | None = None, nombre: str = "") -> str:
    raw = (nombre or "").strip() or (getattr(abonado, "nombre", None) or "").strip()
    if not raw:
        return ""
    return raw.split()[0].title()


def _mensaje_cierre_calido(nombre: str = "") -> str:
    """Cierre N1 con más expresión (TTS y texto)."""
    nom = (nombre or "").strip()
    if nom:
        return (
            f"De nada {nom}. Cualquier otra consulta, no dudes en escribirme. "
            "¡Que tengas un lindo día!"
        )
    return (
        "De nada. Cualquier otra consulta, no dudes en escribirme. "
        "¡Que tengas un lindo día!"
    )


def _cerrar_consulta_resuelta(
    db: Session,
    org_id: str,
    conv: ConversacionCanal,
    *,
    canal: str,
    mensaje: str = "",
    nota_ticket: str = "",
    nombre: str = "",
) -> dict:
    """Cierra el hilo N1 como resuelto (opcional: anota el ticket si había)."""
    tid = (conv.ticket_id or "").strip()
    if tid and nota_ticket:
        _append_evidencia_ticket(db, org_id, tid, nota_ticket)
    conv.estado = "cerrado"
    db.commit()
    if (mensaje or "").strip():
        resp = mensaje.strip()
    else:
        nom = (nombre or "").strip()
        if not nom and (getattr(conv, "abonado_id", None) or "").strip():
            abo = db.get(Abonado, conv.abonado_id)
            nom = _primer_nombre_cliente(abo)
        resp = _mensaje_cierre_calido(nom)
    _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
    enviar_encuesta_cierre(
        db, conv, origen=ORIGEN_BOT, enviar_externo=_enviar_externo(canal)
    )
    return {
        "ok": True,
        "modo": "cerrado",
        "conversacion_id": conv.id,
        "respuesta": resp,
        "estado": conv.estado,
        "ticket_id": tid,
    }


_AVISO_ESPERA_COOLDOWN_S = 90


def _intencion_desde_tipo_menu(tipo: str) -> str:
    """tecnico → movil | comercial → alta_plan | facturacion → facturacion."""
    if tipo == "tecnico":
        return "movil"
    if tipo == "comercial":
        return "alta_plan"
    return "facturacion"


def _manejar_menu_consulta_n1(
    db: Session,
    org_id: str,
    conv: ConversacionCanal,
    abonado: Abonado | None,
    texto: str,
    *,
    canal: str,
    ctx: dict,
    usar_llama: bool,
) -> dict | None:
    """Menú 2 pasos: servicio → (si móvil) técnico/comercial/administrativo."""
    paso = str(ctx.get("menu_paso") or "").strip()
    if not paso or not abonado:
        return None
    servicio_abo = abonado.servicio if abonado else ""

    if paso == "servicio":
        elec = parse_menu_servicio(texto)
        # Padrón sin internet fijo + habla de fibra/niega internet → aclarar
        if not tiene_internet_fijo(servicio_abo) and (
            niega_producto_internet(texto)
            or elec == "internet"
            or (
                elec is None
                and any(
                    k in (texto or "").lower()
                    for k in ("internet", "fibra", "wifi", "wi-fi")
                )
            )
        ):
            resp = texto_sin_internet_contratado(servicio_abo)
            _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
                "intencion": "general",
                "menu_paso": "servicio",
            }
        if not elec:
            resp = f"No te entendí. {texto_menu_consulta(servicio_abo)}"
            _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
                "menu_paso": "servicio",
            }
        if elec == "movil":
            ctx["menu_paso"] = "tipo"
            ctx["menu_servicio"] = "movil"
            crepo.set_contexto(conv, ctx)
            db.commit()
            resp = texto_menu_tipo_consulta()
            _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
                "menu_paso": "tipo",
            }
        # internet / facturacion → arrancar flujo
        intent = "internet" if elec == "internet" else "facturacion"
        ctx.pop("menu_paso", None)
        ctx.pop("menu_servicio", None)
        return _arrancar_intencion_menu(
            db,
            org_id,
            conv,
            abonado,
            texto,
            canal=canal,
            ctx=ctx,
            intencion=intent,
            usar_llama=usar_llama,
            servicio_abo=servicio_abo,
        )

    if paso == "tipo":
        tipo = parse_menu_tipo_consulta(texto)
        if not tipo:
            resp = f"No te entendí. {texto_menu_tipo_consulta()}"
            _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
                "menu_paso": "tipo",
            }
        intent = _intencion_desde_tipo_menu(tipo)
        ctx.pop("menu_paso", None)
        ctx.pop("menu_servicio", None)
        return _arrancar_intencion_menu(
            db,
            org_id,
            conv,
            abonado,
            texto,
            canal=canal,
            ctx=ctx,
            intencion=intent,
            usar_llama=usar_llama,
            servicio_abo=servicio_abo,
        )

    return None


def _arrancar_intencion_menu(
    db: Session,
    org_id: str,
    conv: ConversacionCanal,
    abonado: Abonado | None,
    texto: str,
    *,
    canal: str,
    ctx: dict,
    intencion: str,
    usar_llama: bool,
    servicio_abo: str,
) -> dict:
    ctx["intencion"] = intencion
    ctx["paso_idx"] = 0
    ctx["diag_turnos"] = 0
    ctx["pasos_cubiertos"] = []
    if intencion in ("internet", "internet_radio", "internet_adsl", "movil"):
        conv.servicio_detectado = intencion
    if (
        abonado
        and _deuda_positiva(abonado)
        and _intencion_es_tecnica(intencion)
        and not ctx.get("aviso_deuda_ofrecido")
        and intencion != "corte_deuda"
    ):
        ctx["intencion"] = "aviso_deuda"
        ctx["intencion_tecnica_pendiente"] = intencion
        ctx["aviso_deuda_ofrecido"] = True
        crepo.set_contexto(conv, ctx)
        db.commit()
        resp = _texto_aviso_deuda_tecnico(abonado, intencion)
        _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
        return {
            "ok": True,
            "modo": "bot",
            "conversacion_id": conv.id,
            "respuesta": resp,
            "estado": conv.estado,
            "intencion": "aviso_deuda",
        }
    crepo.set_contexto(conv, ctx)
    db.commit()
    diag = _aplicar_diagnostico_ia(
        db,
        org_id,
        conv,
        abonado,
        texto,
        canal=canal,
        ctx=ctx,
        intencion=intencion,
        usar_llama=usar_llama,
    )
    if diag is not None:
        return diag
    pb = _playbooks(db)
    pasos = pb.get(intencion) or pb["general"]
    pregunta = pasos[0].pregunta if pasos else "Contame qué necesitás."
    if intencion == "general":
        pregunta = texto_menu_consulta(servicio_abo)
    if intencion == "movil":
        pregunta = (
            "Dale, vamos con el servicio de telefonía móvil. "
            "¿Qué te pasa: sin señal, sin datos o no podés llamar?"
        )
    if usar_llama:
        pregunta = _redactar_con_llama(
            pregunta,
            f"intencion={intencion} desde_menu=1",
            db=db,
            org_id=org_id,
            consulta=texto,
        )
    _enviar_respuesta(db, org_id, conv, pregunta, enviar_externo=_enviar_externo(canal))
    return {
        "ok": True,
        "modo": "bot",
        "conversacion_id": conv.id,
        "respuesta": pregunta,
        "estado": conv.estado,
        "intencion": intencion,
    }


def _mensaje_operativo_sin_tts(texto: str) -> bool:
    """Avisos cortos de sistema (CSAT / derivado) → siempre texto, nunca TTS."""
    t = (texto or "").strip().lower()
    if not t:
        return True
    if "gracias por tu calificación" in t or "gracias por tu calificacion" in t:
        return True
    if "ya está derivado" in t or "ya esta derivado" in t:
        return True
    if "te van a responder por este mismo chat" in t and len(t) < 320:
        return True
    return False


def _responder_espera_agente(
    db: Session,
    org_id: str,
    conv: ConversacionCanal,
    texto: str,
    *,
    canal: str,
) -> dict:
    """En espera de agente: si ya resolvió, cierra; si insiste en otro tema, anota."""
    if _cliente_desiste_o_resuelto(texto):
        return _cerrar_consulta_resuelta(
            db,
            org_id,
            conv,
            canal=canal,
            nota_ticket=(
                "[Abonado] Indicó que ya está solucionado / no necesita agente: "
                f"{(texto or '').strip()[:300]}"
            ),
        )

    tid = conv.ticket_id or ""
    ctx = crepo.get_contexto(conv)
    # Nunca TTS en cola humana: el flag de audio entrante + reintentos Meta
    # generaba un loop de la misma nota de voz (~9s).
    ctx.pop("responder_en_audio", None)

    tema = _tema_desde_mensaje(texto)
    pendientes = [str(x) for x in (ctx.get("temas_pendientes") or []) if str(x).strip()]
    anotados = [str(x) for x in (ctx.get("temas_anotados_ticket") or []) if str(x).strip()]
    insiste = any(
        k in (texto or "").lower()
        for k in ("y la ", "y el ", "qué pasó con", "que paso con", "y eso de")
    )

    def _cooldown_activo() -> bool:
        last = ctx.get("ultimo_aviso_espera_ts")
        try:
            return last is not None and (time.time() - float(last)) < _AVISO_ESPERA_COOLDOWN_S
        except (TypeError, ValueError):
            return False

    def _marcar_aviso_enviado() -> None:
        ctx["ultimo_aviso_espera_ts"] = time.time()
        crepo.set_contexto(conv, ctx)
        db.commit()

    if tema and tid and (tema in pendientes or tema in anotados or insiste):
        label = _label_tema_pendiente(tema)
        _append_evidencia_ticket(
            db,
            org_id,
            tid,
            f"[Seguimiento abonado] Insiste en {label}: {(texto or '').strip()[:300]}",
        )
        ctx["temas_pendientes"] = [p for p in pendientes if p != tema]
        if tema not in anotados:
            anotados.append(tema)
        ctx["temas_anotados_ticket"] = anotados
        aviso = (
            f"Sí: el ticket {tid} queda con el reclamo de {label} "
            "junto a lo de la conexión. El agente lo ve en el mismo caso; "
            "te van a responder por este chat."
        )
        if _cooldown_activo():
            crepo.set_contexto(conv, ctx)
            db.commit()
            return {
                "ok": True,
                "modo": "espera_agente",
                "conversacion_id": conv.id,
                "respuesta": "",
                "estado": conv.estado,
                "ticket_id": tid,
                "aviso_omitido": True,
            }
        _marcar_aviso_enviado()
        _enviar_respuesta(db, org_id, conv, aviso, enviar_externo=_enviar_externo(canal))
        return {
            "ok": True,
            "modo": "espera_agente",
            "conversacion_id": conv.id,
            "respuesta": aviso,
            "estado": conv.estado,
            "ticket_id": tid,
        }

    if _cooldown_activo():
        crepo.set_contexto(conv, ctx)
        db.commit()
        return {
            "ok": True,
            "modo": "espera_agente",
            "conversacion_id": conv.id,
            "respuesta": "",
            "estado": conv.estado,
            "ticket_id": tid,
            "aviso_omitido": True,
        }

    aviso = (
        "Tu caso ya está derivado a un agente. En breve te van a responder por este mismo chat."
    )
    if pendientes and tid:
        labels = " y ".join(_label_tema_pendiente(p) for p in pendientes)
        aviso = (
            f"Tu caso ya está derivado (ticket {tid}). "
            f"También quedó anotado: {labels}. Te responden por este chat."
        )
    _marcar_aviso_enviado()
    _enviar_respuesta(db, org_id, conv, aviso, enviar_externo=_enviar_externo(canal))
    return {
        "ok": True,
        "modo": "espera_agente",
        "conversacion_id": conv.id,
        "respuesta": aviso,
        "estado": conv.estado,
        "ticket_id": tid,
    }


def _es_canal_externo(canal: str) -> bool:
    return (canal or "") in ("whatsapp", "telegram", "simulate")


def _origen_ticket(canal: str) -> str:
    return {
        "whatsapp": "WhatsApp",
        "simulate": "WhatsApp",
        "telegram": "Telegram",
        "web": "Portal",
    }.get(canal or "", "Canal")


def _dispatch_outbound(
    conv: ConversacionCanal,
    texto: str,
    *,
    prefer_audio: bool = False,
) -> dict:
    canal = conv.canal or ""
    if canal == "whatsapp":
        # Preferir wa_id (from de Meta); telefono puede diferir en formato AR
        dest = (conv.wa_id or conv.telefono or "").strip()
        if prefer_audio:
            try:
                from app.services.tts import mime_y_filename_tts, sintetizar_audio
                from app.services.whatsapp_client import enviar_audio as enviar_audio_wa

                audio = sintetizar_audio(texto)
                if audio:
                    mime, fname = mime_y_filename_tts()
                    result = enviar_audio_wa(dest, audio, mime=mime, filename=fname)
                    if result.get("ok"):
                        return result
                    logger.warning(
                        "WhatsApp audio send falló; fallback texto to=%s detail=%s",
                        dest,
                        (result.get("detail") or result.get("reason") or "")[:200],
                    )
            except Exception:
                logger.exception("TTS/audio WA falló; fallback texto dest=%s", dest)
        return enviar_texto_wa(dest, texto)
    if canal == "telegram":
        dest = conv.wa_id or conv.telefono
        return enviar_texto_tg(dest, texto)
    return {"ok": True, "simulated": True}


def _enviar_respuesta(
    db: Session,
    org_id: str,
    conv: ConversacionCanal,
    texto: str,
    *,
    enviar_externo: bool = True,
) -> str:
    crepo.add_mensaje(db, org_id, conv.id, direccion="out", autor="bot", texto=texto)
    if enviar_externo and _es_canal_externo(conv.canal):
        prefer_audio = False
        if (conv.canal or "") == "whatsapp":
            try:
                prefer_audio = bool(crepo.get_contexto(conv).get("responder_en_audio"))
            except Exception:
                prefer_audio = False
            if prefer_audio and _mensaje_operativo_sin_tts(texto):
                prefer_audio = False
        delivery = _dispatch_outbound(conv, texto, prefer_audio=prefer_audio)
        if not delivery.get("ok") or delivery.get("simulated"):
            logger.warning(
                "Outbound canal=%s conv=%s ok=%s simulated=%s type=%s detail=%s",
                conv.canal,
                conv.id,
                delivery.get("ok"),
                delivery.get("simulated"),
                delivery.get("type") or "text",
                (delivery.get("detail") or delivery.get("reason") or "")[:200],
            )
    return texto


def mensaje_derivacion_visitante(*, motivo: str = "") -> str:
    """Copy cálido para quien no tiene cuenta identificada (sin tono de 'cola inferior')."""
    motivo_l = (motivo or "").lower()
    if "dni" in motivo_l:
        return (
            "No te encuentro como abonado en el padrón con ese dato. "
            "Puede ser otro DNI, o que todavía no seas cliente de la Cooperativa Batán. "
            "Igual te derivo con un agente para ayudarte. "
            "Te van a responder por este mismo chat. "
            "Si ya sos abonado, intentá de nuevo con el DNI del titular."
        )
    return (
        "Hola, soy la asistente de la Cooperativa Batán. "
        "Todavía no identifiqué tu cuenta, así que no puedo ver saldos ni diagnosticar "
        "tu servicio de forma automática. "
        "Te derivo con un agente; te responden por este mismo chat. "
        "Si sos abonado, pasame el DNI del titular cuando puedas."
    )


def marcar_cola_visitante(conv: ConversacionCanal, ctx: dict | None, *, motivo: str) -> dict:
    """Marca visitante / prioridad baja y deja la conversación en espera de agente (sin ticket N2)."""
    out = dict(ctx) if isinstance(ctx, dict) else {}
    out["invitado"] = True
    out["visitante"] = True
    out["cola_prioridad"] = "baja"
    out["motivo_derivacion"] = motivo
    out["saludo"] = True
    out.pop("identificado", None)
    crepo.set_contexto(conv, out)
    if not (conv.servicio_detectado or "").strip():
        conv.servicio_detectado = "comercial"
    # prev_estado se notifica en callers con DB (ver notify_espera_agente)
    out["_prev_estado_antes_cola"] = conv.estado or ""
    conv.estado = "espera_agente"
    return out


def _derivar_visitante(
    db: Session,
    org_id: str,
    conv: ConversacionCanal,
    *,
    canal: str,
    ctx: dict,
    motivo: str = "visitante_sin_cuenta",
    enviar_mensaje: bool = True,
    mensaje: str | None = None,
) -> dict:
    """Visitante sin padrón: mensaje breve + cola de agente (prioridad baja)."""
    ctx = marcar_cola_visitante(conv, ctx, motivo=motivo)
    prev = str(ctx.pop("_prev_estado_antes_cola", "") or "")
    db.commit()
    try:
        from app.services.handoff_notify import notify_espera_agente

        notify_espera_agente(db, conv, prev_estado=prev)
    except Exception:
        logger.warning("Fallo notify handoff visitante", exc_info=True)
    resp = (mensaje or mensaje_derivacion_visitante(motivo=motivo)).strip()
    if enviar_mensaje and resp:
        _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
    return {
        "ok": True,
        "modo": "espera_agente",
        "conversacion_id": conv.id,
        "respuesta": resp if enviar_mensaje else "",
        "estado": conv.estado,
        "es_visitante": True,
        "cola_prioridad": "baja",
    }


def _mensaje_cierre_escalamiento(
    tid: str,
    *,
    motivo: str = "",
    mensaje_ia: str = "",
    nota_temas: str = "",
    intencion: str = "",
) -> str:
    """Cierre empático al derivar: no reemplazar un mensaje bueno por plantilla fría."""
    nota = (nota_temas or "").strip()
    if nota and not nota.startswith(" "):
        nota = " " + nota
    motivo_l = (motivo or "").lower()
    ia = (mensaje_ia or "").strip()
    from app.services.diagnostico_n1 import (
        _parece_diagnostico_optica_fuera_de_lugar,
        es_intencion_optica,
    )

    aplica_optica = es_intencion_optica(intencion)
    # No reutilizar plantilla/tono de fibra si la intención no es óptica
    if not aplica_optica and (
        any(k in motivo_l for k in ("los", "fibra", "optica", "óptica", "wifi_post_los"))
        or _parece_diagnostico_optica_fuera_de_lugar(ia)
    ):
        ia = ""
        motivo_l = "handoff"

    # Si la IA / detector ya explicó el caso, conservar tono y solo sumar ticket
    if ia and "ticket" not in ia.lower():
        base = ia.rstrip(" .")
        # Evitar dejar la pregunta "¿te derivo?" si ya estamos derivando
        for q in (
            " ¿Te derivo con un agente para coordinar?",
            " ¿Te derivo con un agente para coordinarla?",
            " ¿Querés que te derive?",
            " ¿Me confirmás si te derivo?",
        ):
            if base.endswith(q.strip()) or q.strip().lower() in base.lower():
                base = base.replace(q.strip(), "").replace(q.strip().lower(), "").rstrip(" .")
        return (
            f"{base}. Ya generé el ticket {tid} y te derivo con un agente.{nota} "
            "Te van a responder por este mismo chat."
        )

    if aplica_optica and any(
        k in motivo_l for k in ("los", "fibra", "optica", "óptica", "wifi_post_los")
    ):
        return (
            f"La luz LOS en rojo indica que la fibra no está llegando bien a la cajita. "
            f"Eso ya no lo resolvemos reiniciando: hace falta una visita técnica. "
            f"Generé el ticket {tid} y te derivo con un agente.{nota} "
            "Te van a responder por este mismo chat."
        )

    if "pedido_humano" in motivo_l or "agente" in motivo_l:
        return (
            f"Dale, te derivo con un agente y le paso lo que charlamos. "
            f"Ticket {tid}.{nota} Quedate en este chat."
        )

    return (
        f"Con lo que me contaste ya hace falta un agente. "
        f"Generé el ticket {tid}.{nota} Te van a responder por este mismo chat."
    )


def _aplicar_diagnostico_ia(
    db: Session,
    org_id: str,
    conv: ConversacionCanal,
    abonado: Abonado | None,
    texto: str,
    *,
    canal: str,
    ctx: dict,
    intencion: str,
    usar_llama: bool,
) -> dict | None:
    """Modo técnico: la IA diagnostica con el playbook como checklist.

    Retorna respuesta del canal o None si no aplica (seguir flujo estructurado).
    """
    if not usar_llama or not resolve_canal_diagnostico_ia(db):
        return None
    if not es_intencion_diagnostico(intencion):
        return None

    # Cierre primero: no seguir con ramas Wi‑Fi/PPPoE si el abonado ya resolvió
    if indica_resuelto(texto) or _cliente_desiste_o_resuelto(texto):
        return _cerrar_consulta_resuelta(
            db,
            org_id,
            conv,
            canal=canal,
            nombre=_primer_nombre_cliente(abonado),
            nota_ticket=(
                "[Abonado] Confirmó resolución / pidió cierre durante diagnóstico: "
                f"{(texto or '').strip()[:200]}"
            ),
        )

    # Primer turno de internet: informar estado PPPoE real (no depender del LLM).
    pppoe_msg = _talvez_mensaje_pppoe(db, abonado, ctx, intencion)
    if pppoe_msg:
        turnos = int(ctx.get("diag_turnos") or 0)
        ctx["diag_turnos"] = turnos + 1
        ctx["pppoe_informado"] = True
        ctx["intencion"] = intencion
        crepo.set_contexto(conv, ctx)
        db.commit()
        _enviar_respuesta(db, org_id, conv, pppoe_msg, enviar_externo=_enviar_externo(canal))
        return {
            "ok": True,
            "modo": "diagnostico",
            "conversacion_id": conv.id,
            "respuesta": pppoe_msg,
            "estado": conv.estado,
            "intencion": intencion,
            "diagnostico_ia": True,
            "pppoe": True,
        }

    # Línea PPPoE OK + "solo Wi‑Fi" → playbook wifi (sin preguntar ONT/PON).
    if (
        ctx.get("pppoe_rama") == "wifi_lan"
        and not ctx.get("wifi_rama_activada")
        and (_cliente_indica_solo_wifi(texto) or _cliente_cable_ok(texto))
    ):
        ctx["wifi_rama_activada"] = True
        ctx["enlace_optico_ok"] = True
        intencion = "wifi"
        ctx["intencion"] = "wifi"
        cubiertos = [str(x) for x in (ctx.get("pasos_cubiertos") or []) if str(x).strip()]
        for pid in (
            "wifi_vs_cable_ftth",
            "luces_los",
            "cable_fibra",
            "reinicio_ont",
            "enlace_optico",
        ):
            if pid not in cubiertos:
                cubiertos.append(pid)
        if _cliente_cable_ok(texto):
            msg = (
                "Si por cable anda bien, el acceso está OK y el problema es el Wi‑Fi. "
                "¿Les pasa a todos los equipos Wi‑Fi o solo a uno?"
            )
            if "otros_dispositivos_wifi" not in cubiertos:
                cubiertos.append("zona_wifi")
        else:
            msg = (
                "Dale, entonces el acceso anda y el tema es el Wi‑Fi. "
                "¿Les pasa a todos los equipos Wi‑Fi o solo a uno?"
            )
        turnos = int(ctx.get("diag_turnos") or 0)
        ctx["pasos_cubiertos"] = cubiertos
        ctx["diag_turnos"] = turnos + 1
        ctx["paso_idx"] = len(cubiertos)
        ctx["ultima_diag_motivo"] = "rama_wifi_post_pppoe"
        crepo.set_contexto(conv, ctx)
        db.commit()
        _enviar_respuesta(db, org_id, conv, msg, enviar_externo=_enviar_externo(canal))
        return {
            "ok": True,
            "modo": "diagnostico",
            "conversacion_id": conv.id,
            "respuesta": msg,
            "estado": conv.estado,
            "intencion": "wifi",
            "diagnostico_ia": True,
            "pppoe_wifi": True,
        }

    # Ya en rama wifi post-PPPoE: mantener intención wifi aunque el ctx diga internet
    if ctx.get("wifi_rama_activada") or (
        ctx.get("pppoe_rama") == "wifi_lan" and ctx.get("enlace_optico_ok")
    ):
        if (intencion or "").startswith("internet"):
            intencion = "wifi"
            ctx["intencion"] = "wifi"

    pb = _playbooks(db)
    checklist = pb.get(intencion) or pb.get("general") or []
    historial = crepo.list_mensajes(db, conv.id)
    turnos = int(ctx.get("diag_turnos") or 0)
    cubiertos = [str(x) for x in (ctx.get("pasos_cubiertos") or []) if str(x).strip()]
    kb = _kb_fragmento(db, org_id, texto)
    forzar = bool(
        es_escape_agente(texto)
        or pide_humano_en_flujo_activo(texto, ctx)
        or pide_humano(texto)
    )

    from app.services.eco_voice import build_contexto_abonado

    extras_ctx: dict[str, str] = {}
    if ctx.get("pppoe_resumen"):
        extras_ctx["pppoe_resumen"] = str(ctx.get("pppoe_resumen") or "")
    if ctx.get("pppoe_triage"):
        extras_ctx["pppoe_triage"] = str(ctx.get("pppoe_triage") or "")

    result = diagnosticar_turno(
        intencion=intencion,
        checklist=checklist,
        historial_mensajes=historial,
        mensaje_cliente=texto,
        turnos_diagnostico=turnos,
        pasos_cubiertos=cubiertos,
        kb_fragmento=kb,
        forzar_agente=forzar,
        contexto_abonado=build_contexto_abonado(
            abonado, org_id=org_id, extras=extras_ctx or None
        ),
    )

    accion = result.get("accion") or "ask"
    mensaje = (result.get("mensaje") or "").strip()
    paso = (result.get("paso_cubierto") or "").strip()
    if paso and paso not in cubiertos:
        cubiertos.append(paso)
    # PON verde: capa óptica OK → no seguir al chequeo del cable amarillo
    if (result.get("motivo") or "") == "pon_verde_enlace_ok":
        for pid in ("luces_los", "cable_fibra", "reinicio_ont"):
            if pid not in cubiertos:
                cubiertos.append(pid)
    ctx["pasos_cubiertos"] = cubiertos
    ctx["diag_turnos"] = turnos + 1
    ctx["paso_idx"] = min(len(cubiertos), max(len(checklist) - 1, 0))
    ctx["ultima_diag_motivo"] = (result.get("motivo") or "")[:200]
    ctx["intencion"] = intencion
    if (result.get("motivo") or "") == "pon_verde_enlace_ok":
        ctx["enlace_optico_ok"] = True
    crepo.set_contexto(conv, ctx)
    db.commit()

    if accion == "escalate":
        from app.services.diagnostico_n1 import _cierra_consulta_facturacion

        if _cierra_consulta_facturacion(texto) or _cliente_desiste_o_resuelto(texto):
            return _cerrar_consulta_resuelta(
                db,
                org_id,
                conv,
                canal=canal,
            )
        tid = _crear_ticket_n2(
            db,
            org_id,
            conv,
            abonado,
            f"Diagnóstico N1 IA: {result.get('motivo') or 'escalate'} ({intencion})",
            intencion=intencion,
            paso_idx=int(ctx.get("paso_idx") or 0),
            ctx=ctx,
        )
        mensaje = _mensaje_cierre_escalamiento(
            tid,
            motivo=str(result.get("motivo") or ""),
            mensaje_ia=mensaje,
            nota_temas=_nota_temas_pendientes(ctx),
            intencion=intencion,
        )
        _enviar_respuesta(db, org_id, conv, mensaje, enviar_externo=_enviar_externo(canal))
        return {
            "ok": True,
            "modo": "espera_agente",
            "conversacion_id": conv.id,
            "respuesta": mensaje,
            "estado": conv.estado,
            "ticket_id": tid,
            "intencion": intencion,
            "diagnostico_ia": True,
        }

    if accion == "resolved":
        conv.estado = "cerrado"
        db.commit()
        if not mensaje or result.get("cierre_calido"):
            mensaje = _mensaje_cierre_calido(_primer_nombre_cliente(abonado))
        _enviar_respuesta(db, org_id, conv, mensaje, enviar_externo=_enviar_externo(canal))
        enviar_encuesta_cierre(
            db, conv, origen=ORIGEN_BOT, enviar_externo=_enviar_externo(canal)
        )
        return {
            "ok": True,
            "modo": "cerrado",
            "conversacion_id": conv.id,
            "respuesta": mensaje,
            "estado": conv.estado,
            "intencion": intencion,
            "diagnostico_ia": True,
        }

    if not mensaje:
        mensaje = "Contame un poco más del problema para seguir el diagnóstico."
    _enviar_respuesta(db, org_id, conv, mensaje, enviar_externo=_enviar_externo(canal))
    return {
        "ok": True,
        "modo": "bot",
        "conversacion_id": conv.id,
        "respuesta": mensaje,
        "estado": conv.estado,
        "intencion": intencion,
        "diagnostico_ia": True,
    }


def procesar_mensaje_entrante(
    db: Session,
    org_id: str,
    *,
    telefono: str,
    texto: str,
    canal: str = "whatsapp",
    wa_id: str = "",
    meta_message_id: str = "",
    usar_llama: bool = True,
    entrada_audio: bool = False,
) -> dict:
    """Procesa un mensaje del cliente. Retorna respuesta del bot o estado agente.

    Si entrada_audio=True y canal=whatsapp, las respuestas del bot de este turno
    se intentan enviar como nota de voz (TTS) con fallback a texto.
    """
    texto = (texto or "").strip()
    if not texto:
        return {"ok": False, "error": "mensaje vacío"}

    mid = (meta_message_id or "").strip()
    if mid and crepo.inbound_meta_ya_procesado(db, org_id, mid):
        logger.warning(
            "Mensaje entrante duplicado omitido canal=%s mid=%s",
            canal,
            mid[:48],
        )
        return {"ok": True, "modo": "duplicado", "meta_message_id": mid[:48]}

    # Voto CSAT sobre conversación cerrada con encuesta pendiente (antes de abrir hilo nuevo)
    try:
        capturado = intentar_capturar_voto(
            db,
            org_id,
            telefono=telefono,
            texto=texto,
            canal=canal,
            wa_id=wa_id,
            meta_message_id=meta_message_id,
            enviar_externo=_enviar_externo(canal),
        )
        if capturado is not None:
            return capturado
    except Exception:
        db.rollback()
        logger.exception("Error capturando voto CSAT canal=%s", canal)

    conv: ConversacionCanal | None = None
    try:
        conv = crepo.get_or_create_conversacion(
            db, org_id, telefono=telefono, canal=canal, wa_id=wa_id
        )
        if (canal or "") == "whatsapp":
            ctx0 = crepo.get_contexto(conv)
            if entrada_audio:
                ctx0["responder_en_audio"] = True
            else:
                ctx0.pop("responder_en_audio", None)
            crepo.set_contexto(conv, ctx0)
            db.commit()
        crepo.add_mensaje(
            db,
            org_id,
            conv.id,
            direccion="in",
            autor="cliente",
            texto=texto,
            meta_message_id=meta_message_id,
        )
    except Exception:
        db.rollback()
        logger.exception(
            "No se pudo persistir mensaje entrante canal=%s tel=%s",
            canal,
            (telefono or "")[:20],
        )
        raise

    # Si ya está con agente o en espera, no responde el bot N1
    if conv.estado in ("con_agente", "espera_agente"):
        if conv.estado == "con_agente":
            return {
                "ok": True,
                "modo": "agente",
                "conversacion_id": conv.id,
                "respuesta": "",
                "estado": conv.estado,
                "ticket_id": conv.ticket_id,
            }
        return _responder_espera_agente(
            db, org_id, conv, texto, canal=canal
        )

    # No reabrir hilos cerrados: si quedó cerrado, pedir uno nuevo (histórico intacto)
    if conv.estado == "cerrado":
        conv = crepo.get_or_create_conversacion(
            db, org_id, telefono=telefono, canal=canal, wa_id=wa_id
        )

    ctx = crepo.get_contexto(conv)
    abonado: Abonado | None = None
    if conv.abonado_id:
        abonado = db.get(Abonado, conv.abonado_id)
    if not abonado:
        abonado = crepo.find_abonado_por_telefono(db, org_id, conv.telefono)

    # Cierre temprano: tras QR/pago o factura, "perfecto/gracias" no debe abrir ticket.
    # No aplica en aviso_deuda (elección pagar vs diagnóstico): ahí «no entiendo» ≠ cierre.
    _intent_ctx = str(ctx.get("intencion") or "").strip()
    if intencion_es_facturacion(_intent_ctx):
        from app.services.diagnostico_n1 import _cierra_consulta_facturacion

        if _cierra_consulta_facturacion(texto) or _cliente_desiste_o_resuelto(texto):
            return _cerrar_consulta_resuelta(
                db,
                org_id,
                conv,
                canal=canal,
            )

    # DNI solo (p. ej. respuesta a «pasame DNI»): identificar antes de frustración/ticket
    if not abonado and _es_solo_dni(texto):
        abonado = _intentar_identificar_por_dni(db, org_id, texto)
        if abonado:
            conv.abonado_id = abonado.id
            if abonado.telefono_e164:
                # No pisar guest phone sintético si no hay tel real — opcional
                pass
            ctx["identificado"] = True
            ctx["dni"] = abonado.dni
            ctx.pop("invitado", None)
            crepo.set_contexto(conv, ctx)
            db.commit()
            nombre = (abonado.nombre or "").split()[0].title() or "ahí"
            estado = (abonado.estado or "").lower()
            pedi_saldo = _mensaje_pedi_saldo_reciente(db, conv.id)
            deuda = str(abonado.deuda_monto or "0").strip() or "0"
            if pedi_saldo:
                baja_nota = (
                    "La cuenta figura «de baja» en el padrón."
                    if estado == "baja"
                    else ""
                )
                resp = (
                    f"Te ubiqué, {nombre}.\n"
                    + mensaje_saldo_padron(deuda, nota_extra=baja_nota)
                )
                ctx["intencion"] = "facturacion"
                ctx["saludo"] = True
                crepo.set_contexto(conv, ctx)
                db.commit()
            elif estado == "baja":
                resp = (
                    f"Te ubiqué, {nombre}: la cuenta figura «de baja» en el padrón. "
                    "Igual puedo ayudarte (reactivación, factura, o un trámite). "
                    "¿Qué necesitás?"
                )
            elif estado in ("corte", "suspendido"):
                from app.services.eco_voice import texto_monto_ars

                resp = (
                    f"Te ubiqué, {nombre}: la cuenta figura «{abonado.estado}». "
                    f"Saldo pendiente {texto_monto_ars(abonado.deuda_monto)}. "
                    "¿Es por reactivar, pagar, o por otra consulta?"
                )
            else:
                resp = (
                    f"Listo {nombre}, ya te identifiqué. "
                    f"{texto_menu_consulta(abonado.servicio)}"
                )
            if not pedi_saldo:
                ctx["saludo"] = True
                ctx["menu_paso"] = "servicio"
                crepo.set_contexto(conv, ctx)
                db.commit()
            _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
                "abonado": crepo.abonado_to_dict(abonado),
            }

    # Ya identificado y manda solo DNI (p. ej. tras un ask erróneo): no re-pedir identificación
    if abonado and _es_solo_dni(texto):
        from app.services.eco_voice import texto_monto_ars, texto_ov_aviso_pago

        deuda = str(abonado.deuda_monto or "0").strip() or "0"
        nombre = (abonado.nombre or "").split()[0].title() or "ahí"
        dni_abo = re.sub(r"\D", "", abonado.dni or "")
        dni_msg = re.sub(r"\D", "", texto or "")
        estado = (abonado.estado or "").lower()
        cortado = estado in ("corte", "cortado", "suspendido", "suspendida")
        aviso = texto_ov_aviso_pago(cortado=cortado)
        if dni_abo and dni_msg and dni_abo != dni_msg:
            resp = (
                f"{nombre}, esa cuenta ya está identificada con otro DNI del padrón. "
                "Si es otra titularidad, pedime un agente. "
                f"Saldo que figura ahora: {texto_monto_ars(deuda)}.\n{aviso}"
            )
        else:
            resp = (
                f"Ya te tenía ubicado, {nombre}. "
                f"{mensaje_saldo_padron(deuda, incluir_ov=False)}\n"
                f"{aviso}\n¿Pudiste cargar el aviso?"
            )
        ctx["intencion"] = "facturacion"
        ctx["identificado"] = True
        crepo.set_contexto(conv, ctx)
        db.commit()
        _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
        return {
            "ok": True,
            "modo": "bot",
            "conversacion_id": conv.id,
            "respuesta": resp,
            "estado": conv.estado,
            "abonado": crepo.abonado_to_dict(abonado),
            "intencion": "facturacion",
        }

    # Incidente masivo por NAS (antes de frustración/ticket/LLM)
    if abonado:
        outage_resp = _talvez_respuesta_outage(
            db, org_id, conv, abonado, ctx, canal=canal, texto=texto
        )
        if outage_resp is not None:
            return outage_resp

    # Frustración / reiteración: solo tras avance N1 real (paso_idx ≥ 2)
    # No aplicar a mensajes que son solo un DNI.
    if not _es_solo_dni(texto) and detecta_frustracion(texto, ctx):
        intent = str(ctx.get("intencion") or conv.servicio_detectado or "general")
        paso = int(ctx.get("paso_idx") or 0)
        tid = _crear_ticket_n2(
            db,
            org_id,
            conv,
            abonado,
            "Reiteración/frustración del abonado sin resolución N1",
            intencion=intent,
            paso_idx=paso,
            ctx=ctx,
        )
        resp = (
            f"Entiendo la molestia. Te derivo con un agente con el historial. "
            f"Ticket {tid}.{_nota_temas_pendientes(ctx)} Quedate en este chat."
        )
        _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
        return {
            "ok": True,
            "modo": "espera_agente",
            "conversacion_id": conv.id,
            "respuesta": resp,
            "estado": conv.estado,
            "ticket_id": tid,
        }

    # Reiteración temprana (mismo síntoma sin progreso): reformular, no ticket
    reiteracion_temprana = misma_queja(texto, ctx) and int(ctx.get("paso_idx") or 0) < 2
    ctx = registrar_queja(ctx, texto)
    crepo.set_contexto(conv, ctx)
    db.commit()

    if reiteracion_temprana:
        intent = str(ctx.get("intencion") or "")
        pb = _playbooks(db)
        if intent and intent in pb:
            pasos = pb[intent]
            idx = max(0, min(int(ctx.get("paso_idx") or 0), len(pasos) - 1))
            base = pasos[idx].pregunta
        else:
            base = (
                "Para ayudarte necesito saber si es internet (fibra, antena o ADSL), "
                "móvil IMOWI, factura/pago u otra consulta."
            )
        resp = f"Para seguir, necesito ese dato. {base}"
        if usar_llama:
            resp = _redactar_con_llama(
                resp,
                f"reiteracion_temprana intencion={intent or 'ninguna'}",
                db=db,
                org_id=org_id,
                consulta=texto,
            )
        _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
        return {
            "ok": True,
            "modo": "bot",
            "conversacion_id": conv.id,
            "respuesta": resp,
            "estado": conv.estado,
            "intencion": intent or None,
        }

    # Escape hatch *agente*, pedido de técnico a mitad de diagnóstico,
    # o 2ª insistencia sin síntoma → ticket.
    # Pedido de humano al inicio SIN síntoma y SIN flujo → menú + CTA *agente*.
    if (
        es_escape_agente(texto)
        or pide_humano_en_flujo_activo(texto, ctx)
        or (
            pide_humano(texto)
            and not contiene_sintoma_canal(texto)
            and int(ctx.get("pidio_humano") or 0) >= 1
        )
    ):
        intent = str(ctx.get("intencion") or conv.servicio_detectado or "general")
        tid = _crear_ticket_n2(
            db,
            org_id,
            conv,
            abonado,
            "Cliente solicitó agente/técnico",
            intencion=intent,
            paso_idx=int(ctx.get("paso_idx") or ctx.get("diag_turnos") or 0),
            ctx=ctx,
        )
        resp = (
            f"Dale, te derivo con un agente y le paso lo que charlamos. "
            f"Ticket {tid}.{_nota_temas_pendientes(ctx)} Quedate en este chat."
        )
        _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
        return {
            "ok": True,
            "modo": "espera_agente",
            "conversacion_id": conv.id,
            "respuesta": resp,
            "estado": conv.estado,
            "ticket_id": tid,
        }

    if pide_humano(texto) and not contiene_sintoma_canal(texto):
        ctx["pidio_humano"] = int(ctx.get("pidio_humano") or 0) + 1
        crepo.set_contexto(conv, ctx)
        db.commit()
        resp = (
            "Puedo ayudarte yo primero (internet, móvil IMOWI o factura/pago). "
            "Contame qué te pasa. Si preferís una persona, escribí *agente*."
        )
        if usar_llama:
            resp = _redactar_con_llama(
                resp,
                "pedido_humano_sin_sintoma",
                db=db,
                org_id=org_id,
                consulta=texto,
            )
        _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
        return {
            "ok": True,
            "modo": "bot",
            "conversacion_id": conv.id,
            "respuesta": resp,
            "estado": conv.estado,
        }

    # Identificación — sin abonado: pedir DNI (WA) o derivar visitante a agente
    if not abonado:
        dni = _extraer_dni(texto)
        abonado = _intentar_identificar_por_dni(db, org_id, texto)
        if abonado:
            conv.abonado_id = abonado.id
            ctx["identificado"] = True
            ctx["dni"] = abonado.dni
            ctx.pop("invitado", None)
            ctx.pop("visitante", None)
            ctx.pop("cola_prioridad", None)
            crepo.set_contexto(conv, ctx)
            db.commit()
            outage_resp = _talvez_respuesta_outage(
                db, org_id, conv, abonado, ctx, canal=canal, texto=texto
            )
            if outage_resp is not None:
                return outage_resp

        if not abonado:
            # Ya enviaron un DNI/socio y no hay match → visitante (sin repreguntar)
            if dni:
                ctx["dni_intentado"] = dni
                crepo.set_contexto(conv, ctx)
                db.commit()
                return _derivar_visitante(
                    db,
                    org_id,
                    conv,
                    canal=canal,
                    ctx=ctx,
                    motivo="dni_no_encontrado",
                )

            # WhatsApp: una chance de DNI antes de derivar
            if _enviar_externo(canal) and not ctx.get("pidio_dni") and not ctx.get("invitado"):
                ctx["pidio_dni"] = True
                crepo.set_contexto(conv, ctx)
                db.commit()
                resp = (
                    "Hola, soy la asistente de la Cooperativa Batán. "
                    "Para ayudarte, enviame tu DNI o número de socio. "
                    "Si preferís, escribí *agente*."
                )
                if usar_llama:
                    resp = _redactar_con_llama(
                        resp,
                        f"tel={conv.telefono}",
                        db=db,
                        org_id=org_id,
                        consulta=texto,
                    )
                _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
                return {
                    "ok": True,
                    "modo": "bot",
                    "conversacion_id": conv.id,
                    "respuesta": resp,
                    "estado": conv.estado,
                }

            return _derivar_visitante(
                db,
                org_id,
                conv,
                canal=canal,
                ctx=ctx,
                motivo="visitante_sin_cuenta",
            )

    if abonado:
        conv.abonado_id = abonado.id
        if not ctx.get("saludo"):
            ctx["saludo"] = True
            ctx["menu_paso"] = "servicio"
            ctx.pop("invitado", None)
            ctx.pop("visitante", None)
            ctx.pop("cola_prioridad", None)
            crepo.set_contexto(conv, ctx)
            db.commit()
            saludo = (
                f"Hola {abonado.nombre.split()[0]}, te identifiqué correctamente. "
                f"{texto_menu_consulta(abonado.servicio)}"
            )
            if usar_llama:
                saludo = _redactar_con_llama(
                    saludo,
                    f"abonado={abonado.nombre} estado={abonado.estado} deuda={abonado.deuda_monto}",
                    db=db,
                    org_id=org_id,
                    consulta=texto,
                )
            _enviar_respuesta(db, org_id, conv, saludo, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": saludo,
                "estado": conv.estado,
                "abonado": crepo.abonado_to_dict(abonado),
            }

    # Saldo/pago/OV con cuenta identificada: respuesta fija (sin LLM).
    if abonado:
        from app.services.diagnostico_n1 import (
            _cliente_consulta_saldo,
            _cliente_pide_oficina_virtual,
            _cliente_pide_pagar,
        )
        from app.services.eco_voice import PLANTILLA_PAGO_QR

        deuda = str(abonado.deuda_monto or "0").strip() or "0"
        nota_baja = (
            "La cuenta figura «de baja» en el padrón."
            if (abonado.estado or "").lower() == "baja"
            else ""
        )

        if _cliente_pide_oficina_virtual(texto) or _cliente_pide_pagar(texto):
            resp = (
                f"{mensaje_saldo_padron(deuda, incluir_ov=False, nota_extra=nota_baja)}\n"
                f"{PLANTILLA_PAGO_QR}"
            )
            ctx["intencion"] = "facturacion"
            ctx["saludo"] = True
            ctx.pop("invitado", None)
            crepo.set_contexto(conv, ctx)
            db.commit()
            _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
                "abonado": crepo.abonado_to_dict(abonado),
                "intencion": "facturacion",
            }

        if _cliente_consulta_saldo(texto):
            resp = mensaje_saldo_padron(deuda, nota_extra=nota_baja)
            ctx["intencion"] = "facturacion"
            ctx["saludo"] = True
            ctx.pop("invitado", None)
            crepo.set_contexto(conv, ctx)
            db.commit()
            _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
                "abonado": crepo.abonado_to_dict(abonado),
                "intencion": "facturacion",
            }

    # Corte por deuda automático si aplica
    intencion = ctx.get("intencion") or ""
    servicio_abo = abonado.servicio if abonado else ""

    # Menú post-ID: servicio → (móvil) técnico/comercial/administrativo
    if abonado and ctx.get("menu_paso"):
        menu_out = _manejar_menu_consulta_n1(
            db,
            org_id,
            conv,
            abonado,
            texto,
            canal=canal,
            ctx=ctx,
            usar_llama=usar_llama,
        )
        if menu_out is not None:
            return menu_out

    # Saludo corto: menú según padrón, sin deuda ni diagnóstico
    if es_saludo_solo(texto) and intencion in ("", "general"):
        ctx["intencion"] = "general"
        ctx["saludo"] = True
        ctx["menu_paso"] = "servicio"
        crepo.set_contexto(conv, ctx)
        db.commit()
        resp = f"¡Hola! {texto_menu_consulta(servicio_abo)}"
        _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
        return {
            "ok": True,
            "modo": "bot",
            "conversacion_id": conv.id,
            "respuesta": resp,
            "estado": conv.estado,
            "intencion": "general",
            "abonado": crepo.abonado_to_dict(abonado) if abonado else None,
        }

    # Aviso de deuda antes de diagnóstico técnico: esperar elección pago vs seguir
    if intencion == "aviso_deuda":
        if _debe_explicar_sin_internet(
            abonado, texto, str(ctx.get("intencion_tecnica_pendiente") or "")
        ):
            _reset_ctx_diagnostico(ctx)
            ctx["intencion"] = "general"
            crepo.set_contexto(conv, ctx)
            db.commit()
            resp = texto_sin_internet_contratado(servicio_abo)
            _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
                "intencion": "general",
            }
        # "No" / "funciona todo bien" / desiste → cerrar sin loop
        if _cliente_salir_aviso_deuda(texto):
            _reset_ctx_diagnostico(ctx)
            crepo.set_contexto(conv, ctx)
            db.commit()
            return _cerrar_consulta_resuelta(
                db,
                org_id,
                conv,
                canal=canal,
                nota_ticket=(
                    "[Abonado] Declínó aviso deuda / indicó que no necesita seguir: "
                    f"{(texto or '').strip()[:200]}"
                ),
            )
        eleccion = _elige_pago_o_tecnico(texto)
        pendiente = str(ctx.get("intencion_tecnica_pendiente") or "internet")
        if eleccion is None:
            t_low = (texto or "").lower()
            if any(
                k in t_low
                for k in (
                    "no entiendo",
                    "no te entiendo",
                    "no comprendo",
                    "qué",
                    "que?",
                    "repetí",
                    "repite",
                    "otra vez",
                )
            ):
                resp = (
                    "Perdón, te lo digo más simple: tenés dos opciones.\n"
                    "1) *Pagar* el saldo pendiente (te paso el link/QR).\n"
                    "2) *Seguir* con el diagnóstico del servicio (internet/móvil).\n"
                    "¿Cuál preferís: pagar o seguir con el diagnóstico?"
                )
            else:
                resp = (
                    "Decime cuál preferís: ¿te ayudo a pagar el saldo pendiente, "
                    "o seguimos con el diagnóstico del servicio?"
                )
            _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
                "intencion": "aviso_deuda",
            }
        if eleccion == "pago":
            from app.services.eco_voice import PLANTILLA_PAGO_QR

            deuda = str(abonado.deuda_monto or "0") if abonado else "0"
            resp = (
                f"{mensaje_saldo_padron(deuda, incluir_ov=False)}\n{PLANTILLA_PAGO_QR}"
            )
            ctx["intencion"] = "corte_deuda"
            ctx["paso_idx"] = 0
            ctx["diag_turnos"] = 0
            ctx["pasos_cubiertos"] = []
            # Conservar el tema técnico por si vuelve después
            ctx["temas_pendientes"] = list(
                dict.fromkeys(
                    list(ctx.get("temas_pendientes") or [])
                    + (["tecnico"] if _intencion_es_tecnica(pendiente) else [])
                )
            )
            crepo.set_contexto(conv, ctx)
            db.commit()
            _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
                "intencion": "corte_deuda",
            }
        # Seguir técnico
        intencion = pendiente if _intencion_es_tecnica(pendiente) else "general"
        intencion = _intencion_compatible_padron(intencion, abonado, texto)
        if _debe_explicar_sin_internet(abonado, texto, intencion):
            ctx["intencion"] = "general"
            ctx.pop("intencion_tecnica_pendiente", None)
            crepo.set_contexto(conv, ctx)
            db.commit()
            resp = texto_sin_internet_contratado(servicio_abo)
            _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
                "intencion": "general",
            }
        ctx["intencion"] = intencion
        ctx["paso_idx"] = 0
        ctx["diag_turnos"] = 0
        ctx["pasos_cubiertos"] = []
        ctx.pop("intencion_tecnica_pendiente", None)
        conv.servicio_detectado = intencion
        crepo.set_contexto(conv, ctx)
        db.commit()
        diag = _aplicar_diagnostico_ia(
            db,
            org_id,
            conv,
            abonado,
            texto,
            canal=canal,
            ctx=ctx,
            intencion=intencion,
            usar_llama=usar_llama,
        )
        if diag is not None:
            return diag
        pb = _playbooks(db)
        pasos = pb.get(intencion) or pb["general"]
        pregunta = pasos[0].pregunta if pasos else "Contame qué te pasa con el servicio."
        if usar_llama:
            pregunta = _redactar_con_llama(
                pregunta,
                f"intencion={intencion} post_aviso_deuda=1",
                db=db,
                org_id=org_id,
                consulta=texto,
            )
        _enviar_respuesta(db, org_id, conv, pregunta, enviar_externo=_enviar_externo(canal))
        return {
            "ok": True,
            "modo": "bot",
            "conversacion_id": conv.id,
            "respuesta": pregunta,
            "estado": conv.estado,
            "intencion": intencion,
        }

    # Doble tema (internet + factura): esperar elección de prioridad
    if intencion == "multi_tema":
        elegida = resolver_prioridad_tema(texto)
        if not elegida:
            resp = (
                "Decime por cuál empezamos: ¿el internet o el aumento de la factura?"
            )
            _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
                "intencion": "multi_tema",
            }
        original = str(ctx.get("texto_multi_tema") or texto)
        intent = intencion_desde_tema(elegida, original)
        pendientes = [t for t in (ctx.get("temas_pendientes") or []) if t != elegida]
        ctx["intencion"] = intent
        ctx["prioridad_elegida"] = elegida
        ctx["temas_pendientes"] = pendientes
        ctx["paso_idx"] = 0
        ctx["diag_turnos"] = 0
        ctx["pasos_cubiertos"] = []
        conv.servicio_detectado = intent
        crepo.set_contexto(conv, ctx)
        db.commit()
        if (
            abonado
            and _deuda_positiva(abonado)
            and _intencion_es_tecnica(intent)
            and not ctx.get("aviso_deuda_ofrecido")
        ):
            ctx["intencion"] = "aviso_deuda"
            ctx["intencion_tecnica_pendiente"] = intent
            ctx["aviso_deuda_ofrecido"] = True
            crepo.set_contexto(conv, ctx)
            db.commit()
            resp = _texto_aviso_deuda_tecnico(abonado, intent)
            _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
                "intencion": "aviso_deuda",
            }
        # Diagnosticar con el mensaje original (tenía ambos temas), no solo "internet"/"factura"
        diag = _aplicar_diagnostico_ia(
            db,
            org_id,
            conv,
            abonado,
            original,
            canal=canal,
            ctx=ctx,
            intencion=intent,
            usar_llama=usar_llama,
        )
        if diag is not None:
            return diag
        intencion = intent
        # Continúa abajo si el diagnóstico IA no aplicó

    if not intencion:
        temas = detectar_temas_duales(texto)
        if len(temas) >= 2:
            ctx["intencion"] = "multi_tema"
            ctx["temas_pendientes"] = temas
            ctx["texto_multi_tema"] = texto[:500]
            ctx["paso_idx"] = 0
            ctx["diag_turnos"] = 0
            ctx["pasos_cubiertos"] = []
            crepo.set_contexto(conv, ctx)
            db.commit()
            resp = (
                "Veo dos cosas: la conexión y el tema de la factura. "
                "¿Arrancamos por el internet o por el aumento?"
            )
            # IMOWI / móvil + factura
            if any(k in texto.lower() for k in ("imowi", "móvil", "movil", "celular")):
                resp = (
                    "Veo dos cosas: el servicio de telefonía móvil y el tema de la factura. "
                    "¿Arrancamos por el móvil o por el aumento?"
                )
            _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
                "intencion": "multi_tema",
            }
        intencion = clasificar_intencion(texto, servicio_abo)
        if _debe_explicar_sin_internet(abonado, texto, intencion):
            ctx["intencion"] = "general"
            ctx["paso_idx"] = 0
            ctx["diag_turnos"] = 0
            ctx["pasos_cubiertos"] = []
            crepo.set_contexto(conv, ctx)
            db.commit()
            resp = texto_sin_internet_contratado(servicio_abo)
            _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
                "intencion": "general",
            }
        if _deberia_priorizar_corte_deuda(abonado, texto, intencion):
            intencion = "corte_deuda"
        paso_inicial = 0
        # Ya dijo «sin tono» → no re-preguntar tono
        if intencion == "telefono_fija" and any(
            k in texto.lower() for k in ("sin tono", "no tiene tono", "no hay tono")
        ):
            paso_inicial = 1
        ctx["intencion"] = intencion
        ctx["paso_idx"] = paso_inicial
        ctx["diag_turnos"] = 0
        ctx["pasos_cubiertos"] = []
        conv.servicio_detectado = (
            intencion
            if intencion in ("internet", "internet_radio", "internet_adsl", "movil")
            else (servicio_abo or intencion)
        )
        # Con deuda: avisar una vez y dejar elegir pagar vs diagnóstico técnico
        if (
            abonado
            and _deuda_positiva(abonado)
            and _intencion_es_tecnica(intencion)
            and not ctx.get("aviso_deuda_ofrecido")
            and intencion != "corte_deuda"
        ):
            ctx["intencion"] = "aviso_deuda"
            ctx["intencion_tecnica_pendiente"] = intencion
            ctx["aviso_deuda_ofrecido"] = True
            crepo.set_contexto(conv, ctx)
            db.commit()
            resp = _texto_aviso_deuda_tecnico(abonado, intencion)
            _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
                "intencion": "aviso_deuda",
            }
        crepo.set_contexto(conv, ctx)
        db.commit()
        pb = _playbooks(db)
        pasos = pb.get(intencion) or pb["general"]
        idx = max(0, min(paso_inicial, len(pasos) - 1))
        pregunta = pasos[idx].pregunta
        if intencion == "general":
            pregunta = texto_menu_consulta(servicio_abo)
        if intencion == "corte_deuda":
            # Siempre guía QR primero (evita playbooks admin sin Fiserv / rewrites).
            from app.services.eco_voice import PLANTILLA_PAGO_QR

            if abonado:
                from app.services.eco_voice import texto_monto_ars

                pregunta = (
                    f"Tu cuenta figura con estado «{abonado.estado}» "
                    f"y saldo pendiente {texto_monto_ars(abonado.deuda_monto)}. "
                    f"{PLANTILLA_PAGO_QR}"
                )
            else:
                # Invitado: no inventar saldo ni soltar QR sin cuenta.
                pregunta = (
                    "En modo invitado no veo tu cuenta. "
                    "Pasame tu DNI (solo el número) y te digo si hay saldo pendiente "
                    "y cómo abonar."
                )
            _enviar_respuesta(db, org_id, conv, pregunta, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": pregunta,
                "estado": conv.estado,
                "intencion": intencion,
            }
        # Facturación y técnicos: diagnóstico IA (playbook = checklist de indagación).
        diag = _aplicar_diagnostico_ia(
            db,
            org_id,
            conv,
            abonado,
            texto,
            canal=canal,
            ctx=ctx,
            intencion=intencion,
            usar_llama=usar_llama,
        )
        if diag is not None:
            return diag
        usar_llm_paso = usar_llama
        if usar_llm_paso:
            pregunta = _redactar_con_llama(
                pregunta,
                f"intencion={intencion}",
                db=db,
                org_id=org_id,
                consulta=texto,
            )
        _enviar_respuesta(db, org_id, conv, pregunta, enviar_externo=_enviar_externo(canal))
        return {
            "ok": True,
            "modo": "bot",
            "conversacion_id": conv.id,
            "respuesta": pregunta,
            "estado": conv.estado,
            "intencion": intencion,
        }

    # Refinar internet → radio / ADSL tras la pregunta de tipo de acceso
    # Si aclara que NO tiene fijo y solo móvil/IMOWI → saltar a playbook móvil
    if intencion_es_internet(intencion):
        if _debe_explicar_sin_internet(abonado, texto, intencion):
            ctx["intencion"] = "general"
            ctx["paso_idx"] = 0
            ctx["diag_turnos"] = 0
            ctx["pasos_cubiertos"] = []
            crepo.set_contexto(conv, ctx)
            db.commit()
            resp = texto_sin_internet_contratado(servicio_abo)
            _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
                "intencion": "general",
            }
        if declara_solo_movil_sin_fijo(texto, servicio_abo):
            intencion = clasificar_intencion(texto, "movil")
            if not intencion.startswith("movil"):
                intencion = "movil"
            ctx["intencion"] = intencion
            ctx["paso_idx"] = 0
            ctx["diag_turnos"] = 0
            ctx["pasos_cubiertos"] = []
            ctx["correccion_solo_movil"] = True
            conv.servicio_detectado = "movil"
            crepo.set_contexto(conv, ctx)
            db.commit()
            pb = _playbooks(db)
            pasos = pb.get(intencion) or pb["general"]
            diag = _aplicar_diagnostico_ia(
                db,
                org_id,
                conv,
                abonado,
                texto,
                canal=canal,
                ctx=ctx,
                intencion=intencion,
                usar_llama=usar_llama,
            )
            if diag is not None:
                return diag
            pregunta = pasos[0].pregunta if pasos else (
                "Dale, vamos con el servicio de telefonía móvil. ¿Qué te pasa: sin señal, sin datos o no podés llamar?"
            )
            if usar_llama:
                pregunta = _redactar_con_llama(
                    pregunta,
                    f"intencion={intencion} correccion_solo_movil=1",
                    db=db,
                    org_id=org_id,
                    consulta=texto,
                )
            _enviar_respuesta(db, org_id, conv, pregunta, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": pregunta,
                "estado": conv.estado,
                "intencion": intencion,
            }

    if intencion == "internet":
        refinada = refinar_intencion_internet(texto)
        if refinada:
            intencion = refinada
            ctx["intencion"] = intencion
            ctx["paso_idx"] = 0
            ctx["diag_turnos"] = 0
            ctx["pasos_cubiertos"] = []
            conv.servicio_detectado = intencion
            crepo.set_contexto(conv, ctx)
            db.commit()
            pb = _playbooks(db)
            pasos = pb.get(intencion) or pb["general"]
            diag = _aplicar_diagnostico_ia(
                db,
                org_id,
                conv,
                abonado,
                texto,
                canal=canal,
                ctx=ctx,
                intencion=intencion,
                usar_llama=usar_llama,
            )
            if diag is not None:
                return diag
            pregunta = pasos[0].pregunta
            if usar_llama:
                pregunta = _redactar_con_llama(
                    pregunta,
                    f"intencion={intencion}",
                    db=db,
                    org_id=org_id,
                    consulta=texto,
                )
            _enviar_respuesta(db, org_id, conv, pregunta, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": pregunta,
                "estado": conv.estado,
                "intencion": intencion,
            }

    # Si estaba en general y el usuario elige servicio, reclasificar
    if intencion == "general":
        if _debe_explicar_sin_internet(abonado, texto):
            resp = texto_sin_internet_contratado(servicio_abo)
            _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
                "intencion": "general",
            }
        nueva = clasificar_intencion(texto, servicio_abo)
        if _debe_explicar_sin_internet(abonado, texto, nueva):
            resp = texto_sin_internet_contratado(servicio_abo)
            _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
                "intencion": "general",
            }
        if nueva != "general":
            intencion = nueva
            ctx["intencion"] = intencion
            ctx["paso_idx"] = 0
            ctx["diag_turnos"] = 0
            ctx["pasos_cubiertos"] = []
            if (
                abonado
                and _deuda_positiva(abonado)
                and _intencion_es_tecnica(intencion)
                and not ctx.get("aviso_deuda_ofrecido")
            ):
                ctx["intencion"] = "aviso_deuda"
                ctx["intencion_tecnica_pendiente"] = intencion
                ctx["aviso_deuda_ofrecido"] = True
                crepo.set_contexto(conv, ctx)
                db.commit()
                resp = _texto_aviso_deuda_tecnico(abonado, intencion)
                _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
                return {
                    "ok": True,
                    "modo": "bot",
                    "conversacion_id": conv.id,
                    "respuesta": resp,
                    "estado": conv.estado,
                    "intencion": "aviso_deuda",
                }
            crepo.set_contexto(conv, ctx)
            db.commit()
            pb = _playbooks(db)
            pasos = pb.get(intencion) or pb["general"]
            diag = _aplicar_diagnostico_ia(
                db,
                org_id,
                conv,
                abonado,
                texto,
                canal=canal,
                ctx=ctx,
                intencion=intencion,
                usar_llama=usar_llama,
            )
            if diag is not None:
                return diag
            pregunta = pasos[0].pregunta
            if usar_llama:
                pregunta = _redactar_con_llama(
                    pregunta,
                    f"intencion={intencion}",
                    db=db,
                    org_id=org_id,
                    consulta=texto,
                )
            _enviar_respuesta(db, org_id, conv, pregunta, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": pregunta,
                "estado": conv.estado,
                "intencion": intencion,
            }

    # Saludo corto: no avanzar el playbook (evita agotar pasos con "Hola")
    if es_saludo_corto(texto):
        pb = _playbooks(db)
        pasos = pb.get(intencion) or pb["general"]
        paso_idx = int(ctx.get("paso_idx") or 0)
        paso_idx = max(0, min(paso_idx, max(len(pasos) - 1, 0)))
        pregunta = pasos[paso_idx].pregunta if pasos else (
            "¿En qué te puedo ayudar: internet, móvil, factura u otra consulta?"
        )
        resp = f"¡Hola! {pregunta}"
        if usar_llama:
            resp = _redactar_con_llama(
                resp,
                f"saludo intencion={intencion}",
                db=db,
                org_id=org_id,
                consulta=texto,
            )
        _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
        return {
            "ok": True,
            "modo": "bot",
            "conversacion_id": conv.id,
            "respuesta": resp,
            "estado": conv.estado,
            "intencion": intencion,
        }

    # Consulta nueva a mitad de flujo: solo saltar a OTRO dominio específico.
    # Nunca degradar a "general" (eso reinicia con el saludo del menú).
    if parece_consulta_nueva(texto) and intencion and intencion != "general":
        nueva = clasificar_intencion(texto, servicio_abo)
        if nueva and nueva != intencion and nueva != "general":
            intencion = nueva
            ctx["intencion"] = intencion
            ctx["paso_idx"] = 0
            ctx["diag_turnos"] = 0
            ctx["pasos_cubiertos"] = []
            crepo.set_contexto(conv, ctx)
            db.commit()
            pb = _playbooks(db)
            pasos = pb.get(intencion) or pb["general"]
            diag = _aplicar_diagnostico_ia(
                db,
                org_id,
                conv,
                abonado,
                texto,
                canal=canal,
                ctx=ctx,
                intencion=intencion,
                usar_llama=usar_llama,
            )
            if diag is not None:
                return diag
            pregunta = pasos[0].pregunta
            if usar_llama:
                pregunta = _redactar_con_llama(
                    pregunta,
                    f"intencion={intencion} reclasificado=1",
                    db=db,
                    org_id=org_id,
                    consulta=texto,
                )
            _enviar_respuesta(db, org_id, conv, pregunta, enviar_externo=_enviar_externo(canal))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": pregunta,
                "estado": conv.estado,
                "intencion": intencion,
            }

    # Continuación: técnicos con diagnóstico IA (sin sí/no rígido del playbook)
    diag = _aplicar_diagnostico_ia(
        db,
        org_id,
        conv,
        abonado,
        texto,
        canal=canal,
        ctx=ctx,
        intencion=intencion,
        usar_llama=usar_llama,
    )
    if diag is not None:
        return diag

    # Corte/pago o factura: "sí, perfecto, gracias" cierra (no avanzar playbook ni escalar)
    if intencion_es_facturacion(intencion):
        from app.services.diagnostico_n1 import _cierra_consulta_facturacion

        if _cierra_consulta_facturacion(texto) or _cliente_desiste_o_resuelto(texto):
            return _cerrar_consulta_resuelta(
                db,
                org_id,
                conv,
                canal=canal,
            )

    pb = _playbooks(db)
    pasos = pb.get(intencion) or pb["general"]
    paso_idx = int(ctx.get("paso_idx") or 0)
    paso_idx = max(0, min(paso_idx, max(len(pasos) - 1, 0)))
    paso_actual = pasos[paso_idx] if pasos else None
    veredicto = respuesta_paso_ok(texto)

    def _preguntar(idx: int, *, prefijo: str = "") -> dict:
        pregunta = pasos[idx].pregunta
        if prefijo:
            pregunta = f"{prefijo}{pregunta}"
        # Pagos/QR en corte: plantilla fija. Facturación ya va por diagnóstico IA.
        if usar_llama and intencion != "corte_deuda":
            pregunta = _redactar_con_llama(
                pregunta,
                f"paso={idx} intencion={intencion}",
                db=db,
                org_id=org_id,
                consulta=texto,
            )
        _enviar_respuesta(db, org_id, conv, pregunta, enviar_externo=_enviar_externo(canal))
        return {
            "ok": True,
            "modo": "bot",
            "conversacion_id": conv.id,
            "respuesta": pregunta,
            "estado": conv.estado,
            "intencion": intencion,
        }

    def _escalar(motivo: str) -> dict:
        from app.services.diagnostico_n1 import _cierra_consulta_facturacion

        # Nunca abrir ticket si el abonado está cerrando (gracias/perfecto/listo)
        if _cierra_consulta_facturacion(texto) or _cliente_desiste_o_resuelto(texto):
            return _cerrar_consulta_resuelta(
                db,
                org_id,
                conv,
                canal=canal,
            )
        tid = _crear_ticket_n2(
            db,
            org_id,
            conv,
            abonado,
            motivo,
            intencion=intencion,
            paso_idx=paso_idx,
            ctx=ctx,
        )
        resp = _mensaje_cierre_escalamiento(
            tid,
            motivo=motivo,
            mensaje_ia="",
            nota_temas=_nota_temas_pendientes(ctx),
            intencion=intencion,
        )
        if usar_llama:
            resp = _redactar_con_llama(
                resp,
                f"escalamiento intencion={intencion} paso={paso_idx}",
                db=db,
                org_id=org_id,
                consulta=texto,
            )
            if tid not in resp:
                resp = f"{resp.rstrip('.')} Ticket {tid}."
        _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
        return {
            "ok": True,
            "modo": "espera_agente",
            "conversacion_id": conv.id,
            "respuesta": resp,
            "estado": conv.estado,
            "ticket_id": tid,
            "intencion": intencion,
        }

    # El abonado dice que ya quedó resuelto
    if indica_resuelto(texto) or _cliente_desiste_o_resuelto(texto):
        return _cerrar_consulta_resuelta(
            db,
            org_id,
            conv,
            canal=canal,
        )

    # Confirmó derivación en el último paso tipo "¿Querés que te derive?"
    if veredicto is True and es_paso_derivacion(paso_actual):
        return _escalar(f"Abonado aceptó derivación en playbook {intencion}")

    # En guía de pago/QR, un "sí/perfecto" = pudo pagar → cerrar (no pedir DNI ni derivar)
    if (
        veredicto is True
        and paso_actual
        and (paso_actual.id or "")
        in ("medios_pago_qr", "guia_pago_si_aplica", "guia_pago")
    ):
        return _cerrar_consulta_resuelta(
            db,
            org_id,
            conv,
            canal=canal,
        )
    # Sigue fallando → siguiente paso de diagnóstico (no escalar en el primero)
    if veredicto is False:
        if paso_idx >= len(pasos) - 1:
            if es_paso_derivacion(paso_actual):
                # Última pregunta de derivación respondida con "no"
                resp = (
                    "Entendido, no te derivo por ahora. Si más adelante necesitás "
                    "ayuda o querés hablar con un agente, escribí *agente*."
                )
                _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
                return {
                    "ok": True,
                    "modo": "bot",
                    "conversacion_id": conv.id,
                    "respuesta": resp,
                    "estado": conv.estado,
                }
            return _escalar(
                f"Playbook {intencion} agotado sin resolución en paso {paso_idx}"
            )
        paso_idx += 1
        ctx["paso_idx"] = paso_idx
        crepo.set_contexto(conv, ctx)
        db.commit()
        return _preguntar(paso_idx)

    # Afirmación / paso cumplido → avanzar en el playbook
    if veredicto is True:
        paso_idx += 1
        ctx["paso_idx"] = paso_idx
        crepo.set_contexto(conv, ctx)
        db.commit()
        if paso_idx >= len(pasos):
            conv.estado = "cerrado"
            db.commit()
            resp = (
                "¡Genial! Parece resuelto en N1. Si vuelve el problema, escribime de nuevo. "
                "¡Gracias!"
            )
            _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
            enviar_encuesta_cierre(
                db, conv, origen=ORIGEN_BOT, enviar_externo=_enviar_externo(canal)
            )
            return {
                "ok": True,
                "modo": "cerrado",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
            }
        return _preguntar(paso_idx)

    # Respuesta informativa / ambigua: avanzar si no es sí/no cerrado,
    # para recolectar datos; nunca escalar solo por estar en el último paso.
    if paso_idx < len(pasos) - 1 and not es_paso_derivacion(paso_actual):
        paso_idx += 1
        ctx["paso_idx"] = paso_idx
        # Guardar pista del mensaje para el contexto
        ctx["ultima_respuesta_libre"] = (texto or "")[:240]
        crepo.set_contexto(conv, ctx)
        db.commit()
        return _preguntar(paso_idx)

    pregunta = pasos[min(paso_idx, len(pasos) - 1)].pregunta
    resp = (
        "Para seguir ayudándote necesito un poco más de detalle. "
        f"{pregunta}"
    )
    if usar_llama:
        resp = _redactar_con_llama(
            resp,
            f"paso={paso_idx} intencion={intencion} ambiguo=1",
            db=db,
            org_id=org_id,
            consulta=texto,
        )
    _enviar_respuesta(db, org_id, conv, resp, enviar_externo=_enviar_externo(canal))
    return {
        "ok": True,
        "modo": "bot",
        "conversacion_id": conv.id,
        "respuesta": resp,
        "estado": conv.estado,
    }
