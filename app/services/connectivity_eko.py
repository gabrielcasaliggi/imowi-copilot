"""Adaptador thin: sondas ya obtenidas por Eko → motor común de conectividad.

No es un segundo motor. No hace I/O OSS. No escribe Wi-Fi.
Mapea ONU/CPE/PPP/outage ya consultados a ConnectivityBundle, llama decidir()
y proyecta TechnicalSelfServiceResult para el contexto conversacional.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.services.connectivity_decision import decidir
from app.services.connectivity_evidence import (
    AccessEvidence,
    AccessTechnology,
    CatalogEvidence,
    ConnectivityBundle,
    Freshness,
    IncidentEvidence,
    ReasonCode,
    ServiceRef,
    SessionEvidence,
    classify_provider_error,
    link_up_from_phy,
    map_calidad_to_quality,
)
from app.services.connectivity_result import (
    TechnicalSelfServiceResult,
    build_technical_self_service_result,
)

TSS_CTX_KEYS = (
    "tss_status",
    "tss_reason_code",
    "tss_message_key",
    "tss_service_id",
    "tss_access_technology",
    "tss_freshness",
    "tss_checked_at",
    "tss_incident_id",
    "tss_eko_branch",
)

# Compatibilidad conversacional: reason canónico → rama histórica de Eko.
# No cambia el vocabulario de decidir().
_BRANCH_BY_REASON: dict[str, str] = {
    "incident_active": "outage",
    "no_session": "sin_sesion",
    "sources_unavailable": "unknown_sources",
    "insufficient_data": "unknown_insufficient",
    "service_selection_required": "seleccion_cuenta",
}


def conversational_branch_for(
    reason_code: ReasonCode | None,
    *,
    status: str = "",
    tech: str = "",
) -> str:
    """Hint de rama conversacional. No sustituye reason_code."""
    if reason_code == "access_link_down":
        return "cpe_offline" if tech == "radio" else "onu_offline"
    if reason_code == "link_quality_poor":
        return "senal_mala" if tech == "radio" else "potencia_mala"
    if not reason_code and status == "operational":
        return "enlace_ok"
    if not reason_code:
        return ""
    return _BRANCH_BY_REASON.get(reason_code, "")


def limpiar_tss_de_ctx(ctx: dict) -> None:
    for k in TSS_CTX_KEYS:
        ctx.pop(k, None)


def access_technology_from_flags(
    *,
    es_ftth: bool = False,
    es_radio: bool = False,
    es_adsl: bool = False,
    servicio: Any | None = None,
) -> AccessTechnology:
    if es_radio:
        return "radio"
    if es_ftth:
        return "ftth"
    if es_adsl:
        return "other"
    if servicio is not None:
        from app.domain.flujos_abonado import playbook_internet_desde_tipo_servicio

        pb = playbook_internet_desde_tipo_servicio(
            str(getattr(servicio, "service_type_code", "") or ""),
            str(getattr(servicio, "service_type_label", "") or ""),
        )
        if pb == "internet_ftth":
            return "ftth"
        if pb == "internet_radio":
            return "radio"
        if pb == "internet_adsl":
            return "other"
    return "unknown"


def service_ref_from_servicio(svc: Any | None) -> ServiceRef | None:
    if svc is None:
        return None
    label = ""
    for key in ("product", "label", "service_type_label"):
        val = str(getattr(svc, key, "") or "").strip()
        if val:
            label = val
            break
    if not label:
        label = "Internet"
    return ServiceRef(
        id=str(getattr(svc, "id", "") or "").strip(),
        label=label,
        type_code=str(getattr(svc, "service_type_code", "") or "").strip(),
        type_label=str(getattr(svc, "service_type_label", "") or "").strip(),
        login=str(getattr(svc, "login", "") or "").strip(),
        base_account_number=str(getattr(svc, "base_account_number", "") or "").strip(),
        product=str(getattr(svc, "product", "") or "").strip(),
    )


def catalog_from_servicio(
    servicio: Any | None,
    *,
    es_ftth: bool = False,
    es_radio: bool = False,
    es_adsl: bool = False,
    servicios: list[Any] | None = None,
    needs_selection: bool = False,
) -> CatalogEvidence:
    refs: list[ServiceRef] = []
    seen: set[str] = set()
    for raw in servicios or ([] if servicio is None else [servicio]):
        ref = service_ref_from_servicio(raw)
        if ref is None:
            continue
        key = ref.id or ref.login or str(id(ref))
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
    if needs_selection:
        return CatalogEvidence(
            services=refs,
            selected=None,
            needs_selection=True,
            access_technology="unknown",
        )
    selected = service_ref_from_servicio(servicio)
    tech = access_technology_from_flags(
        es_ftth=es_ftth,
        es_radio=es_radio,
        es_adsl=es_adsl,
        servicio=servicio,
    )
    return CatalogEvidence(
        services=refs or ([selected] if selected else []),
        selected=selected,
        needs_selection=False,
        access_technology=tech,
    )


def access_from_onu(onu: Any | None) -> AccessEvidence:
    """Mismo mapeo que Portal `_probe_bcm` sobre un EstadoOnuBcm ya leído."""
    now = datetime.now(UTC)
    if onu is None:
        return AccessEvidence(
            kind="ftth",
            available=False,
            error="unavailable",
            observed_at=now,
        )
    err_raw = str(getattr(onu, "error", "") or "")
    encontrado = bool(getattr(onu, "encontrado", False))
    if err_raw and not encontrado:
        err = classify_provider_error(err_raw)
        return AccessEvidence(
            kind="ftth",
            available=False,
            found=False,
            error="other" if err == "none" else err,
            observed_at=now,
        )
    if not encontrado:
        return AccessEvidence(
            kind="ftth",
            available=True,
            found=False,
            link_up=None,
            quality="unknown",
            error="not_found",
            observed_at=now,
        )
    quality = map_calidad_to_quality(str(getattr(onu, "calidad_optica", "") or ""))
    link_up = link_up_from_phy(
        online=getattr(onu, "online", None),
        quality=quality,
        has_metric=getattr(onu, "rx_dbm", None) is not None,
    )
    return AccessEvidence(
        kind="ftth",
        available=True,
        found=True,
        link_up=link_up,
        quality=quality,
        error="none",
        observed_at=now,
    )


def access_from_cpe(cpe: Any | None) -> AccessEvidence:
    """Mismo mapeo que Portal `_probe_uisp` sobre un EstadoCpeUisp ya leído."""
    now = datetime.now(UTC)
    if cpe is None:
        return AccessEvidence(
            kind="radio",
            available=False,
            error="unavailable",
            observed_at=now,
        )
    err_raw = str(getattr(cpe, "error", "") or "")
    encontrado = bool(getattr(cpe, "encontrado", False))
    if err_raw and not encontrado:
        err = classify_provider_error(err_raw)
        return AccessEvidence(
            kind="radio",
            available=False,
            found=False,
            error="other" if err == "none" else err,
            observed_at=now,
        )
    if not encontrado:
        return AccessEvidence(
            kind="radio",
            available=True,
            found=False,
            link_up=None,
            quality="unknown",
            error="not_found",
            observed_at=now,
        )
    quality = map_calidad_to_quality(str(getattr(cpe, "calidad_senal", "") or ""))
    link_up = link_up_from_phy(
        online=getattr(cpe, "online", None),
        quality=quality,
        has_metric=getattr(cpe, "signal_dbm", None) is not None,
    )
    return AccessEvidence(
        kind="radio",
        available=True,
        found=True,
        link_up=link_up,
        quality=quality,
        error="none",
        observed_at=now,
    )


def session_from_pppoe(estado: Any | None) -> SessionEvidence:
    """Mismo mapeo que Portal `_probe_session` sobre EstadoConexionPPPoE ya leído."""
    now = datetime.now(UTC)
    if estado is None:
        return SessionEvidence(available=False, error="unavailable", observed_at=now)
    err_raw = str(getattr(estado, "error", "") or "")
    sesion = getattr(estado, "sesion", None)
    if err_raw and sesion is None:
        err = classify_provider_error(err_raw)
        if err == "none":
            err = "other"
        return SessionEvidence(
            available=False,
            error=err,  # type: ignore[arg-type]
            observed_at=now,
        )
    if sesion is None:
        return SessionEvidence(
            available=True,
            session_present=False,
            error="none",
            observed_at=now,
        )
    if getattr(sesion, "error", "") and not getattr(sesion, "online", False):
        return SessionEvidence(
            available=True,
            session_present=False,
            nas_internal=str(getattr(sesion, "nas", "") or "").strip(),
            uptime_raw=str(getattr(sesion, "uptime", "") or "").strip(),
            error="none",
            observed_at=now,
        )
    return SessionEvidence(
        available=True,
        session_present=bool(getattr(sesion, "online", False)),
        nas_internal=str(getattr(sesion, "nas", "") or "").strip(),
        uptime_raw=str(getattr(sesion, "uptime", "") or "").strip(),
        error="none",
        observed_at=now,
    )


def incident_from_outage(outage: Any | None) -> IncidentEvidence:
    """Solo incidente activo. Histórico → matched=False."""
    if outage is None:
        return IncidentEvidence(matched=False)
    estado = str(getattr(outage, "estado", "") or "").strip().lower()
    oid = str(getattr(outage, "id", "") or "").strip()
    if estado != "activo":
        return IncidentEvidence(matched=False, outage_id=oid, estado=estado)
    eta_ok = str(getattr(outage, "eta_validada", "") or "").strip().lower() in (
        "sí",
        "si",
        "1",
        "true",
        "yes",
    )
    eta_raw = getattr(outage, "eta_minutos", None)
    try:
        eta_minutos = int(eta_raw) if eta_raw else None
    except (TypeError, ValueError):
        eta_minutos = None
    msg = str(getattr(outage, "mensaje_cliente", "") or "").strip()
    return IncidentEvidence(
        matched=True,
        outage_id=oid,
        started_at=getattr(outage, "started_at", None),
        alcance=str(getattr(outage, "alcance", "") or "").strip().lower() or "total",
        mensaje=msg,
        eta_minutos=eta_minutos,
        eta_validada=eta_ok,
        estado=str(getattr(outage, "estado", "") or ""),
    )


def bundle_from_probes(
    *,
    estado_pppoe: Any | None,
    onu: Any | None = None,
    cpe: Any | None = None,
    es_ftth: bool = False,
    es_radio: bool = False,
    es_adsl: bool = False,
    needs_selection: bool = False,
    incident: IncidentEvidence | None = None,
) -> ConnectivityBundle:
    servicio = getattr(estado_pppoe, "servicio", None) if estado_pppoe is not None else None
    servicios = list(getattr(estado_pppoe, "servicios", None) or []) if estado_pppoe else []
    catalog = catalog_from_servicio(
        servicio,
        es_ftth=es_ftth,
        es_radio=es_radio,
        es_adsl=es_adsl,
        servicios=servicios or None,
        needs_selection=needs_selection,
    )
    if needs_selection:
        return ConnectivityBundle(
            catalog=catalog,
            access=AccessEvidence(),
            session=SessionEvidence(),
            incident=incident or IncidentEvidence(),
        )
    if es_radio:
        access = access_from_cpe(cpe)
    elif es_ftth:
        access = access_from_onu(onu)
    else:
        access = AccessEvidence(kind="none")
    return ConnectivityBundle(
        catalog=catalog,
        access=access,
        session=session_from_pppoe(estado_pppoe),
        incident=incident or IncidentEvidence(),
    )


def evaluar_desde_sondas_eko(
    *,
    estado_pppoe: Any | None,
    onu: Any | None = None,
    cpe: Any | None = None,
    es_ftth: bool = False,
    es_radio: bool = False,
    es_adsl: bool = False,
    needs_selection: bool = False,
    incident: IncidentEvidence | None = None,
    freshness: Freshness | None = None,
    checked_at: datetime | None = None,
) -> TechnicalSelfServiceResult:
    """Bundle → decidir() → TSS. Sin I/O."""
    bundle = bundle_from_probes(
        estado_pppoe=estado_pppoe,
        onu=onu,
        cpe=cpe,
        es_ftth=es_ftth,
        es_radio=es_radio,
        es_adsl=es_adsl,
        needs_selection=needs_selection,
        incident=incident,
    )
    decision = decidir(bundle)
    now = checked_at or datetime.now(UTC)
    fresh: Freshness = freshness or ("none" if needs_selection else "live")
    return build_technical_self_service_result(
        decision,
        bundle,
        freshness=fresh,
        checked_at=now,
    )


def aplicar_resultado_a_ctx(ctx: dict, result: TechnicalSelfServiceResult) -> None:
    """Estampa diagnóstico común. Sin login, NAS, serial ni claves Wi-Fi."""
    ctx["tss_status"] = result.diagnosis.status
    ctx["tss_reason_code"] = result.diagnosis.reason_code or ""
    ctx["tss_message_key"] = result.diagnosis.message_key
    ctx["tss_service_id"] = result.subject.service_id or ""
    ctx["tss_access_technology"] = result.subject.access_technology
    ctx["tss_freshness"] = result.freshness.freshness
    ctx["tss_checked_at"] = result.freshness.checked_at.isoformat()
    ctx["tss_incident_id"] = result.incident.id if result.incident else ""
    ctx["tss_eko_branch"] = conversational_branch_for(
        result.diagnosis.reason_code,
        status=result.diagnosis.status,
        tech=result.subject.access_technology,
    )


def stamp_incident_activo_en_ctx(ctx: dict, outage: Any) -> TechnicalSelfServiceResult:
    """Incidente ya resuelto por canal_outage → TSS (sin reconsultar NetworkOutage)."""
    result = evaluar_desde_sondas_eko(
        estado_pppoe=None,
        incident=incident_from_outage(outage),
        freshness="live",
    )
    aplicar_resultado_a_ctx(ctx, result)
    return result


def linea_acceso_ok_desde_tss(ctx: dict | None) -> bool | None:
    """True/False si hay TSS; None si el caller debe usar el fallback conversacional."""
    c = ctx or {}
    status = str(c.get("tss_status") or "")
    reason = str(c.get("tss_reason_code") or "")
    if not status and not reason:
        return None
    if status == "operational":
        return True
    if reason in (
        "access_link_down",
        "link_quality_poor",
        "incident_active",
        "no_session",
        "sources_unavailable",
        "insufficient_data",
        "service_selection_required",
    ):
        return False
    return None


__all__ = [
    "TSS_CTX_KEYS",
    "access_from_cpe",
    "access_from_onu",
    "access_technology_from_flags",
    "aplicar_resultado_a_ctx",
    "bundle_from_probes",
    "catalog_from_servicio",
    "conversational_branch_for",
    "evaluar_desde_sondas_eko",
    "incident_from_outage",
    "linea_acceso_ok_desde_tss",
    "limpiar_tss_de_ctx",
    "service_ref_from_servicio",
    "session_from_pppoe",
    "stamp_incident_activo_en_ctx",
]
