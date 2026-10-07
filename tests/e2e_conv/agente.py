"""Acciones de un agente humano en el panel, para usar como elemento de ``converse(script=[...])``.

Llaman a los endpoints reales (con sus hooks: cierre del hilo y calificación CSAT), no escriben en la base."""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

_client = TestClient(app)


def _headers() -> dict[str, str]:
    r = _client.post("/api/login", json={"usuario": "admin", "password": "admin"})  # credenciales de demo (README)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}", "X-Tenant-Slug": "coop-batan"}


def cierra_el_ticket_desde_el_panel(h) -> None:
    """tickets.py: ``PUT /tickets/{id}`` con estado Cerrado (cierra el hilo y pide la calificación)."""
    assert h.ticket_id, "la conversación vigente no tiene ticket"
    r = _client.put(f"/api/v1/tickets/{h.ticket_id}", headers=_headers(), json={"estado": "Cerrado", "resolucion_tecnica": "Resuelto por el agente"})
    assert r.status_code == 200, r.text


def cierra_la_conversacion_desde_la_bandeja(h) -> None:
    """inbox.py: ``POST /inbox/conversations/{id}/close`` (cierra el hilo y pide la calificación)."""
    r = _client.post(f"/api/v1/inbox/conversations/{h.conv_id}/close", headers=_headers(), json={"nota": "Resuelto por el agente"})
    assert r.status_code == 200, r.text


# ----------------------------------------------------------------------------- re-login del abonado (portal web / app)
_PIN = "123456"
_OTP = "4821"


def reingresa_al_portal(via: str = "pin", canal: str = "web"):
    """Acción del abonado entre turnos: vuelve a iniciar sesión en el portal por el endpoint real (``login-pin`` o ``verify`` del
    OTP) con el header ``X-Canal`` del canal (``web`` o ``app``). Solo prepara el vínculo/desafío que en prod dejan el alta del PIN
    y ``auth/start``; el reset de la conversación lo decide el endpoint. Requiere ``converse(..., reconocer_telefono=True)``."""
    assert via in ("pin", "otp") and canal in ("web", "app")

    def _accion(h) -> None:
        from datetime import UTC, datetime, timedelta

        from app.estate.database import get_session_factory
        from app.estate.models import PortalAbonadoLink, PortalOtpChallenge
        from app.estate.security import hash_dni, hash_pin, hash_token

        hdr = {"X-Canal": canal}
        with get_session_factory()() as db:
            if via == "pin":
                db.add(PortalAbonadoLink(organizacion_id=h.org_id, dni_normalized=h.dni, dni_hash=hash_dni(h.dni), abonado_ref=f"ref{h.dni}",
                                         pin_hash=hash_pin(_PIN), activo="Sí"))
                db.commit()
                r = _client.post("/api/v1/portal/auth/login-pin", headers=hdr, json={"dni": h.dni, "pin": _PIN, "org_slug": "coop-batan"})
            else:
                ch = PortalOtpChallenge(organizacion_id=h.org_id, dni_normalized=h.dni, code_hash=hash_token(_OTP), abonado_ref=f"ref{h.dni}",
                                        expires_at=datetime.now(UTC) + timedelta(minutes=10))
                db.add(ch)
                db.commit()
                r = _client.post("/api/v1/portal/auth/verify", headers=hdr, json={"challenge_id": ch.id, "otp": _OTP, "org_slug": "coop-batan"})
        assert r.status_code == 200, r.text
        assert r.json()["conversacion"]["id"], r.text

    return _accion
