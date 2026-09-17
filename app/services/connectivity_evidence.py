"""Modelos internos de evidencia para self-service de conectividad (portal).

Nunca serializar estos tipos al DTO público: contienen campos backend-only
(login, NAS, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

AccessKind = Literal["ftth", "radio", "none"]
AccessQuality = Literal["good", "acceptable", "poor", "unknown"]
AccessError = Literal["none", "timeout", "unavailable", "not_found", "other"]
SessionError = Literal["none", "timeout", "unavailable", "other"]
AccessTechnology = Literal["ftth", "radio", "other", "unknown"]
ConnectivityStatus = Literal["operational", "impaired", "outage", "unknown"]
Freshness = Literal["live", "cached", "stale", "none"]
ReasonCode = Literal[
    "incident_active",
    "access_link_down",
    "no_session",
    "link_quality_poor",
    "insufficient_data",
    "sources_unavailable",
    "service_selection_required",
]
MessageKey = Literal[
    "operational",
    "impaired_access_down",
    "impaired_quality",
    "impaired_no_session",
    "outage",
    "unknown_stale",
    "unknown_sources",
    "service_selection",
]


def map_calidad_to_quality(raw: str) -> AccessQuality:
    """BCM/UISP 'buena|aceptable|mala' → quality canónica del motor."""
    v = (raw or "").strip().lower()
    if v == "buena":
        return "good"
    if v == "aceptable":
        return "acceptable"
    if v == "mala":
        return "poor"
    return "unknown"


def link_up_from_phy(
    *,
    online: bool | None,
    quality: str,
    has_metric: bool,
) -> bool | None:
    """Misma regla que Portal: métrica usable implica enlace físico."""
    if online is True:
        return True
    if has_metric and quality in ("good", "acceptable", "poor"):
        return True
    if online is False:
        return False
    return None


def classify_provider_error(err: str) -> AccessError:
    """Timeout / no configurado / vacío → error canónico del motor."""
    e = (err or "").strip().lower()
    if not e:
        return "none"
    if "timeout" in e or "timed out" in e:
        return "timeout"
    if (
        "no configurad" in e
        or "not configured" in e
        or "disabled" in e
        or "no configurada" in e
    ):
        return "unavailable"
    if "vacío" in e or "vacio" in e or "empty" in e:
        return "unavailable"
    return "other"


@dataclass
class ServiceRef:
    """Referencia interna a un servicio de conectividad BillTrack."""

    id: str
    label: str
    type_code: str = ""
    type_label: str = ""
    login: str = ""  # backend-only
    base_account_number: str = ""  # backend-only
    product: str = ""


@dataclass
class CatalogEvidence:
    services: list[ServiceRef] = field(default_factory=list)
    selected: ServiceRef | None = None
    needs_selection: bool = False
    access_technology: AccessTechnology = "unknown"


@dataclass
class AccessEvidence:
    kind: AccessKind = "none"
    available: bool = False
    found: bool | None = None
    link_up: bool | None = None
    quality: AccessQuality = "unknown"
    observed_at: datetime | None = None
    error: AccessError = "none"


@dataclass
class SessionEvidence:
    available: bool = False
    session_present: bool | None = None
    nas_internal: str = ""  # backend-only
    uptime_raw: str = ""  # backend-only
    error: SessionError = "none"
    observed_at: datetime | None = None


@dataclass
class IncidentEvidence:
    matched: bool = False
    outage_id: str = ""
    started_at: datetime | None = None
    alcance: str = ""
    mensaje: str = ""
    eta_minutos: int | None = None
    eta_validada: bool = False
    estado: str = ""


@dataclass
class ConnectivityBundle:
    """Entrada del motor de decisión (sin I/O)."""

    catalog: CatalogEvidence
    access: AccessEvidence
    session: SessionEvidence
    incident: IncidentEvidence
    # Evidencia de esta evaluación se considera "fresh" si available=True
    # (el orquestador no pasa observaciones stale al motor).


@dataclass
class ConnectivityDecision:
    status: ConnectivityStatus
    reason_code: ReasonCode | None
    message_key: MessageKey
