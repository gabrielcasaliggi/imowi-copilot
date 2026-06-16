"""Normalizador híbrido: reglas + contexto del último bot → TurnUnderstanding."""

from __future__ import annotations

import re
from typing import Any

from app.domain.conversacion import (
    AFIRMACION_CORTA,
    mensaje_indica_persistencia_parcial,
    mensaje_indica_resolucion_real,
    operador_confirmo_persistencia_explicita,
    usuario_confirmo_ticket,
)
from app.domain.turn_understanding import (
    HechosTurno,
    IntencionTurno,
    PreguntaPendiente,
    TurnUnderstanding,
)
from app.services.interprete_conversacional import (
    _es_pregunta,
    detectar_intencion_normalizada,
    extraer_hechos_normalizados,
)


def _ultimo_mensaje(historial: list[dict], rol: str) -> str:
    for m in reversed(historial):
        if m.get("rol") == rol:
            return (m.get("contenido") or "").strip()
    return ""


def inferir_pregunta_pendiente(ultimo_bot: str, *, flujo_paso_id: str = "") -> PreguntaPendiente:
    """Qué pregunta cerrada hizo el bot en el turno anterior."""
    bot = (ultimo_bot or "").lower()
    if not bot:
        return PreguntaPendiente.NINGUNA

    if any(
        p in bot
        for p in (
            "problema persiste",
            "sigue con",
            "sigue teniendo",
            "persiste después",
            "persiste despues",
            "confirmar que el problema",
            "confirmás que el problema",
            "confirmas que el problema",
        )
    ):
        return PreguntaPendiente.CONFIRMAR_PERSISTENCIA

    if any(
        p in bot
        for p in (
            "registrar un ticket",
            "registre un ticket",
            "dejar cargado",
            "confirmás que",
            "confirmas que",
            "querés que lo deje",
            "quieres que lo deje",
        )
    ) and "ticket" in bot:
        return PreguntaPendiente.CONFIRMAR_TICKET

    if flujo_paso_id == "sms_ticket_carrier" or (
        "carrier" in bot and any(p in bot for p in ("remitente", "horario", "escalar"))
    ):
        return PreguntaPendiente.APORTAR_DATOS_ESCALAMIENTO

    if "llamada" in bot and any(p in bot for p in ("prueba", "hacer y recibir", "puede llamar")):
        return PreguntaPendiente.INFORMAR_PRUEBA

    if any(p in bot for p in ("una sola zona", "varias ubicaciones", "varias zonas")):
        return PreguntaPendiente.INFORMAR_ALCANCE

    if "jsc" in bot or "modo avión" in bot or "modo avion" in bot or "reinici" in bot or "apn" in bot:
        return PreguntaPendiente.CONFIRMAR_PASO

    if any(p in bot for p in ("resuelto", "quedó resuelto", "mismo inconveniente")):
        return PreguntaPendiente.CONFIRMAR_RESOLUCION

    return PreguntaPendiente.NINGUNA


def _es_afirmacion_corta(msg: str) -> bool:
    t = (msg or "").lower().strip().rstrip(".!?")
    if not t:
        return False
    if t in AFIRMACION_CORTA:
        return True
    return bool(re.fullmatch(r"(s[ií]|sip|dale|ok|okay|confirmo|de acuerdo|correcto|exacto)", t))


def _es_negacion_corta(msg: str) -> bool:
    t = (msg or "").lower().strip().rstrip(".!?")
    return t in ("no", "nop", "nope", "nah", "negativo")


def _detecta_solicitud_ticket(msg: str) -> bool:
    t = (msg or "").lower()
    if not _es_pregunta(msg):
        return False
    return any(
        p in t
        for p in (
            "ticket",
            "reclamo",
            "registrar",
            "registralo",
            "regístralo",
            "generar",
            "generá",
            "crear",
            "creá",
            "cargar",
            "realizar el ticket",
            "hacer el ticket",
        )
    )


def _detecta_persistencia_semantica(msg: str) -> bool:
    t = (msg or "").lower()
    if operador_confirmo_persistencia_explicita(t):
        return True
    if mensaje_indica_persistencia_parcial(t):
        return True
    if any(p in t for p in ("persiste", "persisten", "sigue igual", "sigue sin", "no anda", "no funciona")):
        return True
    if re.search(r"\b(s[ií]|sip)\b.*\b(persist|problema|falla|sms|mensaje)", t):
        return True
    return False


def _extraer_dato_escalamiento_sms(msg: str) -> HechosTurno:
    t = (msg or "").strip()
    tl = t.lower()
    hechos = HechosTurno()
    if any(p in tl for p in ("remitente", "desde ", "apple", "netflix", "google", "appli", "a2p")):
        hechos.sms_remitente_ejemplo = t[:120]
    if any(p in tl for p in ("horario", "hora", " hoy ", " ayer ", " junio", " julio", "202")):
        hechos.sms_horario_incidente = t[:120]
    elif re.search(r"\d{1,2}\s*(:\d{2})?\s*(hs|horas)?", tl):
        hechos.sms_horario_incidente = t[:120]
    return hechos


def _interpretar_por_contexto(
    msg: str,
    *,
    pregunta: PreguntaPendiente,
    tiene_ticket: bool,
) -> TurnUnderstanding | None:
    """Respuestas cortas interpretadas según la pregunta pendiente del bot."""
    if not msg:
        return None

    if pregunta == PreguntaPendiente.CONFIRMAR_PERSISTENCIA:
        if _es_afirmacion_corta(msg) or _detecta_persistencia_semantica(msg):
            return TurnUnderstanding(
                intencion=IntencionTurno.CONFIRMAR_PERSISTENCIA,
                confianza=0.92,
                fuente="contexto",
                pregunta_pendiente=pregunta,
                hechos=HechosTurno(persistencia_confirmada=True, resuelto=False),
                evidencia=["respuesta_afirmativa_a_persistencia"],
                mensaje_operador=msg,
            )
        if _es_negacion_corta(msg):
            return TurnUnderstanding(
                intencion=IntencionTurno.CORRECCION,
                confianza=0.85,
                fuente="contexto",
                pregunta_pendiente=pregunta,
                hechos=HechosTurno(resuelto=True),
                evidencia=["negacion_a_persistencia"],
                mensaje_operador=msg,
            )

    if pregunta == PreguntaPendiente.CONFIRMAR_TICKET:
        if _es_afirmacion_corta(msg) or usuario_confirmo_ticket([{"rol": "usuario", "contenido": msg}]):
            return TurnUnderstanding(
                intencion=IntencionTurno.SOLICITAR_TICKET,
                confianza=0.9,
                fuente="contexto",
                pregunta_pendiente=pregunta,
                hechos=HechosTurno(solicita_ticket=True, persistencia_confirmada=True, resuelto=False),
                evidencia=["confirmacion_ticket"],
                mensaje_operador=msg,
            )

    if pregunta == PreguntaPendiente.CONFIRMAR_PASO and _es_afirmacion_corta(msg):
        return TurnUnderstanding(
            intencion=IntencionTurno.CONFIRMAR_PASO,
            confianza=0.9,
            fuente="contexto",
            pregunta_pendiente=pregunta,
            hechos=HechosTurno(confirmacion_paso=True),
            evidencia=["confirmacion_paso"],
            mensaje_operador=msg,
        )

    if pregunta == PreguntaPendiente.APORTAR_DATOS_ESCALAMIENTO:
        if _detecta_persistencia_semantica(msg):
            return TurnUnderstanding(
                intencion=IntencionTurno.CONFIRMAR_PERSISTENCIA,
                confianza=0.9,
                fuente="contexto",
                pregunta_pendiente=pregunta,
                hechos=HechosTurno(persistencia_confirmada=True, resuelto=False),
                evidencia=["persistencia_en_paso_escalamiento"],
                mensaje_operador=msg,
            )
        datos = _extraer_dato_escalamiento_sms(msg)
        if datos.sms_remitente_ejemplo or datos.sms_horario_incidente:
            return TurnUnderstanding(
                intencion=IntencionTurno.APORTAR_DATO,
                confianza=0.88,
                fuente="contexto",
                pregunta_pendiente=pregunta,
                hechos=datos,
                evidencia=["dato_escalamiento_sms"],
                mensaje_operador=msg,
            )

    if pregunta == PreguntaPendiente.CONFIRMAR_RESOLUCION and _es_afirmacion_corta(msg):
        if not tiene_ticket:
            return TurnUnderstanding(
                intencion=IntencionTurno.CASO_RESUELTO,
                confianza=0.85,
                fuente="contexto",
                pregunta_pendiente=pregunta,
                hechos=HechosTurno(resuelto=True),
                evidencia=["confirmacion_resolucion"],
                mensaje_operador=msg,
            )

    return None


def _desde_reglas_legacy(msg: str, *, tiene_ticket: bool, hechos_prev: dict) -> TurnUnderstanding:
    """Fallback a reglas existentes — produce el mismo objeto estructurado."""
    norm = detectar_intencion_normalizada(msg, tiene_ticket=tiene_ticket, hechos=hechos_prev)
    tipo_map = {
        "estado_ticket": IntencionTurno.ESTADO_TICKET,
        "novedad_ticket": IntencionTurno.NOVEDAD_TICKET,
        "resumen_caso": IntencionTurno.RESUMEN_CASO,
        "cerrar_ticket": IntencionTurno.CERRAR_TICKET,
        "correccion": IntencionTurno.CORRECCION,
        "agradecimiento": IntencionTurno.AGRADECIMIENTO,
        "pregunta_recomendacion": IntencionTurno.PREGUNTA_RECOMENDACION,
        "persistencia": IntencionTurno.PERSISTENCIA,
        "confirmacion_paso": IntencionTurno.CONFIRMAR_PASO,
        "caso_resuelto": IntencionTurno.CASO_RESUELTO,
        "informe_prueba": IntencionTurno.INFORME_PRUEBA,
        "informe_alcance": IntencionTurno.INFORME_ALCANCE,
        "seguimiento_activo": IntencionTurno.SEGUIMIENTO_ACTIVO,
        "continuar": IntencionTurno.CONTINUAR,
    }
    intencion = tipo_map.get(norm.get("tipo", "continuar"), IntencionTurno.CONTINUAR)

    hechos_turno = HechosTurno()
    if intencion == IntencionTurno.PERSISTENCIA:
        hechos_turno.resuelto = False
        if operador_confirmo_persistencia_explicita(msg):
            hechos_turno.persistencia_confirmada = True
    if intencion == IntencionTurno.CASO_RESUELTO and mensaje_indica_resolucion_real(msg):
        hechos_turno.resuelto = True
    if intencion == IntencionTurno.CONFIRMAR_PASO:
        hechos_turno.confirmacion_paso = True

    if _detecta_solicitud_ticket(msg):
        intencion = IntencionTurno.SOLICITAR_TICKET
        hechos_turno.solicita_ticket = True
        hechos_turno.resuelto = False

    if _detecta_persistencia_semantica(msg) and intencion == IntencionTurno.CONTINUAR:
        intencion = IntencionTurno.PERSISTENCIA
        hechos_turno.resuelto = False
        if operador_confirmo_persistencia_explicita(msg):
            hechos_turno.persistencia_confirmada = True

    return TurnUnderstanding(
        intencion=intencion,
        confianza=float(norm.get("confianza") or 0.4),
        fuente=str(norm.get("fuente") or "reglas"),
        hechos=hechos_turno,
        evidencia=[f"regla:{norm.get('tipo', 'continuar')}"],
        mensaje_operador=msg,
    )


def interpretar_turno_hibrido(
    historial: list[dict],
    *,
    hechos_prev: dict | None = None,
    tiene_ticket: bool = False,
    flujo_paso_id: str = "",
) -> TurnUnderstanding:
    """Punto de entrada híbrido: contexto del bot + reglas + hechos normalizados."""
    msg = _ultimo_mensaje(historial, "usuario")
    ultimo_bot = _ultimo_mensaje(historial, "asistente")
    pregunta = inferir_pregunta_pendiente(ultimo_bot, flujo_paso_id=flujo_paso_id)

    ctx = _interpretar_por_contexto(msg, pregunta=pregunta, tiene_ticket=tiene_ticket)
    if ctx and ctx.confianza >= 0.85:
        understanding = ctx
    else:
        understanding = _desde_reglas_legacy(msg, tiene_ticket=tiene_ticket, hechos_prev=hechos_prev or {})
        understanding.pregunta_pendiente = pregunta

    # Enriquecer con hechos técnicos del mensaje (APN, llamadas, etc.)
    norm_hechos = extraer_hechos_normalizados(msg, ultimo_bot=ultimo_bot)
    for k, v in norm_hechos.items():
        if hasattr(understanding.hechos, k) and v is not None:
            setattr(understanding.hechos, k, v)

    if pregunta == PreguntaPendiente.APORTAR_DATOS_ESCALAMIENTO:
        extra = _extraer_dato_escalamiento_sms(msg)
        if extra.sms_remitente_ejemplo:
            understanding.hechos.sms_remitente_ejemplo = extra.sms_remitente_ejemplo
        if extra.sms_horario_incidente:
            understanding.hechos.sms_horario_incidente = extra.sms_horario_incidente

    return understanding


def fusionar_hechos_turno(hechos: dict, understanding: TurnUnderstanding) -> dict:
    """Aplica hechos del turno al estado acumulado."""
    out = dict(hechos)
    for k, v in understanding.hechos.a_dict().items():
        if v is None:
            continue
        if k not in out or out[k] is None:
            out[k] = v
        elif k in (
            "persistencia_confirmada",
            "solicita_ticket",
            "confirmacion_paso",
            "linea_jsc_verificada",
            "reinicio_o_modo_avion",
            "alcance_confirmado",
            "apn_configurado",
        ) and v is True:
            out[k] = True
        elif k in ("resuelto", "datos_ok", "llamadas_ok") and v is False:
            out[k] = False
        elif k.startswith("sms_") and v:
            out[k] = v
    if understanding.intencion in (
        IntencionTurno.PERSISTENCIA,
        IntencionTurno.CONFIRMAR_PERSISTENCIA,
        IntencionTurno.SOLICITAR_TICKET,
    ):
        out["resuelto"] = False
    return out
