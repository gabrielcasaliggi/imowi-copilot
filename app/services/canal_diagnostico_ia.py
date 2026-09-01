"""Diagnóstico N1 con IA (playbook como checklist).

Cuerpo idéntico al orquestador; resuelve helpers desde `canal_abonado` en
runtime para no romper monkeypatches de tests.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.estate.models import Abonado, ConversacionCanal


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
    from app.services import canal_abonado as c
    from app.services.canal_pppoe import _talvez_mensaje_pppoe
    from app.services.diagnostico_n1 import diagnosticar_turno

    resolve_canal_diagnostico_ia = c.resolve_canal_diagnostico_ia
    es_intencion_diagnostico = c.es_intencion_diagnostico
    _responder_consulta_saldo = c._responder_consulta_saldo
    _responder_pendiente_pago_o_corte = c._responder_pendiente_pago_o_corte
    _sincronizar_login_desde_mensaje = c._sincronizar_login_desde_mensaje
    _responder_seleccion_cuenta_internet = c._responder_seleccion_cuenta_internet
    _responder_consulta_senal_antena = c._responder_consulta_senal_antena
    _responder_paso_diagnostico_wifi = c._responder_paso_diagnostico_wifi
    _responder_confirmacion_mejora_wifi = c._responder_confirmacion_mejora_wifi
    indica_resuelto = c.indica_resuelto
    _cliente_desiste_o_resuelto = c._cliente_desiste_o_resuelto
    _cerrar_consulta_resuelta = c._cerrar_consulta_resuelta
    _primer_nombre_cliente = c._primer_nombre_cliente
    _enviar_respuesta = c._enviar_respuesta
    _enviar_externo = c._enviar_externo
    _cliente_indica_solo_wifi = c._cliente_indica_solo_wifi
    _cliente_cable_ok = c._cliente_cable_ok
    crepo = c.crepo
    _playbooks = c._playbooks
    _kb_fragmento = c._kb_fragmento
    es_escape_agente = c.es_escape_agente
    pide_humano_en_flujo_activo = c.pide_humano_en_flujo_activo
    refinar_playbook_internet = c.refinar_playbook_internet
    es_afirmacion_estado_movil = c.es_afirmacion_estado_movil
    _contener_b2b_sin_ticket_n2 = c._contener_b2b_sin_ticket_n2
    _crear_ticket_n2 = c._crear_ticket_n2
    _mensaje_cierre_escalamiento = c._mensaje_cierre_escalamiento
    _nota_temas_pendientes = c._nota_temas_pendientes
    enviar_encuesta_cierre = c.enviar_encuesta_cierre
    ORIGEN_BOT = c.ORIGEN_BOT
    _mensaje_cierre_calido = c._mensaje_cierre_calido

    if not usar_llama or not resolve_canal_diagnostico_ia(db):
        return None
    if not es_intencion_diagnostico(intencion):
        return None

    from app.services.diagnostico_n1 import _cliente_pendiente_pago_o_corte

    if abonado:
        from app.services.diagnostico_n1 import _cliente_consulta_saldo

        if _cliente_consulta_saldo(texto):
            return _responder_consulta_saldo(
                db, org_id, conv, abonado, ctx, canal=canal
            )

    if abonado and _cliente_pendiente_pago_o_corte(texto):
        return _responder_pendiente_pago_o_corte(
            db, org_id, conv, abonado, ctx, canal=canal
        )

    if abonado:
        _sincronizar_login_desde_mensaje(db, abonado, ctx, texto)

    multi_cta = _responder_seleccion_cuenta_internet(
        db, org_id, conv, abonado, texto, canal=canal, ctx=ctx, intencion=intencion
    )
    if multi_cta is not None:
        return multi_cta

    senal_ant = _responder_consulta_senal_antena(
        db, org_id, conv, abonado, texto, canal=canal, ctx=ctx, intencion=intencion
    )
    if senal_ant is not None:
        return senal_ant

    paso_wifi = _responder_paso_diagnostico_wifi(
        db, org_id, conv, texto, canal=canal, ctx=ctx, intencion=intencion
    )
    if paso_wifi is not None:
        return paso_wifi

    conf_wifi = _responder_confirmacion_mejora_wifi(
        db, org_id, conv, texto, canal=canal, ctx=ctx, intencion=intencion
    )
    if conf_wifi is not None:
        return conf_wifi

    # Cierre: no seguir con ramas Wi‑Fi/PPPoE si el abonado ya resolvió
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
    # No usar pide_humano() suelto: «técnico» del menú no debe forzar escalate
    forzar = bool(
        es_escape_agente(texto)
        or pide_humano_en_flujo_activo(texto, ctx)
    )

    from app.services.eco_voice import build_contexto_abonado

    extras_ctx: dict[str, str] = {}
    if ctx.get("pppoe_resumen"):
        extras_ctx["pppoe_resumen"] = str(ctx.get("pppoe_resumen") or "")
    if ctx.get("pppoe_triage"):
        extras_ctx["pppoe_triage"] = str(ctx.get("pppoe_triage") or "")
    if ctx.get("uisp_resumen"):
        extras_ctx["uisp_resumen"] = str(ctx.get("uisp_resumen") or "")
    if ctx.get("uisp_triage"):
        extras_ctx["uisp_triage"] = str(ctx.get("uisp_triage") or "")
    if ctx.get("uisp_signal_dbm"):
        extras_ctx["uisp_signal_dbm"] = str(ctx.get("uisp_signal_dbm") or "")
    if ctx.get("uisp_calidad_senal"):
        extras_ctx["uisp_calidad_senal"] = str(ctx.get("uisp_calidad_senal") or "")
    if ctx.get("pppoe_plan_mbps"):
        extras_ctx["pppoe_plan_mbps"] = str(ctx.get("pppoe_plan_mbps") or "")
    if ctx.get("pppoe_producto"):
        extras_ctx["pppoe_producto"] = str(ctx.get("pppoe_producto") or "")

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

    if accion == "escalate" and intencion == "internet":
        from app.services.diagnostico_n1 import _MOTIVOS_OPTICOS

        motivo_e = str(result.get("motivo") or "")
        if motivo_e not in _MOTIVOS_OPTICOS and not any(
            x in motivo_e.lower() for x in ("agente", "humano", "pedido")
        ):
            refinada = refinar_playbook_internet(texto)
            if refinada:
                intencion = refinada
                ctx["intencion"] = refinada
                ctx["paso_idx"] = 0
                ctx["pasos_cubiertos"] = []
                conv.servicio_detectado = refinada
            accion = "ask"
            result = dict(result)
            result["accion"] = "ask"
            pasos_i = _playbooks(db).get(intencion) or []
            mensaje = (
                pasos_i[0].pregunta
                if pasos_i
                else "¿Tenés fibra (cajita blanca), antena en el techo, o internet por teléfono (ADSL)?"
            )
            crepo.set_contexto(conv, ctx)
            db.commit()

    if accion == "escalate" and intencion in ("movil", "movil_datos", "movil_llamadas"):
        from app.services.diagnostico_n1 import (
            _MSG_APN_ANDROID,
            _MSG_APN_IOS,
            _MSG_BONO_OV,
            datos_agotados_abono,
            detectar_so_movil,
            es_solo_modelo_celular,
        )

        if es_afirmacion_estado_movil(texto):
            accion = "ask"
            mensaje = mensaje or _MSG_BONO_OV
        elif datos_agotados_abono(texto, historial):
            accion = "ask"
            mensaje = _MSG_BONO_OV
            if "consumo_paquete" not in cubiertos:
                cubiertos.append("consumo_paquete")
                ctx["pasos_cubiertos"] = cubiertos
        elif es_solo_modelo_celular(texto):
            accion = "ask"
            so_m = detectar_so_movil(texto, historial)
            mensaje = _MSG_APN_ANDROID if so_m != "ios" else _MSG_APN_IOS
            if "so_dispositivo" not in cubiertos:
                cubiertos.append("so_dispositivo")
                ctx["pasos_cubiertos"] = cubiertos

    if accion == "escalate":
        from app.services.diagnostico_n1 import _cierra_consulta_facturacion

        if _cierra_consulta_facturacion(texto) or _cliente_desiste_o_resuelto(texto):
            return _cerrar_consulta_resuelta(
                db,
                org_id,
                conv,
                canal=canal,
            )
        contenido_b2b = _contener_b2b_sin_ticket_n2(
            db,
            org_id,
            conv,
            texto,
            canal=canal,
            ctx=ctx,
            intencion=intencion,
        )
        if contenido_b2b is not None:
            return contenido_b2b
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
    if intencion in ("movil", "movil_datos", "movil_llamadas"):
        from app.services.diagnostico_n1 import sanitizar_apn_en_texto

        mensaje = sanitizar_apn_en_texto(mensaje)
    from app.services.diagnostico_n1 import aplicar_guardrails_cambio_clave_wifi

    g_wifi = aplicar_guardrails_cambio_clave_wifi(
        mensaje=mensaje,
        mensaje_cliente=texto,
        intencion=intencion,
        accion=accion,
    )
    if g_wifi.get("motivo"):
        mensaje = g_wifi["mensaje"] or mensaje
        if g_wifi.get("paso_cubierto"):
            cubiertos = list(ctx.get("pasos_cubiertos") or [])
            if g_wifi["paso_cubierto"] not in cubiertos:
                cubiertos.append(g_wifi["paso_cubierto"])
                ctx["pasos_cubiertos"] = cubiertos
                crepo.set_contexto(conv, ctx)
                db.commit()
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
