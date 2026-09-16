"""Tests del motor de decisión de conectividad (sin I/O)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.services.connectivity_decision import decidir
from app.services.connectivity_evidence import (
    AccessEvidence,
    CatalogEvidence,
    ConnectivityBundle,
    IncidentEvidence,
    ServiceRef,
    SessionEvidence,
)


def _svc(**kwargs) -> ServiceRef:
    base = ServiceRef(id="svc-1", label="Internet Fibra", type_code="INTFO", login="u1")
    for k, v in kwargs.items():
        setattr(base, k, v)
    return base


def _bundle(
    *,
    tech: str = "ftth",
    needs_selection: bool = False,
    access: AccessEvidence | None = None,
    session: SessionEvidence | None = None,
    incident: IncidentEvidence | None = None,
    selected: ServiceRef | None = None,
) -> ConnectivityBundle:
    sel = selected or (_svc() if not needs_selection else None)
    return ConnectivityBundle(
        catalog=CatalogEvidence(
            services=[sel] if sel else [_svc(), _svc(id="svc-2")],
            selected=sel,
            needs_selection=needs_selection,
            access_technology=tech,  # type: ignore[arg-type]
        ),
        access=access or AccessEvidence(),
        session=session or SessionEvidence(),
        incident=incident or IncidentEvidence(),
    )


def test_service_selection_required():
    d = decidir(_bundle(needs_selection=True))
    assert d.status == "unknown"
    assert d.reason_code == "service_selection_required"
    assert d.message_key == "service_selection"


def test_outage_beats_session_and_phy_ok():
    d = decidir(
        _bundle(
            access=AccessEvidence(
                kind="ftth",
                available=True,
                found=True,
                link_up=True,
                quality="good",
                observed_at=datetime.now(UTC),
            ),
            session=SessionEvidence(available=True, session_present=True),
            incident=IncidentEvidence(
                matched=True,
                outage_id="o1",
                mensaje="Incidencia en tu zona.",
            ),
        )
    )
    assert d.status == "outage"
    assert d.reason_code == "incident_active"


def test_ftth_offline_impaired():
    d = decidir(
        _bundle(
            access=AccessEvidence(
                kind="ftth",
                available=True,
                found=True,
                link_up=False,
                quality="unknown",
            ),
            session=SessionEvidence(available=True, session_present=False),
        )
    )
    assert d.status == "impaired"
    assert d.reason_code == "access_link_down"


def test_radio_offline_session_ok_impaired():
    d = decidir(
        _bundle(
            tech="radio",
            access=AccessEvidence(
                kind="radio",
                available=True,
                found=True,
                link_up=False,
                quality="unknown",
            ),
            session=SessionEvidence(available=True, session_present=True),
        )
    )
    assert d.status == "impaired"
    assert d.reason_code == "access_link_down"


def test_ftth_phy_ok_no_session_impaired():
    d = decidir(
        _bundle(
            access=AccessEvidence(
                kind="ftth",
                available=True,
                found=True,
                link_up=True,
                quality="good",
            ),
            session=SessionEvidence(available=True, session_present=False),
        )
    )
    assert d.status == "impaired"
    assert d.reason_code == "no_session"


def test_ftth_phy_unavailable_no_session_unknown():
    d = decidir(
        _bundle(
            access=AccessEvidence(
                kind="ftth",
                available=False,
                error="unavailable",
            ),
            session=SessionEvidence(available=True, session_present=False),
        )
    )
    assert d.status == "unknown"
    assert d.reason_code in ("insufficient_data", "sources_unavailable")


def test_all_sources_down_unknown():
    d = decidir(
        _bundle(
            access=AccessEvidence(available=False, error="timeout"),
            session=SessionEvidence(available=False, error="timeout"),
        )
    )
    assert d.status == "unknown"
    assert d.reason_code == "sources_unavailable"


def test_quality_poor_impaired():
    d = decidir(
        _bundle(
            access=AccessEvidence(
                kind="ftth",
                available=True,
                found=True,
                link_up=True,
                quality="poor",
            ),
            session=SessionEvidence(available=True, session_present=True),
        )
    )
    assert d.status == "impaired"
    assert d.reason_code == "link_quality_poor"


def test_operational():
    d = decidir(
        _bundle(
            access=AccessEvidence(
                kind="ftth",
                available=True,
                found=True,
                link_up=True,
                quality="good",
            ),
            session=SessionEvidence(available=True, session_present=True),
        )
    )
    assert d.status == "operational"
    assert d.reason_code is None
    assert d.message_key == "operational"


def test_technology_unknown():
    d = decidir(
        _bundle(
            tech="unknown",
            access=AccessEvidence(available=False),
            session=SessionEvidence(available=False),
        )
    )
    assert d.status == "unknown"


def test_contradictory_radio_cpe_down_session_up():
    """Radio: CPE manda sobre sesión."""
    d = decidir(
        _bundle(
            tech="radio",
            access=AccessEvidence(
                kind="radio",
                available=True,
                found=True,
                link_up=False,
            ),
            session=SessionEvidence(available=True, session_present=True),
        )
    )
    assert d.status == "impaired"
    assert d.reason_code == "access_link_down"


def test_other_tech_session_only_operational():
    d = decidir(
        _bundle(
            tech="other",
            access=AccessEvidence(kind="none"),
            session=SessionEvidence(available=True, session_present=True),
        )
    )
    assert d.status == "operational"
