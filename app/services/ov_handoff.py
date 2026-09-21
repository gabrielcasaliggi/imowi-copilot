"""OV-03 — identidad canónica DNI y clasificación AUTH vs PUBLIC.

El handoff *autenticado* solo existe si JSAT publica ``POST /ov/handoff`` y
Eko lo tiene habilitado (``OV_HANDOFF_V2`` / settings ``handoff_v2``).

``GET /ov/link`` + ``tsid`` es legado de compatibilidad (Botmaker / probe).
Un ``tsid`` en URL **no** se etiqueta authenticated/ready/handoff_safe.

Eko identifica al abonado. JSAT crea la sesión OV y autoriza recursos.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

logger = logging.getLogger("operations_hub")

MODE_AUTHENTICATED = "authenticated"
MODE_PUBLIC = "public"
MODE_FAILED = "failed"

INTENT_INVOICE = "invoice"
INTENT_PAY = "pay"
INTENT_PAYMENT_SLIP = "payment_slip"
INTENT_PACK = "pack"
INTENT_PORTABILITY = "portability"
INTENT_ACCOUNT = "account"
INTENT_SERVICE = "service"
INTENT_AVISO = "aviso"

# intent Eko → destination JSAT (allowlist). El usuario no elige path.
INTENT_TO_DESTINATION: dict[str, str] = {
    INTENT_INVOICE: "my",
    INTENT_PAY: "pagar",
    INTENT_PAYMENT_SLIP: "talon-de-pago",
    INTENT_PACK: "comprar-pack",
    INTENT_PORTABILITY: "portabilidad",
    INTENT_ACCOUNT: "cuenta",
    INTENT_SERVICE: "servicio",
    INTENT_AVISO: "aviso-de-pago",
}

# Keys históricas de url_ov_para_key → intent.
KEY_TO_INTENT: dict[str, str] = {
    "my": INTENT_INVOICE,
    "pagar": INTENT_PAY,
    "talon": INTENT_PAYMENT_SLIP,
    "pack": INTENT_PACK,
    "portabilidad": INTENT_PORTABILITY,
    "aviso": INTENT_AVISO,
    "cuenta": INTENT_ACCOUNT,
    "servicio": INTENT_SERVICE,
    **{dest: intent for intent, dest in INTENT_TO_DESTINATION.items()},
}

ALLOWED_DESTINATIONS = frozenset(INTENT_TO_DESTINATION.values())

DEFAULT_AUDIENCE = "https://ov.batan.coop"
DEFAULT_TTL_SECONDS = 60

_REASON_NO_DNI = "no_dni"
_REASON_NOT_IDENTIFIED = "not_identified"
_REASON_AMBIGUOUS = "identity_ambiguous"
_REASON_INVALID = "invalid_identity"
_REASON_DEST_FORBIDDEN = "destination_forbidden"
_REASON_JSAT_0 = "jsat_0"
_REASON_JSAT_N = "jsat_n"
_REASON_JSAT_DOWN = "jsat_down"
_REASON_PUBLIC_ENTRY = "public_entry"
_REASON_HOST = "host_forbidden"

_METRICS_LOCK = threading.Lock()
_METRICS: dict[str, int] = {
    "ov_handoff_authenticated": 0,
    "ov_handoff_public": 0,
    "ov_handoff_identity_ambiguous": 0,
    "ov_handoff_failed": 0,
}


@dataclass(frozen=True)
class HandoffOutcome:
    """Resultado de un pedido de URL OV. mode nunca infiere auth por tener URL."""

    mode: str
    url: str
    destination: str
    intent: str
    reason: str
    expires_in: int | None = None

    @property
    def authenticated(self) -> bool:
        return self.mode == MODE_AUTHENTICATED


def reset_handoff_metrics() -> None:
    with _METRICS_LOCK:
        for k in _METRICS:
            _METRICS[k] = 0


def snapshot_handoff_metrics() -> dict[str, int]:
    with _METRICS_LOCK:
        return dict(_METRICS)


def record_handoff_metric(
    mode: str,
    *,
    canal: str = "",
    intent: str = "",
    reason: str = "",
) -> None:
    """Contadores in-process. Sin PII, tokens ni URLs."""
    key = "ov_handoff_failed"
    if mode == MODE_AUTHENTICATED:
        key = "ov_handoff_authenticated"
    elif reason == _REASON_AMBIGUOUS:
        key = "ov_handoff_identity_ambiguous"
    elif mode == MODE_PUBLIC:
        key = "ov_handoff_public"
    with _METRICS_LOCK:
        _METRICS[key] = int(_METRICS.get(key) or 0) + 1
    logger.info(
        "ov_handoff metric=%s canal=%s intent=%s reason=%s",
        key,
        (canal or "")[:16],
        (intent or "")[:24],
        (reason or "")[:40],
    )


def canonical_dni(abonado: Any | None) -> str:
    """DNI canónico del abonado identificado. Vacío si no hay sujeto válido."""
    if abonado is None:
        return ""
    from app.estate.security import normalizar_dni, valid_dni_ar

    raw = str(getattr(abonado, "dni", "") or "").strip()
    dni = normalizar_dni(raw)
    if not valid_dni_ar(dni):
        return ""
    return dni


def identity_reason(
    abonado: Any | None,
    *,
    phone_candidates: Any = None,
) -> str:
    """Por qué no hay (o sí hay) identidad canónica. No resuelve OV."""
    if phone_candidates and abonado is None:
        return _REASON_AMBIGUOUS
    if abonado is None:
        return _REASON_NOT_IDENTIFIED
    if not canonical_dni(abonado):
        return _REASON_NO_DNI
    return ""


def destination_for_intent(intent: str) -> str | None:
    key = (intent or "").strip().lower()
    mapped = KEY_TO_INTENT.get(key) or key
    dest = INTENT_TO_DESTINATION.get(mapped)
    if dest in ALLOWED_DESTINATIONS:
        return dest
    return None


def allowed_handoff_hosts(public_base: str = "") -> set[str]:
    hosts = {"ov.batan.coop"}
    raw = (public_base or DEFAULT_AUDIENCE).strip()
    if raw:
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        if parsed.hostname:
            hosts.add(parsed.hostname.lower())
    return hosts


def url_host_allowed(url: str, *, public_base: str = "") -> bool:
    """Allowlist https + host OV. No redirects desde input de usuario."""
    raw = (url or "").strip()
    if not raw:
        return False
    parsed = urlparse(raw)
    if parsed.scheme.lower() != "https":
        return False
    host = (parsed.hostname or "").lower()
    if not host or host not in allowed_handoff_hosts(public_base):
        return False
    return True


def public_url_for_destination(destination: str, *, public_base: str = "") -> str:
    from app.services.ov_batan import public_url as _public

    dest = (destination or "").strip() or "pagar"
    return _public(dest, public_base=public_base)


def handoff_v2_enabled(db: Session | None = None) -> bool:
    from app.services.ov_batan import resolve_ov_batan

    cfg = resolve_ov_batan(db)
    return bool(cfg.get("handoff_v2"))


def request_ov_handoff(
    *,
    dni: str,
    destination: str,
    db: Session | None = None,
    resource_id: str | None = None,
) -> dict[str, Any] | None:
    """Cliente POST /ov/handoff. No activo salvo flag. Nunca trata tsid como seguro.

    No loguea body, URL de consume, dni ni sid.
    """
    from app.services.ov_batan import _ensure_sid, _response_json, ov_configurado, resolve_ov_batan

    dni_n = (dni or "").strip()
    dest = (destination or "").strip()
    if not dni_n or dest not in ALLOWED_DESTINATIONS:
        return None
    if not ov_configurado(db) or not handoff_v2_enabled(db):
        return None

    cfg = resolve_ov_batan(db)
    api = str(cfg.get("api_url") or "").rstrip("/")
    timeout = float(cfg.get("timeout") or 20)
    audience = str(cfg.get("public_url") or DEFAULT_AUDIENCE).rstrip("/")
    payload = {
        "identity_type": "dni",
        "identity": dni_n,
        "destination": dest,
        "resource_id": resource_id,
        "audience": audience or DEFAULT_AUDIENCE,
        "ttl_seconds": DEFAULT_TTL_SECONDS,
    }
    try:
        import httpx

        sid = _ensure_sid(cfg)
        r = httpx.post(
            f"{api}/ov/handoff",
            json=payload,
            headers={
                "sid": sid,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
        data = _response_json(r) if r.content else {}
        if not r.is_success:
            logger.info(
                "OV POST /ov/handoff http=%s dest=%s",
                r.status_code,
                dest,
            )
            return {"status": "ERROR", "code": "jsat_down", "result": None}
        status = str(data.get("status") or "").upper()
        if status != "OK":
            code = str(data.get("code") or data.get("statusMessage") or "jsat_down")
            logger.info("OV POST /ov/handoff status=%s code=%s dest=%s", status, code[:48], dest)
            return {"status": "ERROR", "code": code, "result": None}
        result = data.get("result") if isinstance(data, dict) else None
        if not isinstance(result, dict):
            return {"status": "ERROR", "code": "jsat_down", "result": None}
        return {"status": "OK", "result": result}
    except Exception as exc:
        logger.info(
            "OV POST /ov/handoff falló dest=%s err=%s",
            dest,
            type(exc).__name__,
        )
        return {"status": "ERROR", "code": "jsat_down", "result": None}


def _code_to_reason(code: str) -> str:
    c = (code or "").strip().lower()
    if c in ("identity_not_found", "jsat_0"):
        return _REASON_JSAT_0
    if c in ("identity_ambiguous", "jsat_n"):
        return _REASON_JSAT_N
    if c in ("destination_forbidden",):
        return _REASON_DEST_FORBIDDEN
    return _REASON_JSAT_DOWN


def resolve_handoff(
    intent: str,
    abonado: Any | None = None,
    *,
    db: Session | None = None,
    canal: str = "",
    phone_candidates: Any = None,
) -> HandoffOutcome:
    """Resuelve URL OV. AUTH solo con JSAT v2. Sin round-robin de celulares."""
    mapped_intent = KEY_TO_INTENT.get((intent or "").strip().lower()) or (intent or "").strip().lower()
    dest = destination_for_intent(intent)
    if not dest:
        outcome = HandoffOutcome(
            mode=MODE_FAILED,
            url="",
            destination="",
            intent=mapped_intent,
            reason=_REASON_DEST_FORBIDDEN,
        )
        record_handoff_metric(outcome.mode, canal=canal, intent=mapped_intent, reason=outcome.reason)
        return outcome

    from app.services.ov_batan import resolve_ov_batan

    cfg = resolve_ov_batan(db)
    public_base = str(cfg.get("public_url") or DEFAULT_AUDIENCE)
    public = public_url_for_destination(dest, public_base=public_base)

    reason_id = identity_reason(abonado, phone_candidates=phone_candidates)
    if reason_id:
        mode = MODE_PUBLIC
        if reason_id == _REASON_AMBIGUOUS:
            mode = MODE_PUBLIC
        outcome = HandoffOutcome(
            mode=mode,
            url=public,
            destination=dest,
            intent=mapped_intent,
            reason=reason_id,
        )
        record_handoff_metric(outcome.mode, canal=canal, intent=mapped_intent, reason=outcome.reason)
        return outcome

    dni = canonical_dni(abonado)
    if not dni:
        outcome = HandoffOutcome(
            mode=MODE_PUBLIC,
            url=public,
            destination=dest,
            intent=mapped_intent,
            reason=_REASON_NO_DNI,
        )
        record_handoff_metric(outcome.mode, canal=canal, intent=mapped_intent, reason=outcome.reason)
        return outcome

    if handoff_v2_enabled(db):
        raw = request_ov_handoff(dni=dni, destination=dest, db=db, resource_id=None)
        if raw and str(raw.get("status") or "").upper() == "OK":
            result = raw.get("result") if isinstance(raw.get("result"), dict) else {}
            handoff_url = str((result or {}).get("handoff_url") or "").strip()
            expires = (result or {}).get("expires_in")
            try:
                exp_n = int(expires) if expires is not None else DEFAULT_TTL_SECONDS
            except (TypeError, ValueError):
                exp_n = DEFAULT_TTL_SECONDS
            if url_host_allowed(handoff_url, public_base=public_base):
                outcome = HandoffOutcome(
                    mode=MODE_AUTHENTICATED,
                    url=handoff_url,
                    destination=dest,
                    intent=mapped_intent,
                    reason="",
                    expires_in=exp_n,
                )
                record_handoff_metric(
                    outcome.mode, canal=canal, intent=mapped_intent, reason=""
                )
                return outcome
            logger.info("OV handoff_url host no allowlisted dest=%s", dest)
            outcome = HandoffOutcome(
                mode=MODE_PUBLIC,
                url=public,
                destination=dest,
                intent=mapped_intent,
                reason=_REASON_HOST,
            )
            record_handoff_metric(
                outcome.mode, canal=canal, intent=mapped_intent, reason=outcome.reason
            )
            return outcome
        code = str((raw or {}).get("code") or "jsat_down")
        reason = _code_to_reason(code)
        mode = MODE_FAILED if reason == _REASON_DEST_FORBIDDEN else MODE_PUBLIC
        url = "" if mode == MODE_FAILED else public
        outcome = HandoffOutcome(
            mode=mode,
            url=url,
            destination=dest,
            intent=mapped_intent,
            reason=reason,
        )
        record_handoff_metric(outcome.mode, canal=canal, intent=mapped_intent, reason=outcome.reason)
        return outcome

    # Entrada pública verificada (ov.batan.coop/#/…). Sin sesión OV en Eko.
    # GET /ov/link + tsid no se vende como AUTH. Flag v2 permanece off.
    outcome = HandoffOutcome(
        mode=MODE_PUBLIC,
        url=public,
        destination=dest,
        intent=mapped_intent,
        reason=_REASON_PUBLIC_ENTRY,
    )
    record_handoff_metric(outcome.mode, canal=canal, intent=mapped_intent, reason=outcome.reason)
    return outcome
