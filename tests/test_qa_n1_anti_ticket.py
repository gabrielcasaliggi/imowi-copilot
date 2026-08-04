"""Regresiones QA N1 — anti-ticket prematuro, falso cierre, QR, typos."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.domain.flujos_abonado import (
    clasificar_intencion,
    contiene_sintoma_canal,
    detecta_frustracion,
    es_escape_agente,
    indica_resuelto,
    pide_humano,
)
from main import app

client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": "admin", "password": "admin"})
    assert r.status_code == 200
    return {
        "Authorization": f"Bearer {r.json()['token']}",
        "X-Tenant-Slug": "coop-batan",
    }


def _guest_portal() -> str:
    r = client.post("/api/v1/portal/session", json={"org_slug": "coop-batan"})
    assert r.status_code == 200
    return r.json()["portal_token"]


def _portal_msg(token: str, texto: str, *, usar_hint: bool = False) -> dict:
    # Portal messages always go through canal; usar_llama resolved server-side.
    r = client.post(
        "/api/v1/portal/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"texto": texto},
    )
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Unitarios dominio
# ---------------------------------------------------------------------------

def test_indica_resuelto_no_cierra_cobertura_parcial():
    assert indica_resuelto("En el living anda bien, lejos no") is False
    assert indica_resuelto("anda bien en el living pero no llega al fondo") is False
    assert indica_resuelto("ya anda todo") is True
    assert indica_resuelto("mejoró") is True
    assert indica_resuelto("ya funciona") is True


def test_detecta_frustracion_requiere_progreso_n1():
    ctx0 = {"ultima_queja": "no tengo internet", "paso_idx": 0, "reiteracion_queja": 1}
    assert detecta_frustracion("No tengo internet", ctx0) is False
    ctx2 = {"ultima_queja": "no tengo internet", "paso_idx": 2, "reiteracion_queja": 1}
    assert detecta_frustracion("No tengo internet", ctx2) is True


def test_escape_agente_y_sintoma():
    from app.domain.flujos_abonado import pide_humano_en_flujo_activo

    assert es_escape_agente("*agente*") is True
    assert es_escape_agente("agente") is True
    assert es_escape_agente("Quiero hablar con un operador") is False
    assert contiene_sintoma_canal("pasame con operador que no anda internet") is True
    assert contiene_sintoma_canal("quiero un operador") is False
    assert pide_humano("quiero un operador") is True
    assert pide_humano("nose como hacer eso, deberia venir un tecnico") is True
    assert pide_humano("tienen que mandar una visita técnica") is True
    assert pide_humano_en_flujo_activo(
        "deberia venir un tecnico",
        {"intencion": "wifi", "diag_turnos": 2},
    ) is True
    assert pide_humano_en_flujo_activo(
        "deberia venir un tecnico",
        {"intencion": "wifi", "diag_turnos": 0, "paso_idx": 0},
    ) is False
    assert pide_humano_en_flujo_activo(
        "quiero un operador",
        {"intencion": "", "diag_turnos": 0},
    ) is False


def test_typo_internet_clasifica():
    assert clasificar_intencion("ola no anda el interntt, no me carga nadaa") == "internet"
    assert clasificar_intencion("Me cortaron por falta de pago, como pago") == "corte_deuda"


# ---------------------------------------------------------------------------
# Portal / canal
# ---------------------------------------------------------------------------

def test_pedido_humano_sin_sintoma_no_crea_ticket_inmediato():
    token = _guest_portal()
    data = _portal_msg(token, "Quiero hablar con una persona, pasame con un operador")
    assert data.get("ok") is True
    assert data.get("estado") == "bot"
    assert not data.get("ticket_id")
    resp = (data.get("respuesta") or "").lower()
    assert "ticket" not in resp
    assert "agente" in resp or "internet" in resp or "contame" in resp


def test_escape_agente_explicito_crea_ticket():
    token = _guest_portal()
    _portal_msg(token, "Hola")
    data = _portal_msg(token, "*agente*")
    assert data.get("ok") is True
    assert data.get("ticket_id")
    assert data.get("estado") == "espera_agente"


def test_segunda_insistencia_humano_crea_ticket():
    token = _guest_portal()
    r1 = _portal_msg(token, "Quiero hablar con un agente humano")
    assert not r1.get("ticket_id")
    r2 = _portal_msg(token, "Pasame con un operador ya")
    assert r2.get("ticket_id")
    assert r2.get("estado") == "espera_agente"


def test_humano_con_sintoma_entra_n1():
    token = _guest_portal()
    data = _portal_msg(
        token,
        "Quiero un operador porque no me anda internet",
    )
    assert data.get("ok") is True
    assert data.get("estado") == "bot"
    assert not data.get("ticket_id")
    assert data.get("intencion") == "internet"
    resp = (data.get("respuesta") or "").lower()
    assert "ticket" not in resp
    assert "jsc-" not in resp


def test_reiteracion_temprana_no_ticket():
    token = _guest_portal()
    r1 = _portal_msg(token, "No tengo internet")
    assert r1.get("estado") == "bot"
    assert not r1.get("ticket_id")
    r2 = _portal_msg(token, "No tengo internet")
    assert r2.get("estado") == "bot"
    assert not r2.get("ticket_id")
    r3 = _portal_msg(token, "No tengo internet")
    assert r3.get("estado") == "bot"
    assert not r3.get("ticket_id")


def test_corte_deuda_invitado_pide_dni():
    """Invitado con corte/pago: pedir DNI; no inventar saldo ni soltar QR a ciegas."""
    token = _guest_portal()
    data = _portal_msg(token, "Me cortaron el servicio por falta de pago, como pago?")
    assert data.get("ok") is True
    resp = (data.get("respuesta") or "").lower()
    assert "dni" in resp
    assert "fiserv" not in resp
    assert not data.get("ticket_id")


def test_saldo_billtrack_no_fuerza_cobro_ante_aumento_imowi():
    """Regresión: billing_balance > 0 no debe pisar reclamo IMOWI + aumento con QR."""
    from app.estate.models import Abonado
    from app.services.canal_abonado import _deberia_priorizar_corte_deuda, _es_solo_dni
    from app.domain.flujos_abonado import clasificar_intencion, detectar_temas_duales

    msg = "tengo problemas con imowi y quiero reclamar por una factura con aumento"
    assert set(detectar_temas_duales(msg)) == {"tecnico", "facturacion"}
    assert clasificar_intencion(msg) == "facturacion"

    abo = Abonado(
        organizacion_id="x",
        dni="30111222",
        nombre="JORGE",
        estado="activo",
        deuda_monto="55779.99",
    )
    assert _deberia_priorizar_corte_deuda(abo, msg, "facturacion") is False
    assert _deberia_priorizar_corte_deuda(
        abo, "Me cortaron por falta de pago, como pago?", "general"
    ) is True
    assert _es_solo_dni("13920806") is True
    assert _es_solo_dni("mi dni es 13920806") is False


def test_wifi_parcial_no_cierra_resuelto():
    token = _guest_portal()
    _portal_msg(token, "El WiFi no llega a la habitación del fondo")
    data = _portal_msg(token, "En el living anda bien, lejos no")
    assert data.get("estado") != "cerrado"
    resp = (data.get("respuesta") or "").lower()
    assert "quedó resuelto" not in resp
    assert "quedo resuelto" not in resp
    assert "genial" not in resp or "lejos" in resp or "wifi" in resp or "router" in resp


def test_inbox_pide_agente_ya_no_ticket_en_primer_turno():
    """Regresión del comportamiento anterior: 1er pedido humano ≠ ticket."""
    headers = _admin_headers()
    tel = "5492235560199"
    r0 = client.post(
        "/api/v1/inbox/simulate",
        headers=headers,
        json={"telefono": tel, "texto": "Hola", "usar_llama": False},
    )
    assert r0.status_code == 200
    r = client.post(
        "/api/v1/inbox/simulate",
        headers=headers,
        json={
            "telefono": tel,
            "texto": "Quiero hablar con un agente humano",
            "usar_llama": False,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("estado") == "bot"
    assert not data.get("ticket_id")
    # Escape hatch sigue funcionando
    r2 = client.post(
        "/api/v1/inbox/simulate",
        headers=headers,
        json={"telefono": tel, "texto": "*agente*", "usar_llama": False},
    )
    assert r2.status_code == 200
    assert r2.json().get("ticket_id")
    assert r2.json().get("estado") == "espera_agente"
