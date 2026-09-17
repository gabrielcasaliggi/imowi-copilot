"""Orquestación portal: estado de conectividad del abonado (C2 Home Status).

No escribe ni lee ConversacionCanal.contexto. No expone infra al DTO.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.estate.models import Abonado
from app.services import billtrack as bt
from app.services import connectivity_cache as ccache
from app.services.connectivity_decision import decidir
from app.services.connectivity_evidence import (
    AccessEvidence,
    AccessTechnology,
    CatalogEvidence,
    ConnectivityBundle,
    ConnectivityDecision,
    Freshness,
    IncidentEvidence,
    ServiceRef,
    SessionEvidence,
    classify_provider_error,
    link_up_from_phy,
    map_calidad_to_quality,
)
from app.services.connectivity_result import build_technical_self_service_result

logger = logging.getLogger("operations_hub")


def _now() -> datetime:
    return datetime.now(UTC)


def _classify_provider_error(err: str) -> str:
    return classify_provider_error(err)


def _map_quality_optica(raw: str) -> str:
    return map_calidad_to_quality(raw)


def _map_quality_senal(raw: str) -> str:
    return map_calidad_to_quality(raw)


def _link_up_from_phy(
    *,
    online: bool | None,
    quality: str,
    has_metric: bool,
) -> bool | None:
    """Deriva link_up para producto sin afirmar caída por heurísticas ambiguas.

    BCM a veces marca offline (p.ej. uptime 0 / LOS residual) aunque el
    diagnóstico TR-069 muestre RX óptima. Si hay métrica usable (RX/señal)
    con calidad buena/aceptable/poor, el enlace físico existe.
    """
    return link_up_from_phy(online=online, quality=quality, has_metric=has_metric)


def _access_technology(svc: ServiceRef | Any) -> AccessTechnology:
    from app.domain.flujos_abonado import playbook_internet_desde_tipo_servicio

    code = str(getattr(svc, "type_code", None) or getattr(svc, "service_type_code", "") or "")
    label = str(
        getattr(svc, "type_label", None) or getattr(svc, "service_type_label", "") or ""
    )
    pb = playbook_internet_desde_tipo_servicio(code, label)
    if pb == "internet_ftth":
        return "ftth"
    if pb == "internet_radio":
        return "radio"
    if pb == "internet_adsl":
        return "other"
    return "unknown"


def _label_servicio(svc: Any) -> str:
    for key in ("product", "label", "service_type_label"):
        val = str(getattr(svc, key, "") or "").strip()
        if val:
            return val
    return "Internet"


def _to_service_ref(svc: Any) -> ServiceRef | None:
    sid = str(getattr(svc, "id", "") or "").strip()
    if not sid:
        return None
    code = str(getattr(svc, "service_type_code", "") or "").strip().upper()
    if code not in bt.SERVICE_TYPE_CONECTIVIDAD:
        return None
    if not bt.servicio_habilitado(svc):
        return None
    login = str(getattr(svc, "login", "") or "").strip()
    if not login:
        return None
    return ServiceRef(
        id=sid,
        label=_label_servicio(svc),
        type_code=code,
        type_label=str(getattr(svc, "service_type_label", "") or "").strip(),
        login=login,
        base_account_number=str(getattr(svc, "base_account_number", "") or "").strip(),
        product=str(getattr(svc, "product", "") or "").strip(),
    )


def _load_catalog(db: Session, abonado: Abonado) -> list[ServiceRef]:
    dni = str(getattr(abonado, "dni", "") or "").strip()
    client_number = str(getattr(abonado, "client_number", "") or "").strip()
    raw: list[Any] = []
    try:
        if client_number:
            raw = bt.lookup_servicios_conectividad(
                client_number=client_number, db=db
            )
        elif dni:
            raw = bt.lookup_servicios_conectividad_por_dni(dni=dni, db=db)
    except Exception:
        logger.exception("portal_connectivity: catálogo BillTrack falló")
        return []
    out: list[ServiceRef] = []
    seen: set[str] = set()
    for svc in raw or []:
        ref = _to_service_ref(svc)
        if ref is None or ref.id in seen:
            continue
        seen.add(ref.id)
        out.append(ref)
    return out


def _resolve_catalog(
    services: list[ServiceRef],
    service_id: str | None,
) -> CatalogEvidence:
    sid = (service_id or "").strip()
    if not services:
        return CatalogEvidence(
            services=[],
            selected=None,
            needs_selection=False,
            access_technology="unknown",
        )
    if len(services) > 1 and not sid:
        return CatalogEvidence(
            services=services,
            selected=None,
            needs_selection=True,
            access_technology="unknown",
        )
    selected: ServiceRef | None = None
    if sid:
        for s in services:
            if s.id == sid:
                selected = s
                break
        if selected is None:
            raise HTTPException(404, "Servicio no encontrado")
    else:
        selected = services[0]
    tech = _access_technology(selected)
    return CatalogEvidence(
        services=services,
        selected=selected,
        needs_selection=False,
        access_technology=tech,
    )


def _probe_bcm(
    db: Session,
    abonado: Abonado,
    selected: ServiceRef,
) -> AccessEvidence:
    from app.services.conexion_bcm import (
        consultar_onu_bcm_mejor_esfuerzo,
        resolve_bcm_client,
    )

    now = _now()
    if resolve_bcm_client(db) is None:
        return AccessEvidence(
            kind="ftth",
            available=False,
            error="unavailable",
            observed_at=now,
        )
    t0 = time.monotonic()
    try:
        onu = consultar_onu_bcm_mejor_esfuerzo(
            abonado,
            db=db,
            base_account_number=selected.base_account_number,
        )
    except Exception as exc:
        logger.exception("portal_connectivity: BCM probe falló")
        return AccessEvidence(
            kind="ftth",
            available=False,
            error=_classify_provider_error(str(exc)),  # type: ignore[arg-type]
            observed_at=now,
        )
    latency_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "portal_connectivity phy=bcm latency_ms=%s found=%s online=%s rx=%s "
        "calidad=%s err=%s",
        latency_ms,
        bool(onu.encontrado),
        onu.online,
        onu.rx_dbm,
        onu.calidad_optica,
        bool(onu.error),
    )
    if onu.error and not onu.encontrado:
        err = _classify_provider_error(onu.error)
        return AccessEvidence(
            kind="ftth",
            available=False,
            found=False,
            error=err if err != "none" else "other",  # type: ignore[arg-type]
            observed_at=now,
        )
    if not onu.encontrado:
        return AccessEvidence(
            kind="ftth",
            available=True,
            found=False,
            link_up=None,
            quality="unknown",
            error="not_found",
            observed_at=now,
        )
    quality = _map_quality_optica(onu.calidad_optica)
    link_up = _link_up_from_phy(
        online=onu.online,
        quality=quality,
        has_metric=onu.rx_dbm is not None,
    )
    return AccessEvidence(
        kind="ftth",
        available=True,
        found=True,
        link_up=link_up,
        quality=quality,  # type: ignore[arg-type]
        error="none",
        observed_at=now,
    )


def _probe_uisp(db: Session, selected: ServiceRef) -> AccessEvidence:
    from app.services.conexion_uisp import consultar_cpe_uisp, resolve_uisp_client

    now = _now()
    if resolve_uisp_client(db) is None:
        return AccessEvidence(
            kind="radio",
            available=False,
            error="unavailable",
            observed_at=now,
        )
    t0 = time.monotonic()
    try:
        cpe = consultar_cpe_uisp(selected.login, db=db)
    except Exception as exc:
        logger.exception("portal_connectivity: UISP probe falló")
        return AccessEvidence(
            kind="radio",
            available=False,
            error=_classify_provider_error(str(exc)),  # type: ignore[arg-type]
            observed_at=now,
        )
    latency_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "portal_connectivity phy=uisp latency_ms=%s found=%s online=%s signal=%s "
        "calidad=%s err=%s",
        latency_ms,
        bool(cpe.encontrado),
        cpe.online,
        cpe.signal_dbm,
        cpe.calidad_senal,
        bool(cpe.error),
    )
    if cpe.error and not cpe.encontrado:
        err = _classify_provider_error(cpe.error)
        return AccessEvidence(
            kind="radio",
            available=False,
            found=False,
            error=err if err != "none" else "other",  # type: ignore[arg-type]
            observed_at=now,
        )
    if not cpe.encontrado:
        return AccessEvidence(
            kind="radio",
            available=True,
            found=False,
            link_up=None,
            quality="unknown",
            error="not_found",
            observed_at=now,
        )
    quality = _map_quality_senal(cpe.calidad_senal)
    link_up = _link_up_from_phy(
        online=cpe.online,
        quality=quality,
        has_metric=cpe.signal_dbm is not None,
    )
    return AccessEvidence(
        kind="radio",
        available=True,
        found=True,
        link_up=link_up,
        quality=quality,  # type: ignore[arg-type]
        error="none",
        observed_at=now,
    )


def _probe_session(
    db: Session,
    abonado: Abonado,
    selected: ServiceRef,
) -> SessionEvidence:
    """Consulta Radius por login del servicio. NAS solo interno."""
    from app.services.conexion_pppoe import consultar_conexion_pppoe, resolve_radius_client

    now = _now()
    if resolve_radius_client(db) is None:
        return SessionEvidence(available=False, error="unavailable", observed_at=now)
    t0 = time.monotonic()
    try:
        estado = consultar_conexion_pppoe(
            dni=str(getattr(abonado, "dni", "") or ""),
            client_number=str(getattr(abonado, "client_number", "") or ""),
            login=selected.login,
            db=db,
        )
    except Exception as exc:
        logger.exception("portal_connectivity: Radius probe falló")
        return SessionEvidence(
            available=False,
            error=_classify_provider_error(str(exc)),  # type: ignore[arg-type]
            observed_at=now,
        )
    latency_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "portal_connectivity session=radius latency_ms=%s has_session=%s err=%s",
        latency_ms,
        bool(estado.sesion and estado.sesion.online),
        bool(estado.error),
    )
    if estado.error and estado.sesion is None:
        err = _classify_provider_error(estado.error)
        # "radius api no configurada" ya cubierto; otros errores
        if err == "none":
            err = "other"
        return SessionEvidence(
            available=False,
            error=err,  # type: ignore[arg-type]
            observed_at=now,
        )
    sesion = estado.sesion
    if sesion is None:
        return SessionEvidence(
            available=True,
            session_present=False,
            error="none",
            observed_at=now,
        )
    if sesion.error and not sesion.online:
        return SessionEvidence(
            available=True,
            session_present=False,
            nas_internal=str(sesion.nas or "").strip(),
            uptime_raw=str(sesion.uptime or "").strip(),
            error="none",
            observed_at=now,
        )
    present = bool(sesion.online)
    return SessionEvidence(
        available=True,
        session_present=present,
        nas_internal=str(sesion.nas or "").strip(),
        uptime_raw=str(sesion.uptime or "").strip(),
        error="none",
        observed_at=now,
    )


def _resolve_incident(
    db: Session,
    org_id: str,
    session: SessionEvidence,
) -> IncidentEvidence:
    from app.services.outages import (
        mensaje_desde_outage,
        outage_activo_para_nas,
    )

    nas = (session.nas_internal or "").strip()
    if not nas:
        return IncidentEvidence(matched=False)
    try:
        outage = outage_activo_para_nas(db, org_id, nas)
    except Exception:
        logger.exception("portal_connectivity: outage lookup falló")
        return IncidentEvidence(matched=False)
    if outage is None or (outage.estado or "").strip().lower() != "activo":
        return IncidentEvidence(matched=False)
    msg = (outage.mensaje_cliente or "").strip()
    if not msg:
        try:
            msg = mensaje_desde_outage(outage)
        except Exception:
            msg = ""
    # Evitar filtrar nombres de NAS al mensaje si la plantilla los incluye
    eta_ok = str(outage.eta_validada or "").strip().lower() in (
        "sí",
        "si",
        "1",
        "true",
        "yes",
    )
    return IncidentEvidence(
        matched=True,
        outage_id=str(outage.id),
        started_at=outage.started_at,
        alcance=str(outage.alcance or "").strip().lower() or "total",
        mensaje=msg,
        eta_minutos=int(outage.eta_minutos) if outage.eta_minutos else None,
        eta_validada=eta_ok,
        estado=str(outage.estado or ""),
    )


def _service_option(ref: ServiceRef) -> dict[str, str]:
    return {
        "id": ref.id,
        "label": ref.label,
        "access_technology": _access_technology(ref),
    }


def _incident_from_tss(tss) -> dict[str, Any] | None:
    """Proyección customer-safe. eta_at se conserva vacío (contrato Mobile)."""
    inc = tss.incident
    if inc is None:
        return None
    return {
        "id": inc.id,
        "started_at": inc.started_at.isoformat() if inc.started_at else "",
        "eta_minutes": inc.eta_minutes,
        "eta_confirmed": inc.eta_confirmed,
        "eta_at": None,
        "message": inc.message,
        "scope": inc.scope,
    }


def _build_response(
    *,
    decision: ConnectivityDecision,
    bundle: ConnectivityBundle,
    freshness: Freshness,
    checked_at: datetime,
) -> dict[str, Any]:
    """DTO portal = TSS + metadatos de catálogo. No reinterpreta evidencia."""
    tss = build_technical_self_service_result(
        decision,
        bundle,
        freshness=freshness,
        checked_at=checked_at,
    )
    catalog = bundle.catalog
    selected = catalog.selected
    return {
        "status": tss.diagnosis.status,
        "freshness": tss.freshness.freshness,
        "checked_at": tss.freshness.checked_at.isoformat(),
        "message": tss.copy.customer_message,
        "access_technology": tss.subject.access_technology,
        "service": (
            {"id": selected.id, "label": selected.label} if selected else None
        ),
        "incident": _incident_from_tss(tss),
        "actions": {
            "can_open_chat": True,
            "chat_hint": tss.copy.chat_hint,
        },
        "needs_service_selection": bool(catalog.needs_selection),
        "services": (
            [_service_option(s) for s in catalog.services]
            if catalog.needs_selection
            else None
        ),
        "reason_code": tss.diagnosis.reason_code,
        "evidence": {
            "session_present": tss.evidence_safe.session_present,
            "access_link_up": tss.evidence_safe.access_link_up,
            "access_quality": tss.evidence_safe.access_quality,
        },
        "recommendation": {
            "recommended_action": tss.recommendation.recommended_action,
            "available_actions": list(tss.recommendation.available_actions),
        },
    }


def evaluar_conectividad_portal(
    db: Session,
    *,
    org_id: str,
    abonado: Abonado,
    service_id: str | None = None,
    request_id: str = "",
) -> dict[str, Any]:
    """Punto de entrada del endpoint. Nunca toca ConversacionCanal."""
    checked_at = _now()
    abo_id = str(abonado.id)
    sid_q = (service_id or "").strip()

    # Cache solo con servicio concreto
    if sid_q:
        cached = ccache.get_fresh(org_id, abo_id, sid_q)
        if cached is not None:
            out = dict(cached)
            out["checked_at"] = checked_at.isoformat()
            out["freshness"] = "cached"
            logger.info(
                "portal_connectivity cache=hit org=%s abo=%s svc=%s status=%s req=%s",
                org_id,
                abo_id,
                sid_q,
                out.get("status"),
                request_id,
            )
            return out

    services = _load_catalog(db, abonado)
    catalog = _resolve_catalog(services, sid_q or None)

    if catalog.needs_selection:
        bundle = ConnectivityBundle(
            catalog=catalog,
            access=AccessEvidence(),
            session=SessionEvidence(),
            incident=IncidentEvidence(),
        )
        body = _build_response(
            decision=decidir(bundle),
            bundle=bundle,
            freshness="none",
            checked_at=checked_at,
        )
        logger.info(
            "portal_connectivity cache=miss selection org=%s abo=%s req=%s",
            org_id,
            abo_id,
            request_id,
        )
        return body

    if not catalog.selected:
        bundle = ConnectivityBundle(
            catalog=catalog,
            access=AccessEvidence(available=False, error="unavailable"),
            session=SessionEvidence(available=False, error="unavailable"),
            incident=IncidentEvidence(),
        )
        return _build_response(
            decision=decidir(bundle),
            bundle=bundle,
            freshness="none",
            checked_at=checked_at,
        )

    selected = catalog.selected
    tech = catalog.access_technology

    # Session primero: alimenta NAS para outage
    session = _probe_session(db, abonado, selected)

    access = AccessEvidence(kind="none")
    if tech == "ftth":
        access = _probe_bcm(db, abonado, selected)
    elif tech == "radio":
        access = _probe_uisp(db, selected)
    # other/unknown: sin phy

    incident = _resolve_incident(db, org_id, session)

    bundle = ConnectivityBundle(
        catalog=catalog,
        access=access,
        session=session,
        incident=incident,
    )
    decision = decidir(bundle)
    body = _build_response(
        decision=decision,
        bundle=bundle,
        freshness="live",
        checked_at=checked_at,
    )

    logger.info(
        "portal_connectivity cache=miss org=%s abo=%s svc=%s tech=%s "
        "status=%s reason=%s freshness=live outage=%s ttl=%s req=%s",
        org_id,
        abo_id,
        selected.id,
        tech,
        decision.status,
        decision.reason_code,
        incident.matched,
        ccache.ttl_seconds(),
        request_id,
    )

    if selected.id:
        ccache.put(org_id, abo_id, selected.id, body)
    return body
