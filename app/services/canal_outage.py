"""Interceptación N1 de incidentes masivos (NAS / outage).

Vive aparte de `canal_abonado` para no inflar el orquestador. Los helpers de
I/O y cierre de hilo se importan lazy para evitar import circular.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.domain.canales import enviar_externo as _enviar_externo
from app.domain.flujos_abonado import contiene_sintoma_canal, parece_consulta_nueva
from app.estate import canal_repo as crepo
from app.estate.models import Abonado, ConversacionCanal

logger = logging.getLogger("operations_hub")


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
    from app.services.canal_abonado import (
        _cerrar_consulta_resuelta,
        _enviar_respuesta,
        _playbooks,
        _primer_nombre_cliente,
        _reset_ctx_diagnostico,
    )
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

        # "No" / sigue mal tras «¿Ya te anda?» → diagnóstico N1 de internet
        if ctx.get("outage_resuelto_avisado"):
            from app.services.outages import niega_servicio_ok_post_outage

            if niega_servicio_ok_post_outage(texto) or contiene_sintoma_canal(texto):
                _limpiar_ctx_outage(ctx)
                ctx["intencion"] = "internet"
                ctx["paso_idx"] = 0
                ctx["diag_turnos"] = 0
                ctx["pasos_cubiertos"] = []
                ctx["post_outage_n1"] = True
                if hasattr(conv, "servicio_detectado"):
                    conv.servicio_detectado = "internet"
                crepo.set_contexto(conv, ctx)
                db.commit()
                pb = _playbooks(db)
                pasos = pb.get("internet") or pb["general"]
                pregunta = (
                    pasos[0].pregunta
                    if pasos
                    else "¿Les pasa a todos los equipos o solo a uno?"
                )
                msg = (
                    "Dale, entonces seguimos con el diagnóstico. "
                    f"{pregunta}"
                )
                return _pack(msg, intencion="internet", post_outage_n1=True)

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
