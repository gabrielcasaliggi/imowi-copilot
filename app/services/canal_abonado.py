"""Motor N1 del canal abonado (WhatsApp / simulador) + escalamiento N2."""

from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.domain.flujos_abonado import (
    clasificar_intencion,
    detecta_frustracion,
    es_paso_derivacion,
    es_saludo_corto,
    indica_resuelto,
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
from app.services.platform_settings import playbooks_as_pasos
from app.services.whatsapp_client import enviar_texto
from app.config import BOT_DISPLAY_NAME, BOT_DISPLAY_NAME_SHORT, PRODUCT_DISPLAY_NAME

logger = logging.getLogger("operations_hub")


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

        kb_ctx = _kb_fragmento(db, org_id, consulta or contexto, max_chars=600)
        kb_block = (
            f"\n\nDato de KB (opcional, máximo una frase si aporta):\n{kb_ctx}"
            if kb_ctx
            else ""
        )
        out = chat_completion(
            [
                {
                    "role": "system",
                    "content": (
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
                        "- Español argentino cotidiano (vos)."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Contexto: {contexto}"
                        f"{kb_block}\n"
                        f"Cliente dijo: {(consulta or '').strip() or '(n/a)'}\n"
                        f"Borrador (reescribilo breve, una pregunta):\n{borrador}"
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

    # Frustración / reiteración de la misma queja → handoff
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
    ctx = registrar_queja(ctx, texto)
    crepo.set_contexto(conv, ctx)
    db.commit()

    # Pedir agente tiene prioridad absoluta (también sin estar identificado)
    if pide_humano(texto):
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
        ctx["intencion"] = intencion
        ctx["paso_idx"] = 0
        conv.servicio_detectado = (
            intencion
            if intencion in ("internet", "internet_radio", "internet_adsl", "movil")
            else (servicio_abo or intencion)
        )
        crepo.set_contexto(conv, ctx)
        db.commit()
        pb = _playbooks(db)
        pasos = pb.get(intencion) or pb["general"]
        pregunta = pasos[0].pregunta
        if intencion == "corte_deuda" and abonado:
            pregunta = (
                f"Tu cuenta figura con estado «{abonado.estado}» "
                f"y saldo pendiente ${abonado.deuda_monto}. {pregunta}"
            )
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

    # Refinar internet → radio / ADSL tras la pregunta de tipo de acceso
    if intencion == "internet":
        refinada = refinar_intencion_internet(texto)
        if refinada:
            intencion = refinada
            ctx["intencion"] = intencion
            ctx["paso_idx"] = 0
            conv.servicio_detectado = intencion
            crepo.set_contexto(conv, ctx)
            db.commit()
            pb = _playbooks(db)
            pasos = pb.get(intencion) or pb["general"]
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
            crepo.set_contexto(conv, ctx)
            db.commit()
            pb = _playbooks(db)
            pasos = pb.get(intencion) or pb["general"]
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

    # Consulta nueva a mitad de otro flujo: reclasificar si cambia la intención
    if parece_consulta_nueva(texto) and intencion:
        nueva = clasificar_intencion(texto, servicio_abo)
        if nueva and nueva != intencion:
            intencion = nueva
            ctx["intencion"] = intencion
            ctx["paso_idx"] = 0
            crepo.set_contexto(conv, ctx)
            db.commit()
            pb = _playbooks(db)
            pasos = pb.get(intencion) or pb["general"]
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
        if usar_llama:
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
