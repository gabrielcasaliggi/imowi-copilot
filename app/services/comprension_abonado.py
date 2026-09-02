"""Capa de comprensión contextual del canal abonado.

Principio: enriquecer el turno sin reemplazar la política existente.
- Normaliza typos y coloquialismos para las reglas actuales.
- Interpreta respuestas cortas según la pregunta pendiente del bot.
- Persiste hechos confirmados en ctx["hechos"] para continuidad.

Si esta capa falla o no está segura, el flujo legacy sigue igual.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.domain.comprension_abonado import ComprensionTurnoAbonado, PreguntaPendienteAbonado
from app.domain.conversacion import AFIRMACION_CORTA
from app.domain.flujos_abonado import (
    parece_pregunta_interferencia_wifi,
    refinar_intencion_internet,
)
from app.services.comprension_lexico import (
    afirmaciones_extra,
    aplicar_reemplazos_lexico,
    frases_tecnico_en_aviso_deuda,
    negaciones_extra,
)

logger = logging.getLogger("operations_hub")

_FRASES_TECNICO_DEUDA = frases_tecnico_en_aviso_deuda()

_AFIRMACIONES_RAPIDAS = frozenset(
    {
        "si",
        "sí",
        "sip",
        "sep",
        "see",
        "ok",
        "okay",
        "dale",
        "bueno",
        "listo",
        "ya",
        "ya está",
        "ya esta",
        "hecho",
        "confirmo",
        "de acuerdo",
        "correcto",
        "exacto",
        "claro",
        "obvio",
    }
) | afirmaciones_extra()

_NEGACIONES_RAPIDAS = frozenset({"no", "nop", "nope", "nah", "negativo", "nada"}) | negaciones_extra()


def _ultimo_texto_bot(historial: list[Any] | None) -> str:
    for m in reversed(historial or []):
        if isinstance(m, dict):
            rol = (m.get("rol") or m.get("autor") or m.get("direccion") or "").lower()
            if rol in ("bot", "asistente", "out", "eco"):
                return str(m.get("contenido") or m.get("texto") or "").strip()
        else:
            autor = str(getattr(m, "autor", "") or getattr(m, "direccion", "") or "").lower()
            if autor in ("bot", "asistente", "out", "eco"):
                return str(getattr(m, "texto", "") or getattr(m, "contenido", "") or "").strip()
    return ""


def normalizar_lexico_abonado(texto: str) -> str:
    """Typos y variantes frecuentes — no altera el significado declarado."""
    return aplicar_reemplazos_lexico(texto)


def _es_afirmacion_corta(msg: str) -> bool:
    t = (msg or "").lower().strip().rstrip(".!?")
    if not t:
        return False
    if t in AFIRMACION_CORTA or t in _AFIRMACIONES_RAPIDAS:
        return True
    return bool(re.fullmatch(r"(s[iíí]?|sip+|ok+|dale+|listo|ya|claro)", t))


def _es_negacion_corta(msg: str) -> bool:
    t = (msg or "").lower().strip().rstrip(".!?")
    if t in _NEGACIONES_RAPIDAS:
        return True
    return bool(re.fullmatch(r"no+!*", t))


def _bot_pregunta_si_no(ultimo_bot: str) -> bool:
    bot = (ultimo_bot or "").lower()
    if "?" not in bot and "¿" not in bot:
        return False
    return any(
        k in bot
        for k in (
            "¿sí",
            "si o no",
            "sí o no",
            "¿pudiste",
            "¿ya",
            "¿te",
            "¿está",
            "¿esta",
            "¿funciona",
            "¿anda",
            "¿podes",
            "¿podés",
        )
    )


def inferir_pregunta_pendiente_abonado(ultimo_bot: str, ctx: dict | None) -> PreguntaPendienteAbonado:
    """Qué esperaba el bot según estado + último mensaje."""
    c = ctx or {}
    intent = str(c.get("intencion") or "").strip()
    menu_paso = str(c.get("menu_paso") or "").strip()

    if intent == "aviso_deuda" or c.get("aviso_deuda_ofrecido"):
        return PreguntaPendienteAbonado.AVISO_DEUDA

    if menu_paso == "tipo":
        return PreguntaPendienteAbonado.MENU_TIPO_ACCESO

    if menu_paso == "servicio":
        return PreguntaPendienteAbonado.MENU_SERVICIO

    if parece_pregunta_interferencia_wifi(ultimo_bot):
        return PreguntaPendienteAbonado.WIFI_INTERFERENCIAS

    bot = (ultimo_bot or "").lower()
    if intent in ("wifi", "cambio_clave_wifi", "internet_lento") and any(
        k in bot
        for k in (
            "mejoró",
            "mejoro",
            "mejor",
            "más cerca",
            "mas cerca",
            "¿cómo",
            "¿como",
        )
    ):
        return PreguntaPendienteAbonado.WIFI_MEJORA

    if any(
        k in bot
        for k in (
            "reinici",
            "desenchuf",
            "¿pudiste",
            "¿ya",
            "probalo",
            "probá",
            "intentalo",
            "intentá",
        )
    ):
        return PreguntaPendienteAbonado.CONFIRMAR_PASO

    if _bot_pregunta_si_no(ultimo_bot):
        return PreguntaPendienteAbonado.CONFIRMAR_SI_NO

    if any(
        k in bot
        for k in (
            "fibra",
            "antena",
            "adsl",
            "cajita blanca",
            "por teléfono",
            "por telefono",
            "tipo de conexión",
            "tipo de conexion",
        )
    ):
        return PreguntaPendienteAbonado.MENU_TIPO_ACCESO

    return PreguntaPendienteAbonado.NINGUNA


def _interpretar_aviso_deuda(texto: str, ctx: dict) -> ComprensionTurnoAbonado | None:
    t = (texto or "").lower().strip()
    if not t:
        return None

    tech = refinar_intencion_internet(texto)
    if tech:
        return ComprensionTurnoAbonado(
            confianza=0.9,
            fuente="contexto_aviso_deuda",
            hechos_nuevos={"tecnologia_acceso": tech, "intencion_tecnica_pendiente": tech},
            eleccion_aviso_deuda="tecnico",
            evidencia=["sintoma_o_tecnologia_en_aviso_deuda"],
        )

    sintoma_tecnico = any(
        k in t
        for k in (
            "internet",
            "wifi",
            "wi-fi",
            "antena",
            "bai",
            "radio",
            "fibra",
            "no anda",
            "no funciona",
            "sin servicio",
            "lento",
            "señal",
            "senal",
            "datos",
            "móvil",
            "movil",
            "imowi",
            "el problema",
            "problema con",
        )
    )
    pago = any(
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
        )
    )

    if sintoma_tecnico and not pago:
        pend = str(ctx.get("intencion_tecnica_pendiente") or "internet")
        return ComprensionTurnoAbonado(
            confianza=0.88,
            fuente="contexto_aviso_deuda",
            hechos_nuevos={"intencion_tecnica_pendiente": pend},
            eleccion_aviso_deuda="tecnico",
            evidencia=["sintoma_sin_pago_en_aviso_deuda"],
        )

    # Frases cortas frecuentes en Botmaker tras aviso de deuda (76k sesiones minadas).
    if t in _FRASES_TECNICO_DEUDA or any(f in t for f in _FRASES_TECNICO_DEUDA if len(f) >= 10 and f in t):
        pend = str(ctx.get("intencion_tecnica_pendiente") or "internet")
        return ComprensionTurnoAbonado(
            confianza=0.86,
            fuente="contexto_aviso_deuda_lexico",
            hechos_nuevos={"intencion_tecnica_pendiente": pend},
            eleccion_aviso_deuda="tecnico",
            evidencia=["frase_tecnico_deuda_curada"],
        )

    if pago and not sintoma_tecnico:
        return ComprensionTurnoAbonado(
            confianza=0.88,
            fuente="contexto_aviso_deuda",
            eleccion_aviso_deuda="pago",
            evidencia=["solo_pago_en_aviso_deuda"],
        )

    if len(t) <= 28 and _es_afirmacion_corta(texto) and ctx.get("intencion_tecnica_pendiente"):
        return ComprensionTurnoAbonado(
            confianza=0.82,
            fuente="contexto_aviso_deuda",
            eleccion_aviso_deuda="tecnico",
            evidencia=["afirmacion_corta_con_tecnico_pendiente"],
        )

    if len(t) <= 20 and any(k in t for k in ("seguí", "segui", "seguir", "continuar", "diagnóstico", "diagnostico")):
        return ComprensionTurnoAbonado(
            confianza=0.9,
            fuente="contexto_aviso_deuda",
            eleccion_aviso_deuda="tecnico",
            evidencia=["continuar_diagnostico"],
        )

    return None


def _interpretar_tipo_acceso(texto: str) -> ComprensionTurnoAbonado | None:
    tech = refinar_intencion_internet(texto)
    if not tech:
        return None
    return ComprensionTurnoAbonado(
        confianza=0.92,
        fuente="contexto_tipo_acceso",
        hechos_nuevos={"tecnologia_acceso": tech},
        evidencia=[f"tecnologia={tech}"],
    )


def _interpretar_wifi_interferencias(texto: str) -> ComprensionTurnoAbonado | None:
    t = (texto or "").lower().strip()
    if _es_negacion_corta(texto) or any(
        k in t
        for k in (
            "nada",
            "no hay",
            "ningun",
            "ningún",
            "ninguna",
            "libre",
            "sin interfer",
            "no tengo",
            "no hay nada",
            "ya te dije",
        )
    ):
        return ComprensionTurnoAbonado(
            confianza=0.9,
            fuente="contexto_wifi",
            hechos_nuevos={"interferencias_descartadas": True},
            evidencia=["negacion_interferencias"],
        )
    if _es_afirmacion_corta(texto) and len(t) <= 12:
        return ComprensionTurnoAbonado(
            confianza=0.75,
            fuente="contexto_wifi",
            hechos_nuevos={"interferencias_posibles": True},
            evidencia=["afirmacion_interferencias_ambigua"],
        )
    return None


def _interpretar_confirmacion(texto: str, pregunta: PreguntaPendienteAbonado) -> ComprensionTurnoAbonado | None:
    if pregunta not in (
        PreguntaPendienteAbonado.CONFIRMAR_PASO,
        PreguntaPendienteAbonado.CONFIRMAR_SI_NO,
        PreguntaPendienteAbonado.WIFI_MEJORA,
    ):
        return None
    if _es_afirmacion_corta(texto):
        return ComprensionTurnoAbonado(
            confianza=0.85,
            fuente="contexto_confirmacion",
            hechos_nuevos={"confirmacion_positiva": True},
            evidencia=["afirmacion_corta"],
        )
    if _es_negacion_corta(texto):
        return ComprensionTurnoAbonado(
            confianza=0.85,
            fuente="contexto_confirmacion",
            hechos_nuevos={"confirmacion_negativa": True},
            evidencia=["negacion_corta"],
        )
    return None


def interpretar_turno_abonado(
    texto: str,
    *,
    ctx: dict | None = None,
    historial: list[Any] | None = None,
    ultimo_bot: str | None = None,
) -> ComprensionTurnoAbonado:
    """Interpreta el turno: léxico + contexto. Nunca escala ni cambia playbook."""
    original = (texto or "").strip()
    texto_reglas = normalizar_lexico_abonado(original)
    ultimo = (ultimo_bot if ultimo_bot is not None else _ultimo_texto_bot(historial)).strip()
    pregunta = inferir_pregunta_pendiente_abonado(ultimo, ctx)

    base = ComprensionTurnoAbonado(
        texto_original=original,
        texto_para_reglas=texto_reglas,
        pregunta_pendiente=pregunta,
        confianza=0.5 if texto_reglas != original else 0.4,
        fuente="lexico",
        evidencia=["normalizacion_lexica"] if texto_reglas != original else [],
    )

    contextual: ComprensionTurnoAbonado | None = None
    if pregunta == PreguntaPendienteAbonado.AVISO_DEUDA:
        contextual = _interpretar_aviso_deuda(texto_reglas, ctx or {})
    elif pregunta == PreguntaPendienteAbonado.MENU_TIPO_ACCESO:
        contextual = _interpretar_tipo_acceso(texto_reglas)
    elif pregunta == PreguntaPendienteAbonado.WIFI_INTERFERENCIAS:
        contextual = _interpretar_wifi_interferencias(texto_reglas)
    else:
        contextual = _interpretar_confirmacion(texto_reglas, pregunta)

    if not contextual:
        return base

    merged = ComprensionTurnoAbonado(
        texto_original=original,
        texto_para_reglas=texto_reglas,
        pregunta_pendiente=pregunta,
        confianza=max(base.confianza, contextual.confianza),
        fuente=contextual.fuente,
        hechos_nuevos={**base.hechos_nuevos, **contextual.hechos_nuevos},
        eleccion_aviso_deuda=contextual.eleccion_aviso_deuda,
        evidencia=base.evidencia + contextual.evidencia,
    )
    return merged


def fusionar_comprension_en_ctx(ctx: dict, comp: ComprensionTurnoAbonado) -> dict:
    """Persiste hechos confirmados sin pisar política existente."""
    hechos = dict(ctx.get("hechos") or {})
    for clave, valor in (comp.hechos_nuevos or {}).items():
        if valor is not None:
            hechos[clave] = valor
    ctx["hechos"] = hechos

    tech = hechos.get("tecnologia_acceso")
    if tech in ("internet_ftth", "internet_radio", "internet_adsl"):
        ctx["tecnologia_acceso"] = tech

    pend = hechos.get("intencion_tecnica_pendiente")
    if pend:
        ctx["intencion_tecnica_pendiente"] = pend

    if hechos.get("interferencias_descartadas"):
        cub = list(ctx.get("pasos_cubiertos") or [])
        if "canal_interferencia" not in cub:
            cub.append("canal_interferencia")
            ctx["pasos_cubiertos"] = cub

    ctx["comprension_turno"] = comp.to_dict()
    if comp.texto_original and comp.texto_original != comp.texto_para_reglas:
        ctx["mensaje_original"] = comp.texto_original

    return ctx


def preparar_turno_comprension(
    texto: str,
    ctx: dict,
    *,
    historial: list[Any] | None = None,
) -> tuple[str, dict]:
    """Entrada única: devuelve texto para reglas + ctx enriquecido."""
    comp = interpretar_turno_abonado(texto, ctx=ctx, historial=historial)
    ctx = fusionar_comprension_en_ctx(ctx, comp)
    return comp.texto_para_reglas or texto, ctx


def eleccion_aviso_deuda_desde_ctx(ctx: dict) -> str | None:
    """Elección inferida por comprensión (solo si confianza alta)."""
    bloque = ctx.get("comprension_turno") or {}
    if float(bloque.get("confianza") or 0) < 0.8:
        return None
    eleccion = bloque.get("eleccion_aviso_deuda")
    if eleccion in ("pago", "tecnico"):
        return eleccion
    return None


def continuidad_wifi_activa(ctx: dict) -> bool:
    """True si el hilo ya está en diagnóstico WiFi (hechos + pasos)."""
    hechos = ctx.get("hechos") or {}
    if hechos.get("wifi_diagnostico_activo"):
        return True
    from app.domain.flujos_abonado import PASOS_DIAGNOSTICO_WIFI

    cub = set(ctx.get("pasos_cubiertos") or [])
    if cub & PASOS_DIAGNOSTICO_WIFI:
        return True
    intent = str(ctx.get("intencion") or "")
    return intent in ("wifi", "cambio_clave_wifi", "internet_lento")


def tipo_acceso_confirmado_en_hechos(ctx: dict) -> str | None:
    """Tecnología ya confirmada en hechos persistentes."""
    tech = str((ctx.get("hechos") or {}).get("tecnologia_acceso") or ctx.get("tecnologia_acceso") or "")
    if tech in ("internet_ftth", "internet_radio", "internet_adsl"):
        return tech
    return None
