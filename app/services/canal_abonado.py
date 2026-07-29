"""Motor N1 del canal abonado (WhatsApp / simulador) + escalamiento N2."""

from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.domain.flujos_abonado import (
    clasificar_intencion,
    pide_humano,
    respuesta_paso_ok,
)
from app.estate import canal_repo as crepo
from app.estate.models import Abonado, ConversacionCanal
from app.services import ticket_bridge
from app.services.platform_settings import playbooks_as_pasos
from app.services.whatsapp_client import enviar_texto

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


def _redactar_con_llama(borrador: str, contexto: str) -> str:
    """Intenta suavizar el texto con Llama; si falla, usa el borrador."""
    try:
        from app.llm import chat_completion

        out = chat_completion(
            [
                {
                    "role": "system",
                    "content": (
                        "Sos el asistente de soporte N1 de una cooperativa (internet Ecolan y móvil). "
                        "Respondé en español argentino, breve (máx 3 oraciones), sin inventar datos. "
                        "Conservá la pregunta o instrucción del borrador."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Contexto:\n{contexto}\n\nBorrador a reescribir:\n{borrador}",
                },
            ],
            temperature=0.3,
        )
        return (out or borrador).strip() or borrador
    except Exception:
        return borrador


def _crear_ticket_n2(
    db: Session,
    org_id: str,
    conv: ConversacionCanal,
    abonado: Abonado | None,
    motivo: str,
) -> str:
    if conv.ticket_id:
        return conv.ticket_id
    mensajes = crepo.list_mensajes(db, conv.id)
    evidencia = "\n".join(f"[{m.autor}] {m.texto}" for m in mensajes[-12:])
    nombre = abonado.nombre if abonado else conv.telefono
    linea = (abonado.linea_msisdn if abonado else "") or conv.telefono
    cat = conv.servicio_detectado or (abonado.servicio if abonado else "General")
    t = ticket_bridge.crear_ticket(
        db,
        org_id,
        linea=linea,
        dispositivo="Canal WhatsApp",
        descripcion_falla=f"Escalamiento N2 desde canal abonado ({nombre}): {motivo}",
        origen="WhatsApp",
        categoria=cat.title() if cat else "Canal Abonado",
        creado_por=f"wa:{conv.telefono}",
        nivel="N2",
        destino="imowi_noc",
        proveedor="NOC",
        motivo_escalamiento=motivo,
        evidencia=evidencia,
        acciones_n1_realizadas=motivo,
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

    # Identificación
    if not abonado:
        dni = _extraer_dni(texto)
        if dni:
            abonado = crepo.find_abonado_por_dni(db, org_id, dni)
        if not abonado:
            if not ctx.get("pidio_dni"):
                ctx["pidio_dni"] = True
                crepo.set_contexto(conv, ctx)
                db.commit()
                resp = (
                    "Hola, soy el asistente de la cooperativa. "
                    "Para identificarte, enviame tu DNI (solo números)."
                )
                if usar_llama:
                    resp = _redactar_con_llama(resp, f"tel={conv.telefono}")
                _enviar_respuesta(db, org_id, conv, resp, enviar_wa=(canal == "whatsapp"))
                return {
                    "ok": True,
                    "modo": "bot",
                    "conversacion_id": conv.id,
                    "respuesta": resp,
                    "estado": conv.estado,
                }
            resp = "No encontré ese DNI. Verificá el número o escribí *agente* para hablar con una persona."
            _enviar_respuesta(db, org_id, conv, resp, enviar_wa=(canal == "whatsapp"))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
            }

    conv.abonado_id = abonado.id
    if not ctx.get("saludo"):
        ctx["saludo"] = True
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

    if pide_humano(texto):
        tid = _crear_ticket_n2(db, org_id, conv, abonado, "Cliente solicitó agente humano")
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

    # Corte por deuda automático si aplica
    intencion = ctx.get("intencion") or ""
    if not intencion:
        if _deuda_positiva(abonado) or abonado.estado in ("corte", "suspendido"):
            intencion = "corte_deuda"
        else:
            intencion = clasificar_intencion(texto, abonado.servicio)
        ctx["intencion"] = intencion
        ctx["paso_idx"] = 0
        conv.servicio_detectado = intencion if intencion in ("internet", "movil") else abonado.servicio
        crepo.set_contexto(conv, ctx)
        db.commit()
        pb = _playbooks(db)
        pasos = pb.get(intencion) or pb["general"]
        pregunta = pasos[0].pregunta
        if intencion == "corte_deuda":
            pregunta = (
                f"Tu cuenta figura con estado «{abonado.estado}» "
                f"y saldo pendiente ${abonado.deuda_monto}. {pregunta}"
            )
        if usar_llama:
            pregunta = _redactar_con_llama(pregunta, f"intencion={intencion}")
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
    veredicto = respuesta_paso_ok(texto)

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
        pregunta = pasos[paso_idx].pregunta
        if usar_llama:
            pregunta = _redactar_con_llama(pregunta, f"paso={paso_idx} intencion={intencion}")
        _enviar_respuesta(db, org_id, conv, pregunta, enviar_wa=(canal == "whatsapp"))
        return {
            "ok": True,
            "modo": "bot",
            "conversacion_id": conv.id,
            "respuesta": pregunta,
            "estado": conv.estado,
        }

    if veredicto is False or paso_idx >= len(pasos) - 1:
        tid = _crear_ticket_n2(
            db,
            org_id,
            conv,
            abonado,
            f"Playbook {intencion} sin resolución en paso {paso_idx}",
        )
        resp = (
            f"No pudimos resolverlo en N1. Generé el ticket {tid} para un agente. "
            "Te van a contactar por este chat."
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

    # Respuesta ambigua: repetir paso
    pregunta = pasos[min(paso_idx, len(pasos) - 1)].pregunta
    resp = f"No te entendí del todo. {pregunta}"
    _enviar_respuesta(db, org_id, conv, resp, enviar_wa=(canal == "whatsapp"))
    return {
        "ok": True,
        "modo": "bot",
        "conversacion_id": conv.id,
        "respuesta": resp,
        "estado": conv.estado,
    }
