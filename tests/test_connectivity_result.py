"""Proyección ConnectivityDecision → TechnicalSelfServiceResult (sin I/O)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.services.connectivity_copy import CHAT_HINT_DEFAULT, mensaje_para
from app.services.connectivity_decision import decidir
from app.services.connectivity_evidence import (
    AccessEvidence,
    CatalogEvidence,
    ConnectivityBundle,
    ConnectivityDecision,
    IncidentEvidence,
    ServiceRef,
    SessionEvidence,
)
from app.services.connectivity_result import (
    build_technical_self_service_result,
    recommend_for_reason,
)

CHECKED = datetime(2026, 9, 17, 15, 0, tzinfo=UTC)


def _svc(**kwargs) -> ServiceRef:
    base = ServiceRef(
        id="svc-1",
        label="Internet Fibra",
        type_code="INTFO",
        login="secret-login",
        base_account_number="99999",
        product="Fibra 300",
    )
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


def _result(
    decision: ConnectivityDecision,
    bundle: ConnectivityBundle,
    *,
    freshness: str = "live",
):
    return build_technical_self_service_result(
        decision,
        bundle,
        freshness=freshness,  # type: ignore[arg-type]
        checked_at=CHECKED,
    )


def _sensitive_blob(result) -> str:
    return str(result.to_dict())


# --- Diagnosis: proyección 1:1 de decidir() ---


def test_diagnosis_operational():
    bundle = _bundle(
        access=AccessEvidence(
            kind="ftth",
            available=True,
            found=True,
            link_up=True,
            quality="good",
        ),
        session=SessionEvidence(available=True, session_present=True),
    )
    d = decidir(bundle)
    r = _result(d, bundle)
    assert r.diagnosis.status == "operational"
    assert r.diagnosis.reason_code is None
    assert r.diagnosis.message_key == "operational"
    assert r.diagnosis.status == d.status
    assert r.diagnosis.reason_code == d.reason_code
    assert r.diagnosis.message_key == d.message_key


def test_diagnosis_no_session():
    bundle = _bundle(
        access=AccessEvidence(
            kind="ftth",
            available=True,
            found=True,
            link_up=True,
            quality="good",
        ),
        session=SessionEvidence(available=True, session_present=False),
    )
    d = decidir(bundle)
    r = _result(d, bundle)
    assert d.reason_code == "no_session"
    assert r.diagnosis.status == "impaired"
    assert r.diagnosis.reason_code == "no_session"
    assert r.diagnosis.message_key == "impaired_no_session"


def test_diagnosis_access_link_down():
    bundle = _bundle(
        access=AccessEvidence(
            kind="ftth",
            available=True,
            found=True,
            link_up=False,
            quality="unknown",
        ),
        session=SessionEvidence(available=True, session_present=False),
    )
    d = decidir(bundle)
    r = _result(d, bundle)
    assert r.diagnosis.status == "impaired"
    assert r.diagnosis.reason_code == "access_link_down"
    assert r.diagnosis.message_key == "impaired_access_down"


def test_diagnosis_link_quality_poor():
    bundle = _bundle(
        access=AccessEvidence(
            kind="ftth",
            available=True,
            found=True,
            link_up=True,
            quality="poor",
        ),
        session=SessionEvidence(available=True, session_present=True),
    )
    d = decidir(bundle)
    r = _result(d, bundle)
    assert r.diagnosis.reason_code == "link_quality_poor"
    assert r.diagnosis.status == "impaired"
    assert r.diagnosis.message_key == "impaired_quality"


def test_diagnosis_outage_incident_active():
    bundle = _bundle(
        access=AccessEvidence(
            kind="ftth",
            available=True,
            found=True,
            link_up=True,
            quality="good",
        ),
        session=SessionEvidence(available=True, session_present=True),
        incident=IncidentEvidence(
            matched=True,
            outage_id="outage-abc",
            started_at=CHECKED,
            alcance="total",
            mensaje="Corte en tu zona.",
            eta_minutos=45,
            eta_validada=True,
            estado="activo",
        ),
    )
    d = decidir(bundle)
    r = _result(d, bundle)
    assert r.diagnosis.status == "outage"
    assert r.diagnosis.reason_code == "incident_active"
    assert r.diagnosis.message_key == "outage"
    assert r.incident is not None
    assert r.incident.id == "outage-abc"


def test_diagnosis_sources_unavailable():
    bundle = _bundle(
        access=AccessEvidence(kind="ftth", available=False, error="timeout"),
        session=SessionEvidence(available=False, error="timeout"),
    )
    d = decidir(bundle)
    r = _result(d, bundle)
    assert r.diagnosis.status == "unknown"
    assert r.diagnosis.reason_code == "sources_unavailable"
    assert r.diagnosis.message_key == "unknown_sources"


def test_diagnosis_insufficient_data():
    # PHY OK pero sesión no consultada: decidir() → insufficient_data (no inventar).
    bundle = _bundle(
        access=AccessEvidence(
            kind="ftth",
            available=True,
            found=True,
            link_up=True,
            quality="good",
        ),
        session=SessionEvidence(available=False, error="none"),
    )
    d = decidir(bundle)
    r = _result(d, bundle)
    assert d.reason_code == "insufficient_data"
    assert r.diagnosis.status == "unknown"
    assert r.diagnosis.reason_code == "insufficient_data"
    assert r.diagnosis.message_key == "unknown_stale"


def test_diagnosis_service_selection_required():
    bundle = _bundle(needs_selection=True)
    d = decidir(bundle)
    r = _result(d, bundle, freshness="none")
    assert r.diagnosis.reason_code == "service_selection_required"
    assert r.diagnosis.message_key == "service_selection"
    assert r.subject.service_id is None
    assert r.freshness.freshness == "none"


# --- Recommendation ---


def test_recommend_all_reason_codes():
    assert recommend_for_reason("incident_active").recommended_action == "wait_outage"
    assert recommend_for_reason("access_link_down").recommended_action == (
        "talk_to_eko_or_ticket"
    )
    assert recommend_for_reason("link_quality_poor").recommended_action == (
        "talk_to_eko_or_ticket"
    )
    assert recommend_for_reason("no_session").recommended_action == "talk_to_eko"
    assert recommend_for_reason(None).recommended_action == "none"
    assert recommend_for_reason("service_selection_required").recommended_action == (
        "select_service"
    )
    assert recommend_for_reason("sources_unavailable").recommended_action == (
        "retry_or_eko"
    )
    assert recommend_for_reason("insufficient_data").recommended_action == (
        "retry_or_eko"
    )


def test_available_actions_known_and_no_wifi_write():
    for code in (
        "incident_active",
        "access_link_down",
        "link_quality_poor",
        "no_session",
        None,
        "service_selection_required",
        "sources_unavailable",
        "insufficient_data",
    ):
        rec = recommend_for_reason(code)
        assert "change_wifi" not in rec.available_actions
        assert "reboot_cpe" not in rec.available_actions
        assert rec.recommended_action
        assert rec.available_actions


def test_recommendation_on_result_matches_reason():
    bundle = _bundle(
        access=AccessEvidence(
            kind="ftth", available=True, found=True, link_up=False, quality="unknown"
        )
    )
    d = decidir(bundle)
    r = _result(d, bundle)
    assert r.recommendation.recommended_action == "talk_to_eko_or_ticket"
    assert "talk_to_eko" in r.recommendation.available_actions
    assert "create_ticket" in r.recommendation.available_actions


# --- Security ---


def test_customer_safe_result_omits_infra():
    bundle = _bundle(
        selected=_svc(
            login="userRadiusSecret",
            base_account_number="BN-SERIAL-ISH",
        ),
        access=AccessEvidence(
            kind="ftth",
            available=True,
            found=True,
            link_up=True,
            quality="good",
        ),
        session=SessionEvidence(
            available=True,
            session_present=True,
            nas_internal="NAS-PLANTA-01",
            uptime_raw="3600",
        ),
    )
    d = decidir(bundle)
    r = _result(d, bundle)
    blob = _sensitive_blob(r)
    forbidden = (
        "userRadiusSecret",
        "BN-SERIAL-ISH",
        "NAS-PLANTA-01",
        "secret-login",
        "serial",
        "device_id",
        "public_ip",
        "olt",
        "pon",
        "HWTC",
        "password",
        "181.41",
        "-22.4",
    )
    for token in forbidden:
        assert token not in blob, f"filtró {token}"
    dumped = r.to_dict()
    nested_keys: set[str] = set()

    def _collect(obj) -> None:
        if isinstance(obj, dict):
            nested_keys.update(obj.keys())
            for v in obj.values():
                _collect(v)
        elif isinstance(obj, list):
            for v in obj:
                _collect(v)

    _collect(dumped)
    for k in (
        "login",
        "nas",
        "nas_internal",
        "serial",
        "device_id",
        "public_ip",
        "rx",
        "tx",
        "mac",
        "olt",
        "pon",
        "password",
    ):
        assert k not in nested_keys


def test_evidence_safe_has_only_allowed_fields():
    bundle = _bundle(
        access=AccessEvidence(
            kind="ftth",
            available=True,
            found=True,
            link_up=True,
            quality="acceptable",
        ),
        session=SessionEvidence(available=True, session_present=True),
    )
    r = _result(decidir(bundle), bundle)
    ev = r.to_dict()["evidence_safe"]
    assert set(ev.keys()) == {
        "session_present",
        "access_link_up",
        "access_quality",
    }
    assert ev["session_present"] is True
    assert ev["access_link_up"] is True
    assert ev["access_quality"] == "acceptable"


# --- Incident ---


def test_incident_none_when_not_matched():
    bundle = _bundle(
        access=AccessEvidence(
            kind="ftth", available=True, found=True, link_up=True, quality="good"
        ),
        session=SessionEvidence(available=True, session_present=True),
    )
    r = _result(decidir(bundle), bundle)
    assert r.incident is None
    assert r.to_dict()["incident"] is None


def test_incident_preserves_outage_id_and_eta_semantics():
    started = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
    bundle = _bundle(
        incident=IncidentEvidence(
            matched=True,
            outage_id="net-out-42",
            started_at=started,
            alcance="parcial",
            mensaje="Trabajo en la zona.",
            eta_minutos=30,
            eta_validada=True,
            estado="activo",
        )
    )
    d = decidir(bundle)
    r = _result(d, bundle)
    assert r.incident is not None
    assert r.incident.id == "net-out-42"
    assert r.incident.started_at == started
    assert r.incident.scope == "partial"
    assert r.incident.eta_minutes == 30
    assert r.incident.eta_confirmed is True
    assert r.incident.message == "Trabajo en la zona."


def test_incident_eta_omitted_when_not_validated():
    bundle = _bundle(
        incident=IncidentEvidence(
            matched=True,
            outage_id="o2",
            alcance="total",
            mensaje="Incidencia.",
            eta_minutos=90,
            eta_validada=False,
            estado="activo",
        )
    )
    r = _result(decidir(bundle), bundle)
    assert r.incident is not None
    assert r.incident.eta_minutes is None
    assert r.incident.eta_confirmed is False
    assert r.incident.scope == "area"


def test_historical_matched_without_active_diagnosis_is_dropped():
    """Incidente histórico no debe aparecer si decidir() no lo usó."""
    decision = ConnectivityDecision(
        status="operational",
        reason_code=None,
        message_key="operational",
    )
    bundle = _bundle(
        incident=IncidentEvidence(
            matched=True,
            outage_id="old-outage",
            estado="resuelto",
            mensaje="Ya pasó.",
        )
    )
    r = _result(decision, bundle)
    assert r.incident is None


# --- Copy ---


def test_copy_uses_message_key_source_of_truth():
    bundle = _bundle(
        access=AccessEvidence(
            kind="ftth", available=True, found=True, link_up=True, quality="good"
        ),
        session=SessionEvidence(available=True, session_present=True),
    )
    d = decidir(bundle)
    r = _result(d, bundle)
    assert r.copy.customer_message == mensaje_para(d.message_key)
    assert r.copy.chat_hint == CHAT_HINT_DEFAULT
    assert r.copy.customer_message == mensaje_para("operational")


def test_copy_outage_uses_incident_message():
    bundle = _bundle(
        incident=IncidentEvidence(
            matched=True,
            outage_id="o9",
            mensaje="Corte programado hasta las 18.",
            eta_minutos=60,
            eta_validada=True,
        )
    )
    d = decidir(bundle)
    r = _result(d, bundle)
    assert r.copy.customer_message == "Corte programado hasta las 18."
    assert r.diagnosis.message_key == "outage"


# --- Subject / freshness ---


def test_subject_and_freshness_from_metadata():
    bundle = _bundle()
    d = decidir(bundle)
    r = _result(d, bundle, freshness="cached")
    assert r.subject.service_id == "svc-1"
    assert r.subject.access_technology == "ftth"
    assert r.freshness.freshness == "cached"
    assert r.freshness.checked_at == CHECKED


# --- Determinism ---


def test_same_input_same_result():
    bundle = _bundle(
        access=AccessEvidence(
            kind="radio",
            available=True,
            found=True,
            link_up=True,
            quality="good",
        ),
        session=SessionEvidence(available=True, session_present=True),
    )
    d = decidir(bundle)
    a = _result(d, bundle)
    b = _result(d, bundle)
    assert a.to_dict() == b.to_dict()
    assert a == b
