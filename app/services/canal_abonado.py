"""Motor N1 del canal abonado (WhatsApp / simulador) + escalamiento N2."""

from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.domain.flujos_abonado import (
    clasificar_intencion,
    contiene_sintoma_canal,
    detectar_temas_duales,
    detecta_frustracion,
    es_escape_agente,
    es_paso_derivacion,
    es_saludo_corto,
    indica_resuelto,
    intencion_desde_tema,
    misma_queja,
    parece_consulta_nueva,
    pide_humano,
    pide_humano_en_flujo_activo,
    refinar_intencion_internet,
    registrar_queja,
    resolver_prioridad_tema,
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

from app.services.eco_voice import PLANTILLA_PAGO_QR, mensaje_saldo_padron

# Reexport compat: plantilla de pagos Fiserv (único origen: eco_voice).


def _playbooks(db: Session):
    return playbooks_as_pasos(db)


def _extraer_dni(texto: str) -> str:
    nums = re.findall(r"\b\d{7,8}\b", texto or "")
    return nums[0] if nums else ""


def _es_solo_dni(texto: str) -> bool:
    """True si el mensaje es (casi) solo un DNI — no es 'queja' ni frustración."""
    t = (texto or "").strip()
    return bool(re.fullmatch(r"\d{7,8}", t))


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
    abonado = crepo.find_abonado_por_dni(db, org_id, dni)
    if abonado:
        return abonado
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
    return None


def _deuda_positiva(abonado: Abonado) -> bool:
    """True si el padrón indica deuda. BillTrack: balance negativo = debe."""
    from app.services.eco_voice import parse_monto

    m = parse_monto(getattr(abonado, "deuda_monto", None))
    if m is None:
        return abonado.estado in ("corte", "suspendido")
    return m < 0

def _pide_pago_o_reactivar(texto: str) -> bool:
    t = (texto or "").lower()
    return any(
        k in t
        for k in (
            "como pago",
            "cómo pago",
            "quiero pagar",
            "pagar la deuda",
            "pagar la factura",
            "me cortaron",
            "cortaron por",
            "falta de pago",
            "reactivar",
            "reactivación",
            "reactivacion",
            "sin servicio por deuda",
            "fiserv",
            "pagar con qr",
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
    if estado in ("corte", "suspendido") and intencion_clasificada in (
        "",
        "general",
        "corte_deuda",
    ):
        return True
    return False


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
    if pendientes:
        ctx["temas_anotados_ticket"] = list(
            dict.fromkeys(list(ctx.get("temas_anotados_ticket") or []) + pendientes)
        )
        crepo.set_contexto(conv, ctx)
    db.commit()
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


def _responder_espera_agente(
    db: Session,
    org_id: str,
    conv: ConversacionCanal,
    texto: str,
    *,
    canal: str,
) -> dict:
    """En espera de agente: si pregunta por el otro tema, lo anota y confirma."""
    tid = conv.ticket_id or ""
    ctx = crepo.get_contexto(conv)
    tema = _tema_desde_mensaje(texto)
    pendientes = [str(x) for x in (ctx.get("temas_pendientes") or []) if str(x).strip()]
    anotados = [str(x) for x in (ctx.get("temas_anotados_ticket") or []) if str(x).strip()]
    insiste = any(
        k in (texto or "").lower()
        for k in ("y la ", "y el ", "qué pasó con", "que paso con", "y eso de")
    )

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
        crepo.set_contexto(conv, ctx)
        db.commit()
        aviso = (
            f"Sí: el ticket {tid} queda con el reclamo de {label} "
            "junto a lo de la conexión. El agente lo ve en el mismo caso; "
            "te van a responder por este chat."
        )
        _enviar_respuesta(db, org_id, conv, aviso, enviar_wa=(canal == "whatsapp"))
        return {
            "ok": True,
            "modo": "espera_agente",
            "conversacion_id": conv.id,
            "respuesta": aviso,
            "estado": conv.estado,
            "ticket_id": tid,
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
    _enviar_respuesta(db, org_id, conv, aviso, enviar_wa=(canal == "whatsapp"))
    return {
        "ok": True,
        "modo": "espera_agente",
        "conversacion_id": conv.id,
        "respuesta": aviso,
        "estado": conv.estado,
        "ticket_id": tid,
    }


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


def _mensaje_cierre_escalamiento(
    tid: str,
    *,
    motivo: str = "",
    mensaje_ia: str = "",
    nota_temas: str = "",
) -> str:
    """Cierre empático al derivar: no reemplazar un mensaje bueno por plantilla fría."""
    nota = (nota_temas or "").strip()
    if nota and not nota.startswith(" "):
        nota = " " + nota
    motivo_l = (motivo or "").lower()
    ia = (mensaje_ia or "").strip()

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

    if any(k in motivo_l for k in ("los", "fibra", "optica", "óptica", "wifi_post_los")):
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

    result = diagnosticar_turno(
        intencion=intencion,
        checklist=checklist,
        historial_mensajes=historial,
        mensaje_cliente=texto,
        turnos_diagnostico=turnos,
        pasos_cubiertos=cubiertos,
        kb_fragmento=kb,
        forzar_agente=forzar,
        contexto_abonado=build_contexto_abonado(abonado, org_id=org_id),
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
            ctx=ctx,
        )
        mensaje = _mensaje_cierre_escalamiento(
            tid,
            motivo=str(result.get("motivo") or ""),
            mensaje_ia=mensaje,
            nota_temas=_nota_temas_pendientes(ctx),
        )
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
                resp = (
                    f"Te ubiqué, {nombre}: la cuenta figura «{abonado.estado}». "
                    f"Saldo pendiente ${abonado.deuda_monto}. "
                    "¿Es por reactivar, pagar, o por otra consulta?"
                )
            else:
                resp = (
                    f"Listo {nombre}, ya te identifiqué. "
                    "¿Tu consulta es por internet, móvil IMOWI, o factura/deuda?"
                )
            if not pedi_saldo:
                ctx["saludo"] = True
                crepo.set_contexto(conv, ctx)
                db.commit()
            _enviar_respuesta(db, org_id, conv, resp, enviar_wa=(canal == "whatsapp"))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
                "abonado": crepo.abonado_to_dict(abonado),
            }

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
        _enviar_respuesta(db, org_id, conv, resp, enviar_wa=(canal == "whatsapp"))
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
        abonado = _intentar_identificar_por_dni(db, org_id, texto)
        if abonado:
            conv.abonado_id = abonado.id
            ctx["identificado"] = True
            ctx["dni"] = abonado.dni
            ctx.pop("invitado", None)
            crepo.set_contexto(conv, ctx)
            db.commit()

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
                    "¿tu consulta es por internet (fibra, radio o ADSL), móvil IMOWI, "
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
            _enviar_respuesta(db, org_id, conv, resp, enviar_wa=(canal == "whatsapp"))
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
            _enviar_respuesta(db, org_id, conv, resp, enviar_wa=(canal == "whatsapp"))
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

    # Doble tema (internet + factura): esperar elección de prioridad
    if intencion == "multi_tema":
        elegida = resolver_prioridad_tema(texto)
        if not elegida:
            resp = (
                "Decime por cuál empezamos: ¿el internet o el aumento de la factura?"
            )
            _enviar_respuesta(db, org_id, conv, resp, enviar_wa=(canal == "whatsapp"))
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
                    "Veo dos cosas: el móvil IMOWI y el tema de la factura. "
                    "¿Arrancamos por el móvil o por el aumento?"
                )
            _enviar_respuesta(db, org_id, conv, resp, enviar_wa=(canal == "whatsapp"))
            return {
                "ok": True,
                "modo": "bot",
                "conversacion_id": conv.id,
                "respuesta": resp,
                "estado": conv.estado,
                "intencion": "multi_tema",
            }
        intencion = clasificar_intencion(texto, servicio_abo)
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
                # Invitado: no inventar saldo ni soltar QR sin cuenta.
                pregunta = (
                    "En modo invitado no veo tu cuenta. "
                    "Pasame tu DNI (solo el número) y te digo si hay saldo pendiente "
                    "y cómo abonar."
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
        # Pagos/QR en corte: plantilla fija. Facturación ya va por diagnóstico IA.
        if usar_llama and intencion != "corte_deuda":
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
            ctx=ctx,
        )
        resp = _mensaje_cierre_escalamiento(
            tid,
            motivo=motivo,
            mensaje_ia="",
            nota_temas=_nota_temas_pendientes(ctx),
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
        _enviar_respuesta(db, org_id, conv, resp, enviar_wa=(canal == "whatsapp"))
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
