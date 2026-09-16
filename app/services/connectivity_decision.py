"""Motor de decisión puro: evidencia → status + reason_code + message_key.

Sin I/O. Precedencia alineada a Milestone C / D0.
"""

from __future__ import annotations

from app.services.connectivity_evidence import (
    AccessEvidence,
    ConnectivityBundle,
    ConnectivityDecision,
    SessionEvidence,
)


def _phy_fresh(access: AccessEvidence) -> bool:
    return bool(access.available) and access.error == "none"


def _session_fresh(session: SessionEvidence) -> bool:
    return bool(session.available) and session.error == "none"


def _phy_ok(access: AccessEvidence) -> bool:
    return (
        _phy_fresh(access)
        and access.found is True
        and access.link_up is True
        and access.quality in ("good", "acceptable", "unknown")
    )


def _sources_down(access: AccessEvidence, session: SessionEvidence) -> bool:
    phy_bad = (not access.available) or access.error in (
        "timeout",
        "unavailable",
        "other",
    )
    sess_bad = (not session.available) or session.error in (
        "timeout",
        "unavailable",
        "other",
    )
    return phy_bad and sess_bad


def decidir(bundle: ConnectivityBundle) -> ConnectivityDecision:
    cat = bundle.catalog
    access = bundle.access
    session = bundle.session
    incident = bundle.incident
    tech = cat.access_technology

    # 1. Selección requerida
    if cat.needs_selection:
        return ConnectivityDecision(
            status="unknown",
            reason_code="service_selection_required",
            message_key="service_selection",
        )

    # 2. Outage asociable
    if incident.matched:
        return ConnectivityDecision(
            status="outage",
            reason_code="incident_active",
            message_key="outage",
        )

    # 3. Radio PHY down
    if (
        tech == "radio"
        and _phy_fresh(access)
        and access.kind == "radio"
        and access.link_up is False
    ):
        return ConnectivityDecision(
            status="impaired",
            reason_code="access_link_down",
            message_key="impaired_access_down",
        )

    # 4. FTTH PHY down
    if (
        tech == "ftth"
        and _phy_fresh(access)
        and access.kind == "ftth"
        and access.link_up is False
    ):
        return ConnectivityDecision(
            status="impaired",
            reason_code="access_link_down",
            message_key="impaired_access_down",
        )

    # 5. FTTH PHY OK + sin sesión
    if (
        tech == "ftth"
        and _phy_ok(access)
        and _session_fresh(session)
        and session.session_present is False
    ):
        return ConnectivityDecision(
            status="impaired",
            reason_code="no_session",
            message_key="impaired_no_session",
        )

    # 6. PHY quality poor
    if _phy_fresh(access) and access.quality == "poor" and access.link_up is not False:
        # link_up False ya se resolvió arriba; poor con link up o unknown
        return ConnectivityDecision(
            status="impaired",
            reason_code="link_quality_poor",
            message_key="impaired_quality",
        )

    # 7. Operational
    if tech in ("ftth", "radio") and _phy_ok(access):
        if _session_fresh(session) and session.session_present is True:
            return ConnectivityDecision(
                status="operational",
                reason_code=None,
                message_key="operational",
            )
        # Sesión no requerida / no consultada con éxito: solo phy OK no alcanza en FTTH
        # si session fue consultada y ausente → ya cubierto en (5).
        # Si session no available pero phy OK:
        if not session.available or session.error != "none":
            # Conservador: no afirmar operational sin sesión cuando tech usa PPPoE
            pass
        elif session.session_present is True:
            return ConnectivityDecision(
                status="operational",
                reason_code=None,
                message_key="operational",
            )

    if tech == "other":
        # ADSL / otros: capa decisiva = sesión
        if _session_fresh(session) and session.session_present is True:
            return ConnectivityDecision(
                status="operational",
                reason_code=None,
                message_key="operational",
            )
        if _session_fresh(session) and session.session_present is False:
            return ConnectivityDecision(
                status="impaired",
                reason_code="no_session",
                message_key="impaired_no_session",
            )

    # Tech no usa phy y no exige sesión (raro): phy none + session OK
    if access.kind == "none" and _session_fresh(session) and session.session_present is True:
        return ConnectivityDecision(
            status="operational",
            reason_code=None,
            message_key="operational",
        )

    # 8. FTTH PHY unavailable + no session → unknown (nunca impaired)
    if tech == "ftth" and (
        (not access.available) or access.error in ("timeout", "unavailable", "other")
    ):
        if (not session.available) or session.session_present is False:
            reason = (
                "sources_unavailable"
                if (not access.available or access.error != "none")
                and (not session.available or session.error != "none")
                else "insufficient_data"
            )
            return ConnectivityDecision(
                status="unknown",
                reason_code=reason,  # type: ignore[arg-type]
                message_key=(
                    "unknown_sources"
                    if reason == "sources_unavailable"
                    else "unknown_stale"
                ),
            )

    # 9. Fuentes insuficientes
    if _sources_down(access, session):
        return ConnectivityDecision(
            status="unknown",
            reason_code="sources_unavailable",
            message_key="unknown_sources",
        )

    if tech == "unknown":
        return ConnectivityDecision(
            status="unknown",
            reason_code="insufficient_data",
            message_key="unknown_stale",
        )

    # Radio/FTTH: phy OK pero sin evidencia de sesión usable
    if tech in ("ftth", "radio") and _phy_ok(access):
        return ConnectivityDecision(
            status="unknown",
            reason_code="insufficient_data",
            message_key="unknown_stale",
        )

    # 10. Default
    return ConnectivityDecision(
        status="unknown",
        reason_code="insufficient_data",
        message_key="unknown_stale",
    )
