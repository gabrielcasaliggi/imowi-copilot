"""Tests de la capa de comprensión contextual del canal abonado."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain.comprension_abonado import PreguntaPendienteAbonado
from app.services.comprension_abonado import (
    eleccion_aviso_deuda_desde_ctx,
    fusionar_comprension_en_ctx,
    inferir_pregunta_pendiente_abonado,
    interpretar_turno_abonado,
    normalizar_lexico_abonado,
    preparar_turno_comprension,
    tipo_acceso_confirmado_en_hechos,
)
from app.services.comprension_lexico import cargar_lexico_curado, frases_tecnico_en_aviso_deuda

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "comprension_casos_botmaker.json"


def _casos_botmaker() -> list[dict]:
    if not _FIXTURES.is_file():
        return []
    return json.loads(_FIXTURES.read_text(encoding="utf-8"))


@pytest.mark.parametrize("caso", _casos_botmaker(), ids=lambda c: c["id"])
def test_casos_minados_botmaker(caso: dict):
    comp = interpretar_turno_abonado(
        caso["user"],
        ctx=caso.get("ctx") or {},
        ultimo_bot=caso.get("bot") or "",
    )
    ctx = fusionar_comprension_en_ctx(dict(caso.get("ctx") or {}), comp)
    if caso.get("expect_eleccion"):
        assert comp.eleccion_aviso_deuda == caso["expect_eleccion"]
        assert eleccion_aviso_deuda_desde_ctx(ctx) == caso["expect_eleccion"]
    if caso.get("expect_tecnologia"):
        assert (comp.hechos_nuevos.get("tecnologia_acceso") or ctx.get("tecnologia_acceso")) == caso[
            "expect_tecnologia"
        ]
    if caso.get("expect_interferencias_ok"):
        assert (ctx.get("hechos") or {}).get("interferencias_descartadas") is True


def test_lexico_curado_cargado():
    data = cargar_lexico_curado()
    assert data.get("version") == 1
    assert int(data.get("sessions_muestra") or 0) >= 1000
    assert len(frases_tecnico_en_aviso_deuda()) >= 5


def test_normalizar_lexico_typos_frecuentes():
    assert "internet" in normalizar_lexico_abonado("no tengo intenret")
    assert "wifi" in normalizar_lexico_abonado("el wfi no anda")
    assert "bai" in normalizar_lexico_abonado("es beibe")


def test_inferir_pregunta_aviso_deuda_desde_ctx():
    pregunta = inferir_pregunta_pendiente_abonado(
        "¿Preferís pagar o seguir con el diagnóstico?",
        {"intencion": "aviso_deuda"},
    )
    assert pregunta == PreguntaPendienteAbonado.AVISO_DEUDA


def test_aviso_deuda_internet_elige_tecnico():
    comp = interpretar_turno_abonado(
        "internet",
        ctx={"intencion": "aviso_deuda", "intencion_tecnica_pendiente": "wifi"},
        ultimo_bot="¿Te ayudo a pagar o seguimos con el diagnóstico?",
    )
    assert comp.eleccion_aviso_deuda == "tecnico"
    assert comp.confianza >= 0.8


def test_aviso_deuda_bai_elige_tecnico_y_guarda_tecnologia():
    comp = interpretar_turno_abonado(
        "beibe",
        ctx={"intencion": "aviso_deuda"},
        ultimo_bot="Tenés saldo pendiente. ¿Pagás o seguimos?",
    )
    assert comp.eleccion_aviso_deuda == "tecnico"
    assert comp.hechos_nuevos.get("tecnologia_acceso") == "internet_radio"


def test_aviso_deuda_solo_pago():
    comp = interpretar_turno_abonado(
        "quiero pagar la deuda",
        ctx={"intencion": "aviso_deuda"},
        ultimo_bot="¿Pagás o seguimos?",
    )
    assert comp.eleccion_aviso_deuda == "pago"


def test_tipo_acceso_desde_menu():
    comp = interpretar_turno_abonado(
        "la anel",
        ctx={"menu_paso": "tipo"},
        ultimo_bot="¿Tenés fibra, antena o ADSL?",
    )
    assert comp.hechos_nuevos.get("tecnologia_acceso") == "internet_radio"


def test_no_solo_en_ese_es_varios_dispositivos():
    from app.domain.flujos_abonado import interpreta_alcance_dispositivos

    assert interpreta_alcance_dispositivos("no solo en ese") == "todos"
    assert interpreta_alcance_dispositivos("solo en este dispositivo") == "uno"
    assert interpreta_alcance_dispositivos("en la table") == "uno"


def test_wifi_a_veces_zona_parcial():
    comp = interpretar_turno_abonado(
        "a veces",
        ctx={"intencion": "wifi"},
        ultimo_bot="¿Te pasa lo mismo en otras habitaciones o solo ahí?",
    )
    assert comp.hechos_nuevos.get("zona_wifi") == "parcial"


def test_wifi_table_typo_marca_sin_ethernet():
    texto, ctx = preparar_turno_comprension(
        "en la table",
        {"intencion": "wifi", "pasos_cubiertos": ["zona_wifi"]},
        historial=[
            {"autor": "bot", "texto": "¿Les pasa a todos los equipos o solo a uno?"},
        ],
    )
    assert "tablet" in texto.lower()
    hechos = ctx.get("hechos") or {}
    assert hechos.get("dispositivo_sin_ethernet") is True
    assert hechos.get("dispositivo_afectado") == "tablet"
    assert "conexion_cableada" in (ctx.get("pasos_cubiertos") or [])
    assert hechos.get("alcance_wifi") == "uno"
    assert "otros_dispositivos_wifi" in (ctx.get("pasos_cubiertos") or [])


def test_wifi_interferencias_negacion_marca_paso():
    comp = interpretar_turno_abonado(
        "no hay nada",
        ctx={"intencion": "wifi"},
        ultimo_bot="¿Hay objetos metálicos cerca del router WiFi?",
    )
    assert comp.hechos_nuevos.get("interferencias_descartadas") is True
    ctx = fusionar_comprension_en_ctx({"pasos_cubiertos": []}, comp)
    assert "canal_interferencia" in ctx["pasos_cubiertos"]


def test_fusionar_hechos_no_pisa_tecnologia_previa_sin_nueva():
    ctx = {"hechos": {"tecnologia_acceso": "internet_ftth"}, "pasos_cubiertos": []}
    comp = interpretar_turno_abonado(
        "dale",
        ctx={"intencion": "aviso_deuda", "intencion_tecnica_pendiente": "wifi"},
        ultimo_bot="¿Seguimos?",
    )
    ctx = fusionar_comprension_en_ctx(ctx, comp)
    assert tipo_acceso_confirmado_en_hechos(ctx) == "internet_ftth"


def test_preparar_turno_expone_eleccion_en_ctx():
    texto, ctx = preparar_turno_comprension(
        "internet",
        {"intencion": "aviso_deuda"},
        historial=[
            {"autor": "bot", "texto": "¿Pagás o seguimos con el diagnóstico?"},
            {"autor": "cliente", "texto": "internet"},
        ],
    )
    assert texto == "internet"
    assert eleccion_aviso_deuda_desde_ctx(ctx) == "tecnico"


def test_confirmacion_corta_tras_pregunta_si_no():
    comp = interpretar_turno_abonado(
        "sip",
        ctx={"intencion": "internet_ftth"},
        ultimo_bot="¿Ya reiniciaste la cajita? ¿Pudiste?",
    )
    assert comp.hechos_nuevos.get("confirmacion_positiva") is True
