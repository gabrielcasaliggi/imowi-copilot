"""Proyección de ConnectivityDecision a un resultado de Technical Self-Service.

Capa posterior al diagnóstico. Sin I/O, sin OSS, sin acciones.
No modifica decidir(); no es un segundo motor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.services.connectivity_copy import CHAT_HINT_DEFAULT, mensaje_para
from app.services.connectivity_evidence import (
    AccessEvidence,
    AccessQuality,
    AccessTechnology,
    ConnectivityBundle,
    ConnectivityDecision,
    ConnectivityStatus,
    Freshness,
    IncidentEvidence,
    MessageKey,
    ReasonCode,
    SessionEvidence,
)

RecommendedAction = Literal[
    "wait_outage",
    "talk_to_eko_or_ticket",
    "talk_to_eko",
    "none",
    "select_service",
    "retry_or_eko",
]
AvailableAction = Literal[
    "wait_outage",
    "talk_to_eko",
    "create_ticket",
    "select_service",
    "retry_connectivity",
]
IncidentScope = Literal["partial", "area"]

# Vocabulario de acciones: no existe uno previo en el repo.
# Conjunto mínimo alineado a CTAs productivos (Eko, reclamo, selección, retry).
# change_wifi no se deriva del diagnóstico (intención explícita del usuario).


@dataclass(frozen=True)
class TssDiagnosis:
    status: ConnectivityStatus
    reason_code: ReasonCode | None
    message_key: MessageKey


@dataclass(frozen=True)
class TssSubject:
    service_id: str | None
    access_technology: AccessTechnology


@dataclass(frozen=True)
class TssFreshness:
    checked_at: datetime
    freshness: Freshness


@dataclass(frozen=True)
class TssIncident:
    """Incidente activo del diagnóstico. Nunca histórico. id = NetworkOutage.id."""

    id: str
    started_at: datetime | None
    message: str
    scope: IncidentScope
    eta_minutes: int | None
    eta_confirmed: bool


@dataclass(frozen=True)
class TssEvidenceSafe:
    session_present: bool | None
    access_link_up: bool | None
    access_quality: AccessQuality


@dataclass(frozen=True)
class TssRecommendation:
    recommended_action: RecommendedAction
    available_actions: tuple[AvailableAction, ...]


@dataclass(frozen=True)
class TssCopy:
    customer_message: str
    chat_hint: str


@dataclass(frozen=True)
class TechnicalSelfServiceResult:
    diagnosis: TssDiagnosis
    subject: TssSubject
    freshness: TssFreshness
    incident: TssIncident | None
    evidence_safe: TssEvidenceSafe
    recommendation: TssRecommendation
    copy: TssCopy

    def to_dict(self) -> dict:
        """Serialización customer-safe. Sin login, NAS, serial ni métricas crudas."""
        inc = None
        if self.incident is not None:
            inc = {
                "id": self.incident.id,
                "started_at": (
                    self.incident.started_at.isoformat()
                    if self.incident.started_at
                    else ""
                ),
                "message": self.incident.message,
                "scope": self.incident.scope,
                "eta_minutes": self.incident.eta_minutes,
                "eta_confirmed": self.incident.eta_confirmed,
            }
        return {
            "diagnosis": {
                "status": self.diagnosis.status,
                "reason_code": self.diagnosis.reason_code,
                "message_key": self.diagnosis.message_key,
            },
            "subject": {
                "service_id": self.subject.service_id,
                "access_technology": self.subject.access_technology,
            },
            "freshness": {
                "checked_at": self.freshness.checked_at.isoformat(),
                "freshness": self.freshness.freshness,
            },
            "incident": inc,
            "evidence_safe": {
                "session_present": self.evidence_safe.session_present,
                "access_link_up": self.evidence_safe.access_link_up,
                "access_quality": self.evidence_safe.access_quality,
            },
            "recommendation": {
                "recommended_action": self.recommendation.recommended_action,
                "available_actions": list(self.recommendation.available_actions),
            },
            "copy": {
                "customer_message": self.copy.customer_message,
                "chat_hint": self.copy.chat_hint,
            },
        }


def recommend_for_reason(reason_code: ReasonCode | None) -> TssRecommendation:
    """Mapa puro reason_code → recomendación. Sin I/O."""
    if reason_code == "incident_active":
        return TssRecommendation(
            "wait_outage",
            ("wait_outage", "talk_to_eko", "retry_connectivity"),
        )
    if reason_code in ("access_link_down", "link_quality_poor"):
        return TssRecommendation(
            "talk_to_eko_or_ticket",
            ("talk_to_eko", "create_ticket", "retry_connectivity"),
        )
    if reason_code == "no_session":
        return TssRecommendation(
            "talk_to_eko",
            ("talk_to_eko", "create_ticket", "retry_connectivity"),
        )
    if reason_code == "service_selection_required":
        return TssRecommendation("select_service", ("select_service",))
    if reason_code in ("sources_unavailable", "insufficient_data"):
        return TssRecommendation(
            "retry_or_eko",
            ("retry_connectivity", "talk_to_eko"),
        )
    # operational (reason_code None) y cualquier código no mapeado
    return TssRecommendation(
        "none",
        ("talk_to_eko", "retry_connectivity"),
    )


def _project_incident(
    decision: ConnectivityDecision, incident: IncidentEvidence
) -> TssIncident | None:
    """Solo el incidente que participa del diagnóstico actual (activo)."""
    if decision.reason_code != "incident_active" and decision.status != "outage":
        return None
    if not incident.matched:
        return None
    oid = str(incident.outage_id or "").strip()
    if not oid:
        return None
    scope: IncidentScope = "partial" if incident.alcance == "parcial" else "area"
    eta_minutes = incident.eta_minutos if incident.eta_validada else None
    return TssIncident(
        id=oid,
        started_at=incident.started_at,
        message=(incident.mensaje or "").strip(),
        scope=scope,
        eta_minutes=eta_minutes,
        eta_confirmed=bool(incident.eta_validada and eta_minutes),
    )


def _project_evidence_safe(
    access: AccessEvidence, session: SessionEvidence
) -> TssEvidenceSafe:
    quality: AccessQuality = access.quality if access.quality else "unknown"
    session_present = session.session_present if session.available else None
    link_up = access.link_up if access.available else None
    return TssEvidenceSafe(
        session_present=session_present,
        access_link_up=link_up,
        access_quality=quality,
    )


def build_technical_self_service_result(
    decision: ConnectivityDecision,
    bundle: ConnectivityBundle,
    *,
    freshness: Freshness,
    checked_at: datetime,
) -> TechnicalSelfServiceResult:
    """Proyecta una decisión ya tomada. No consulta OSS ni llama decidir()."""
    selected = bundle.catalog.selected
    service_id = str(selected.id).strip() if selected and selected.id else None
    incident = _project_incident(decision, bundle.incident)
    incident_msg = incident.message if incident else ""
    return TechnicalSelfServiceResult(
        diagnosis=TssDiagnosis(
            status=decision.status,
            reason_code=decision.reason_code,
            message_key=decision.message_key,
        ),
        subject=TssSubject(
            service_id=service_id,
            access_technology=bundle.catalog.access_technology,
        ),
        freshness=TssFreshness(checked_at=checked_at, freshness=freshness),
        incident=incident,
        evidence_safe=_project_evidence_safe(bundle.access, bundle.session),
        recommendation=recommend_for_reason(decision.reason_code),
        copy=TssCopy(
            customer_message=mensaje_para(
                decision.message_key,
                incident_message=incident_msg,
            ),
            chat_hint=CHAT_HINT_DEFAULT,
        ),
    )


__all__ = [
    "AvailableAction",
    "RecommendedAction",
    "TechnicalSelfServiceResult",
    "TssCopy",
    "TssDiagnosis",
    "TssEvidenceSafe",
    "TssFreshness",
    "TssIncident",
    "TssRecommendation",
    "TssSubject",
    "build_technical_self_service_result",
    "recommend_for_reason",
]
