"""Triaje internet: no repetir síntoma; daño de campo → N2."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.domain.flujos_abonado import es_dano_campo_obvio, es_saludo_corto
from main import app

client = TestClient(app)

_SINTOMA = "no te carga nada, anda lento, se corta, o es solo el wifi"
_ALCANCE = "todos los dispositivos"


def test_es_dano_campo_obvio():
    assert es_dano_campo_obvio(
        "paso un camión y arranco el cable de teléfono y otros cables"
    )
    assert es_dano_campo_obvio("Se me quemo el internet")
    assert es_dano_campo_obvio("se me quemó el módem")
    assert not es_dano_campo_obvio("no tengo internet")
    assert not es_dano_campo_obvio("el wifi anda lento")


def test_saludo_con_sintoma_no_es_saludo_corto():
    assert es_saludo_corto("hola")
    assert not es_saludo_corto("Hola ! No tengo internet")
    assert not es_saludo_corto("Hola !! Necesito internet !!!!!!!!")


def _identified_portal(dni: str = "30111222") -> str:
    start = client.post(
        "/api/v1/portal/auth/start",
        json={"dni": dni, "org_slug": "coop-batan"},
    )
    assert start.status_code == 200, start.text
    body = start.json()
    verify = client.post(
        "/api/v1/portal/auth/verify",
        json={
            "challenge_id": body["challenge_id"],
            "otp": body["debug_otp"],
            "org_slug": "coop-batan",
        },
    )
    assert verify.status_code == 200, verify.text
    data = verify.json()
    from app.estate import canal_repo as crepo
    from app.estate.database import get_session_factory
    from app.estate.models import ConversacionCanal

    conv_id = data["conversacion"]["id"]
    Session = get_session_factory()
    with Session() as db:
        c = db.get(ConversacionCanal, conv_id)
        if c:
            c.estado = "bot"
            c.ticket_id = ""
            c.agente_id = ""
            ctx = crepo.get_contexto(c)
            for k in (
                "intencion",
                "paso_idx",
                "diag_turnos",
                "pasos_cubiertos",
                "reiteracion_queja",
                "ultima_queja",
                "wifi_rama_activada",
            ):
                ctx.pop(k, None)
            crepo.set_contexto(c, ctx)
            db.commit()
    return data["portal_token"]


def _msg(token: str, texto: str) -> dict:
    from app.domain.flujos_abonado import PLAYBOOKS

    with (
        patch("app.api.v1.portal.resolve_canal_usar_llama", return_value=False),
        patch("app.services.canal_abonado.playbooks_as_pasos", return_value=PLAYBOOKS),
    ):
        r = client.post(
            "/api/v1/portal/messages",
            headers={"Authorization": f"Bearer {token}"},
            json={"texto": texto},
        )
    assert r.status_code == 200, r.text
    return r.json()


def test_corte_total_no_repite_sintoma_ni_alcance():
    token = _identified_portal()
    r1 = _msg(token, "No tengo internet")
    low1 = (r1.get("respuesta") or "").lower()
    assert r1.get("estado") == "bot"
    assert not r1.get("ticket_id")
    assert _SINTOMA not in low1
    assert _ALCANCE not in low1
    assert "fibra" in low1 or "antena" in low1

    r2 = _msg(token, "Hola !! Necesito internet !!!!!!!!")
    low2 = (r2.get("respuesta") or "").lower()
    assert r2.get("estado") == "bot"
    assert not r2.get("ticket_id")
    assert _SINTOMA not in low2
    assert "¡hola!" not in (r2.get("respuesta") or "").lower()[:20]


def test_repite_queja_avanza_a_tipo_acceso():
    token = _identified_portal()
    r1 = _msg(token, "Buen día internet dejo de funcionar")
    r2 = _msg(token, "Buen día!! Me dejó de funcionar internet")
    low2 = (r2.get("respuesta") or "").lower()
    assert r1.get("estado") == "bot"
    assert r2.get("estado") == "bot"
    assert _SINTOMA not in low2
    assert not r2.get("ticket_id")


def test_camion_arranca_cable_deriva_n2():
    token = _identified_portal()
    data = _msg(
        token,
        "Hola mira paso un camión y arranco el cable de teléfono y otros cables "
        "más no tengo tel tampoco internet",
    )
    low = (data.get("respuesta") or "").lower()
    assert data.get("ticket_id")
    assert data.get("estado") in ("espera_agente", "con_agente")
    assert "visita" in low or "derivo" in low or "agente" in low
    assert _SINTOMA not in low
    assert _ALCANCE not in low


def test_equipo_quemado_deriva_n2():
    token = _identified_portal()
    data = _msg(token, "Se me quemo el internet")
    low = (data.get("respuesta") or "").lower()
    assert data.get("ticket_id")
    assert "visita" in low or "derivo" in low or "agente" in low
    assert _SINTOMA not in low
