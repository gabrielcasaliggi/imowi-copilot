"""Tests branding público / asistente Eko."""

from app.api.v1.branding import public_branding
from app.branding_assistant import frase_soy_eko, saludo_identificacion_dni


def test_public_branding_incluye_eko():
    data = public_branding()
    assert data["bot_display_name"] == "Eko"
    assert data["bot_display_name_short"] == "EKO"
    assert data["product_display_name"] == "Soporte Batán"
    assert "asistente virtual" in data["assistant_tagline"].lower()
    assert "Eko" in data["assistant_intro"]
    assert "Soporte Batán" in data["assistant_intro"]


def test_saludos_usan_asistente_virtual():
    intro = frase_soy_eko()
    assert "Eko" in intro
    assert "asistente virtual" in intro
    assert "Soporte Batán" in intro
    assert "bot" not in intro.lower()

    dni = saludo_identificacion_dni()
    assert "DNI" in dni
    assert "Eko" in dni
