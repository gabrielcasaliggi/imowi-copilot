"""Consulta Radius/UISP una vez por conversación en reclamos de internet."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.estate.models import Abonado

logger = logging.getLogger("operations_hub")


def _marcar_pasos_rama_pppoe(ctx: dict) -> None:
    """La sesión Radius cubre pasos del playbook: no volver a preguntarlos."""
    from app.services.conexion_pppoe import enriquecer_pasos_por_pppoe

    ctx["pasos_cubiertos"] = enriquecer_pasos_por_pppoe(
        list(ctx.get("pasos_cubiertos") or []),
        str(ctx.get("pppoe_triage") or ""),
        rama=str(ctx.get("pppoe_rama") or ""),
    )


_INTENCIONES_PPPOE = frozenset({
    "internet",
    "internet_ftth",
    "internet_adsl",
    "internet_radio",
    "internet_lento",
    "internet_intermitente",
    "wifi",
})


def _talvez_mensaje_pppoe(
    db: Session,
    abonado: Abonado | None,
    ctx: dict,
    intencion: str,
) -> str | None:
    """Consulta Radius una vez por conversación en reclamos de internet."""
    from app.domain.flujos_abonado import tiene_internet_fijo
    from app.services.canal_abonado import _deuda_positiva, _servicio_abonado

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
        if estado.servicio:
            from app.domain.flujos_abonado import playbook_internet_desde_tipo_servicio

            pb_tech = playbook_internet_desde_tipo_servicio(
                estado.servicio.service_type_code,
                estado.servicio.service_type_label,
            )
            if pb_tech:
                ctx["tecnologia_acceso"] = pb_tech
                cub = list(ctx.get("pasos_cubiertos") or [])
                if "tipo_acceso" not in cub:
                    cub.append("tipo_acceso")
                ctx["pasos_cubiertos"] = cub

        rama = clasificar_rama_pppoe(estado)
        ctx["pppoe_rama"] = rama
        ctx["pppoe_triage"] = triage_pppoe_para_prompt(estado)
        _marcar_pasos_rama_pppoe(ctx)
        ctx["pppoe_resumen"] = estado.resumen_prompt()
        if estado.sesion:
            ctx["pppoe_ip"] = estado.sesion.public_ip or ""
            ctx["pppoe_uptime"] = estado.sesion.uptime or ""
        if estado.servicio:
            from app.services.velocidad_plan import extraer_mbps_plan

            prod = (estado.servicio.product or estado.servicio.label or "").strip()
            if prod:
                ctx["pppoe_producto"] = prod
            mbps = extraer_mbps_plan(prod, estado.servicio.service_type_label)
            if mbps is not None:
                ctx["pppoe_plan_mbps"] = f"{mbps:g}"

        login = (estado.servicio.login if estado.servicio else "") or ""
        es_radio = (intencion or "").strip() == "internet_radio" or (
            ctx.get("tecnologia_acceso") == "internet_radio"
        )
        msg_uisp = None
        cpe = None
        if login:
            try:
                from app.services.conexion_uisp import (
                    aplicar_uisp_a_ctx,
                    consultar_cpe_uisp,
                    es_servicio_radio,
                    mensaje_abonado_uisp,
                    resolve_uisp_client,
                )

                if resolve_uisp_client(db) is not None:
                    if not es_radio:
                        es_radio = es_servicio_radio(estado.servicio)
                    cpe = consultar_cpe_uisp(login, db=db)
                    aplicar_uisp_a_ctx(ctx, cpe)
                    msg_uisp = mensaje_abonado_uisp(cpe, es_radio=es_radio)
            except Exception:
                logger.exception("UISP check falló en canal")

        msg_bcm = None
        onu = None
        es_ftth = (intencion or "").strip() == "internet_ftth" or (
            ctx.get("tecnologia_acceso") == "internet_ftth"
        )
        es_adsl = (intencion or "").strip() == "internet_adsl" or (
            ctx.get("tecnologia_acceso") == "internet_adsl"
        )
        if not es_radio and not es_adsl:
            try:
                from app.services.conexion_bcm import (
                    aplicar_bcm_a_ctx,
                    consultar_onu_bcm,
                    es_servicio_ftth,
                    mensaje_abonado_bcm,
                    resolve_bcm_client,
                    resolver_numero_cliente_bcm,
                )

                if resolve_bcm_client(db) is not None:
                    if not es_ftth:
                        es_ftth = es_servicio_ftth(estado.servicio)
                    nro = str(getattr(abonado, "client_number", "") or "").strip()
                    if not nro and estado.servicio is not None:
                        nro = str(getattr(estado.servicio, "base_account_number", "") or "").strip()
                    if not nro:
                        nro = resolver_numero_cliente_bcm(abonado, db)
                    if nro:
                        onu = consultar_onu_bcm(nro, db=db)
                        aplicar_bcm_a_ctx(ctx, onu)
                        msg_bcm = mensaje_abonado_bcm(
                            onu, es_ftth=es_ftth or onu.encontrado
                        )
            except Exception:
                logger.exception("BCM check falló en canal")

        bcm_ok = "onu_ftth_enlace_ok" in str(ctx.get("bcm_triage") or "")
        uisp_ok = "cpe_radio_enlace_ok" in str(ctx.get("uisp_triage") or "")
        uisp_alerta = bool(msg_uisp) and not uisp_ok
        bcm_alerta = bool(msg_bcm) and not bcm_ok

        if uisp_alerta:
            ctx["pppoe_rama"] = str(ctx.get("pppoe_rama") or "")
            return msg_uisp

        if bcm_alerta:
            return msg_bcm

        msg = mensaje_abonado_pppoe(
            estado,
            deuda_positiva=_deuda_positiva(abonado),
        )
        from app.services.barra_senal import (
            anexar_antes_de_preguntas,
            bloque_potencia_onu,
            bloque_senal_antena,
        )

        barra = ""
        if onu is not None and onu.encontrado and onu.rx_dbm is not None:
            barra = bloque_potencia_onu(onu.rx_dbm)
        elif cpe is not None and cpe.encontrado and cpe.signal_dbm is not None:
            barra = bloque_senal_antena(cpe.signal_dbm)

        if msg and barra:
            if uisp_ok:
                ctx["pppoe_rama"] = "wifi_lan"
                _marcar_pasos_rama_pppoe(ctx)
            if bcm_ok:
                ctx["pppoe_rama"] = "wifi_lan"
                _marcar_pasos_rama_pppoe(ctx)
            return anexar_antes_de_preguntas(msg, barra)

        if msg_uisp:
            if uisp_ok:
                ctx["pppoe_rama"] = "wifi_lan"
                _marcar_pasos_rama_pppoe(ctx)
            return msg_uisp

        if msg_bcm:
            if bcm_ok:
                ctx["pppoe_rama"] = "wifi_lan"
                _marcar_pasos_rama_pppoe(ctx)
            return msg_bcm

        if msg:
            return msg
        logger.info(
            "PPPoE sin mensaje útil dni=***%s err=%s online=%s",
            str(abonado.dni)[-3:],
            (estado.error or "")[:80],
            estado.online,
        )
        return None
    except Exception:
        logger.exception("PPPoE check falló en canal")
        return None
