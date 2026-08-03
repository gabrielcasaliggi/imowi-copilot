"""Motor N1 del canal abonado (WhatsApp / simulador) + escalamiento N2."""

from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.domain.flujos_abonado import (
    clasificar_intencion,
    contiene_sintoma_canal,
    detecta_frustracion,
    es_escape_agente,
    es_paso_derivacion,
    es_saludo_corto,
    indica_resuelto,
    misma_queja,
    parece_consulta_nueva,
    pide_humano,
    refinar_intencion_internet,
    registrar_queja,
    resumen_handoff,
    respuesta_paso_ok,
    tag_para_intencion,
)
from app.estate import canal_repo as crepo
from app.estate.models import Abonado, ConversacionCanal
from app.services import ticket_bridge
from app.services.diagnostico_n1 import diagnosticar_turno, es_intencion_diagnostico
from app.services.platform_settings import playbooks_as_pasos, resolve_canal_diagnostico_ia
from app.services.whatsapp_client import enviar_texto
from app.config import BOT_DISPLAY_NAME, BOT_DISPLAY_NAME_SHORT, PRODUCT_DISPLAY_NAME

logger = logging.getLogger("operations_hub")

# Plantilla fija N1 — no depende del playbook admin (puede estar desactualizado).
PLANTILLA_PAGO_QR = (
    "Podés pagar con el QR Fiserv de la factura (Mercado Pago, MODO, etc.). "
    "Cuando se acredita, el servicio se reactiva solo. "
    "Si no tenés el QR, identificáte con DNI en el portal o pasame DNI/N.º de socio. "
    "¿Pudiste pagar o necesitás que te ubique la cuenta?"
)


def _playbooks(db: Session):
    return playbooks_as_pasos(db)


def _extraer_dni(texto: str) -> str:
    nums = re.findall(r"\b\d{7,8}\b", texto or "")
    return nums[0] if nums else ""


def _deuda_positiva(abonado: Abonado) -> bool:
    try:
        return float(str(abonado.deuda_monto).replace(",", ".").replace("$", "")) > 0
    except ValueError:
        return abonado.estado in ("corte", "suspendido")


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
                    "content": with_anti_injection(
                        f"Sos {BOT_DISPLAY_NAME}, el asistente de {PRODUCT_DISPLAY_NAME} "
                        "(Cooperativa Batán / Ecolan + móvil). "
                        "Escribí como en un chat de WhatsApp: natural, breve, cálido y resolutivo. "
                        "No sos Copilot NOC ni un agente humano: si derivás, decilo claro. "
                        "REGLAS ESTRICTAS:\n"
                        "- Máximo 2 oraciones cortas.\n"
                        "- UNA sola pregunta por mensaje. Nunca combines varias preguntas.\n"
                        "- No uses listas largas, viñetas ni catálogos de servicios.\n"
                        "- No inventes datos (OLT, saldos, turnos, potencias).\n"
                        "- No uses jerga interna del NOC.\n"
                        "- Conservá la intención del borrador; no agregues pasos extra.\n"
                        "- Si el borrador menciona QR Fiserv / Mercado Pago / MODO, conservalo.\n"
                        "- Nunca digas que quedó resuelto si el cliente aún describe un problema "
                        "(ej. «anda bien lejos no»).\n"
                        "- No ofrezcas ticket ni derivación a agente en el primer o segundo paso "
                        "de un diagnóstico técnico (internet/wifi/móvil); primero autodiagnóstico.\n"
                        "- Si el cliente no respondió la pregunta anterior, reiterá ESA pregunta.\n"
                        "- Español argentino cotidiano (vos)."
                    ),
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
            temperature=0.2,
        )
        texto = (out or "").strip() or borrador
        # Si el modelo se va de mambo, volver al playbook corto
        if len(texto) > 320 or texto.count("?") > 1:
            return borrador.strip()
        return texto
    except Exception:
        return borrador


def _crear_ticket_n2(
    db: Session,
    org_id: str,
    conv: ConversacionCanal,
    abonado: Abonado | None,
    motivo: str,
    *,
    intencion: str = "",
    paso_idx: int = 0,
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
    descripcion = (
        f"[ORIGEN: {BOT_DISPLAY_NAME_SHORT}] {tag} Escalamiento N2 canal abonado ({nombre}): {motivo}. {handoff}"
    )
    t = ticket_bridge.crear_ticket(
        db,
        org_id,
        linea=linea,
        dispositivo="Canal abonado",
        descripcion_falla=descripcion[:2000],
        origen="WhatsApp" if conv.canal == "whatsapp" else "Portal",
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
    conv.estado = "espera_agente"
    db.commit()
    return t.id


def _enviar_respuesta(
    db: Session,
    org_id: str,
    conv: ConversacionCanal,
    texto: str,
    *,
    enviar_wa: bool = True,
) -> str:
    crepo.add_mensaje(db, org_id, conv.id, direccion="out", autor="bot", texto=texto)
    if enviar_wa and conv.canal == "whatsapp":
        enviar_texto(conv.telefono, texto)
    return texto


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

    pb = _playbooks(db)
    checklist = pb.get(intencion) or pb.get("general") or []
    historial = crepo.list_mensajes(db, conv.id)
    turnos = int(ctx.get("diag_turnos") or 0)
    cubiertos = [str(x) for x in (ctx.get("pasos_cubiertos") or []) if str(x).strip()]
    kb = _kb_fragmento(db, org_id, texto)
    forzar = bool(es_escape_agente(texto))

    result = diagnosticar_turno(
        intencion=intencion,
        checklist=checklist,
        historial_mensajes=historial,
        mensaje_cliente=texto,
        turnos_diagnostico=turnos,
        pasos_cubiertos=cubiertos,
        kb_fragmento=kb,
        forzar_agente=forzar,
    )

    accion = result.get("accion") or "ask"
    mensaje = (result.get("mensaje") or "").strip()
    paso = (result.get("paso_cubierto") or "").strip()
    if paso and paso not in cubiertos:
        cubiertos.append(paso)
    ctx["pasos_cubiertos"] = cubiertos
    ctx["diag_turnos"] = turnos + 1
    ctx["paso_idx"] = min(len(cubiertos), max(len(checklist) - 1, 0))
    ctx["ultima_diag_motivo"] = (result.get("motivo") or "")[:200]
    ctx["intencion"] = intencion
    crepo.set_contexto(conv, ctx)
    db.commit()

    if accion == "escalate":
        tid = _crear_ticket_n2(
            db,
            org_id,
            conv,
            abonado,
            f"Diagnóstico N1 IA: {result.get('motivo') or 'escalate'} ({intencion})",
            intencion=intencion,
            paso_idx=int(ctx.get("paso_idx") or 0),
        )
        if not mensaje or "ticket" not in mensaje.lower():
            mensaje = (
                f"Avancé todo lo posible en soporte N1 y generé el ticket {tid} "
                "para un agente. Te van a responder por este mismo chat."
            )
        elif tid not in mensaje:
            mensaje = f"{mensaje} Ticket {tid}."
        _enviar_respuesta(db, org_id, conv, mensaje, enviar_wa=(canal == "whatsapp"))
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
        if not mensaje:
            mensaje = (
                "¡Genial! Qué bueno que quedó resuelto. Si vuelve a pasar, "
                "escribime de nuevo. ¡Gracias!"
            )
        _enviar_respuesta(db, org_id, conv, mensaje, enviar_wa=(canal == "whatsapp"))
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
    _enviar_respuesta(db, org_id, conv, mensaje, enviar_wa=(canal == "whatsapp"))
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
) -> dict:
    """Procesa un mensaje del cliente. Retorna respuesta del bot o estado agente."""
    texto = (texto or "").strip()
    if not texto:
        return {"ok": False, "error": "mensaje vacío"}

    conv = crepo.get_or_create_conversacion(
        db, org_id, telefono=telefono, canal=canal, wa_id=wa_id
    )
    crepo.add_mensaje(
        db,
        org_id,
        conv.id,
        direccion="in",
        autor="cliente",
        texto=texto,
        meta_message_id=meta_message_id,
    )

    # Si ya está con agente o en espera, no responde el bot
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
        # espera_agente: recordatorio breve
        aviso = (
            "Tu caso ya está derivado a un agente. En breve te van a responder por este mismo chat."
        )
        _enviar_respuesta(db, org_id, conv, aviso, enviar_wa=(canal == "whatsapp"))
        return {
            "ok": True,
            "modo": "espera_agente",
            "conversacion_id": conv.id,
            "respuesta": aviso,
            "estado": conv.estado,
            "ticket_id": conv.ticket_id,
        }

    if conv.estado == "cerrado":
        conv.estado = "bot"
        db.commit()

    ctx = crepo.get_contexto(conv)
    abonado: Abonado | None = None
    if conv.abonado_id:
        abonado = db.get(Abonado, conv.abonado_id)
    if not abonado:
        abonado = crepo.find_abonado_por_telefono(db, org_id, conv.telefono)

    # Frustración / reiteración: solo tras avance N1 real (paso_idx ≥ 2)
    if detecta_frustracion(texto, ctx):
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
        )
        resp = (
            f"Entiendo la molestia. Te derivo con un agente con el historial. "
            f"Ticket {tid}. Quedate en este chat."
        )
        _enviar_respuesta(db, org_id, conv, resp, enviar_wa=(canal == "whatsapp"))
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
                "móvil IMOVI, factura/pago u otra consulta."
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
        _enviar_respuesta(db, org_id, conv, resp, enviar_wa=(canal == "whatsapp"))
        return {
            "ok": True,
            "modo": "bot",
            "conversacion_id": conv.id,
            "respuesta": resp,
            "estado": conv.estado,
            "intencion": intent or None,
        }

    # Escape hatch *agente* o 2ª insistencia sin síntoma → ticket.
    # Pedido de humano CON síntoma → sigue N1 (no cortar acá).
    # Primer pedido sin síntoma → menú + CTA *agente*.
    if es_escape_agente(texto) or (
        pide_humano(texto)
        and not contiene_sintoma_canal(texto)
        and int(ctx.get("pidio_humano") or 0) >= 1
    ):
        intent = str(ctx.get("intencion") or conv.servicio_detectado or "general")
        tid = _crear_ticket_n2(
            db,
            org_id,
            conv,
            abonado,
            "Cliente solicitó agente humano",
            intencion=intent,
            paso_idx=int(ctx.get("paso_idx") or 0),
        )
        resp = (
            f"Te derivo con un agente. Ticket {tid}. "
            "Quedate en esta conversación, te van a responder acá."
        )
        _enviar_respuesta(db, org_id, conv, resp, enviar_wa=(canal == "whatsapp"))
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
            "Puedo ayudarte yo primero (internet, móvil IMOVI o factura/pago). "
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
        _enviar_respuesta(db, org_id, conv, resp, enviar_wa=(canal == "whatsapp"))
        return {
            "ok": True,
            "modo": "bot",
            "conversacion_id": conv.id,
            "respuesta": resp,
            "estado": conv.estado,
        }

    # Identificación — portal/web continúa como invitado si no hay match
    if not abonado:
        dni = _extraer_dni(texto)
        if dni:
            abonado = crepo.find_abonado_por_dni(db, org_id, dni)

        if not abonado:
            # WhatsApp: pedir DNI una sola vez; después seguir como invitado
            if canal != "web" and not ctx.get("pidio_dni") and not ctx.get("invitado"):
                ctx["pidio_dni"] = True
                crepo.set_contexto(conv, ctx)
                db.commit()
                resp = (
                    f"Hola, soy {BOT_DISPLAY_NAME}, de {PRODUCT_DISPLAY_NAME} "
                    "(Cooperativa Batán / Ecolan). "
                    "Para identificarte (facturas, diagnóstico de cuenta o visitas), "
                    "enviame tu DNI o N.º de socio. Si preferís, escribí *agente*."
                )
                if usar_llama:
                    resp = _redactar_con_llama(
                        resp,
                        f"tel={conv.telefono}",
                        db=db,
                        org_id=org_id,
                        consulta=texto,
                    )
                _enviar_respuesta(db, org_id, conv, resp, enviar_wa=(canal == "whatsapp"))
                return {
                    "ok": True,
                    "modo": "bot",
                    "conversacion_id": conv.id,
                    "respuesta": resp,
                    "estado": conv.estado,
                }

            if not ctx.get("invitado"):
                ctx["invitado"] = True
                if dni:
                    ctx["dni_intentado"] = dni
                crepo.set_contexto(conv, ctx)
                db.commit()

            if dni and not ctx.get("aviso_invitado"):
                ctx["aviso_invitado"] = True
                crepo.set_contexto(conv, ctx)
                db.commit()
                resp = (
                    "No figurás todavía en el padrón local. Igual te atiendo: "
                    "¿tu consulta es por internet (fibra, radio o ADSL), móvil IMOVI, "
                    "telefonía fija, factura/pago, o un servicio Ecolan empresa?"
                )
                _enviar_respuesta(db, org_id, conv, resp, enviar_wa=(canal == "whatsapp"))
                return {
                    "ok": True,
                    "modo": "bot",
                    "conversacion_id": conv.id,
                    "respuesta": resp,
                    "estado": conv.estado,
                }

    if abonado:
        conv.abonado_id = abonado.id
        if not ctx.get("saludo"):
            ctx["saludo"] = True
            ctx.pop("invitado", None)
            crepo.set_contexto(conv, ctx)
            db.commit()
            saludo = (
                f"Hola {abonado.nombre.split()[0]}, te identifiqué correctamente. "
                f"Servicio: {abonado.servicio} · plan {abonado.plan or 'N/A'} · estado {abonado.estado}. "
                "¿En qué te puedo ayudar?"
            )
            if usar_llama:
                saludo = _redactar_con_llama(
                    saludo,
                    f"abonado={abonado.nombre} estado={abonado.estado} deuda={abonado.deuda_monto}",
                    db=db,
                    org_id=org_id,
                    consulta=texto,
                )
            _enviar_respuesta(db, org_id, conv, saludo, enviar_wa=(canal == "whatsapp"))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": saludo,
                "estado": conv.estado,
                "abonado": crepo.abonado_to_dict(abonado),
            }

    # Corte por deuda automático si aplica
    intencion = ctx.get("intencion") or ""
    servicio_abo = abonado.servicio if abonado else ""
    if not intencion:
        if abonado and (_deuda_positiva(abonado) or abonado.estado in ("corte", "suspendido")):
            intencion = "corte_deuda"
        else:
            intencion = clasificar_intencion(texto, servicio_abo)
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
        crepo.set_contexto(conv, ctx)
        db.commit()
        pb = _playbooks(db)
        pasos = pb.get(intencion) or pb["general"]
        idx = max(0, min(paso_inicial, len(pasos) - 1))
        pregunta = pasos[idx].pregunta
        if intencion == "corte_deuda":
            # Siempre guía QR primero (evita playbooks admin sin Fiserv / rewrites).
            if abonado:
                pregunta = (
                    f"Tu cuenta figura con estado «{abonado.estado}» "
                    f"y saldo pendiente ${abonado.deuda_monto}. {PLANTILLA_PAGO_QR}"
                )
            else:
                pregunta = (
                    "Puede haber un saldo pendiente o el servicio limitado. "
                    f"{PLANTILLA_PAGO_QR}"
                )
            _enviar_respuesta(db, org_id, conv, pregunta, enviar_wa=(canal == "whatsapp"))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": pregunta,
                "estado": conv.estado,
                "intencion": intencion,
            }
        if intencion == "facturacion" and not abonado:
            pregunta = (
                "Para saldo o copia de factura identificáte con DNI en el portal. "
                f"{PLANTILLA_PAGO_QR}"
            )
            _enviar_respuesta(db, org_id, conv, pregunta, enviar_wa=(canal == "whatsapp"))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": pregunta,
                "estado": conv.estado,
                "intencion": intencion,
            }
        # Pagos identificados (no corte): conservar plantilla; no reescribir con LLM
        if intencion in ("corte_deuda", "facturacion"):
            usar_llm_paso = False
        else:
            # Diagnóstico IA (técnicos): playbook = checklist
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
        _enviar_respuesta(db, org_id, conv, pregunta, enviar_wa=(canal == "whatsapp"))
        return {
            "ok": True,
            "modo": "bot",
            "conversacion_id": conv.id,
            "respuesta": pregunta,
            "estado": conv.estado,
            "intencion": intencion,
        }

    # Refinar internet → radio / ADSL tras la pregunta de tipo de acceso
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
            _enviar_respuesta(db, org_id, conv, pregunta, enviar_wa=(canal == "whatsapp"))
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
        nueva = clasificar_intencion(texto, servicio_abo)
        if nueva != "general":
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
                    f"intencion={intencion}",
                    db=db,
                    org_id=org_id,
                    consulta=texto,
                )
            _enviar_respuesta(db, org_id, conv, pregunta, enviar_wa=(canal == "whatsapp"))
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
        _enviar_respuesta(db, org_id, conv, resp, enviar_wa=(canal == "whatsapp"))
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
            _enviar_respuesta(db, org_id, conv, pregunta, enviar_wa=(canal == "whatsapp"))
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
        # Pagos/QR: plantilla fija para no perder instrucciones Fiserv
        if usar_llama and intencion not in ("corte_deuda", "facturacion"):
            pregunta = _redactar_con_llama(
                pregunta,
                f"paso={idx} intencion={intencion}",
                db=db,
                org_id=org_id,
                consulta=texto,
            )
        _enviar_respuesta(db, org_id, conv, pregunta, enviar_wa=(canal == "whatsapp"))
        return {
            "ok": True,
            "modo": "bot",
            "conversacion_id": conv.id,
            "respuesta": pregunta,
            "estado": conv.estado,
            "intencion": intencion,
        }

    def _escalar(motivo: str) -> dict:
        tid = _crear_ticket_n2(
            db,
            org_id,
            conv,
            abonado,
            motivo,
            intencion=intencion,
            paso_idx=paso_idx,
        )
        resp = (
            f"Avancé todo lo posible en soporte N1 y generé el ticket {tid} "
            "para un agente. Te van a responder por este mismo chat."
        )
        if usar_llama:
            resp = _redactar_con_llama(
                resp,
                f"escalamiento intencion={intencion} paso={paso_idx}",
                db=db,
                org_id=org_id,
                consulta=texto,
            )
        _enviar_respuesta(db, org_id, conv, resp, enviar_wa=(canal == "whatsapp"))
        return {
            "ok": True,
            "modo": "espera_agente",
            "conversacion_id": conv.id,
            "respuesta": resp,
            "estado": conv.estado,
            "ticket_id": tid,
        }

    # El abonado dice que ya quedó resuelto
    if indica_resuelto(texto):
        conv.estado = "cerrado"
        db.commit()
        resp = (
            "¡Genial! Qué bueno que quedó resuelto. Si vuelve a pasar, "
            "escribime de nuevo y te ayudo. ¡Gracias!"
        )
        _enviar_respuesta(db, org_id, conv, resp, enviar_wa=(canal == "whatsapp"))
        return {
            "ok": True,
            "modo": "cerrado",
            "conversacion_id": conv.id,
            "respuesta": resp,
            "estado": conv.estado,
        }

    # Confirmó derivación en el último paso tipo "¿Querés que te derive?"
    if veredicto is True and es_paso_derivacion(paso_actual):
        return _escalar(f"Abonado aceptó derivación en playbook {intencion}")

    # Sigue fallando → siguiente paso de diagnóstico (no escalar en el primero)
    if veredicto is False:
        if paso_idx >= len(pasos) - 1:
            if es_paso_derivacion(paso_actual):
                # Última pregunta de derivación respondida con "no"
                resp = (
                    "Entendido, no te derivo por ahora. Si más adelante necesitás "
                    "ayuda o querés hablar con un agente, escribí *agente*."
                )
                _enviar_respuesta(db, org_id, conv, resp, enviar_wa=(canal == "whatsapp"))
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
            _enviar_respuesta(db, org_id, conv, resp, enviar_wa=(canal == "whatsapp"))
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
    _enviar_respuesta(db, org_id, conv, resp, enviar_wa=(canal == "whatsapp"))
    return {
        "ok": True,
        "modo": "bot",
        "conversacion_id": conv.id,
        "respuesta": resp,
        "estado": conv.estado,
    }
