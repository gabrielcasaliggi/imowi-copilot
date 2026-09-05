"""Extractor de casos Botmaker (anonimiza, filtra menús, clasifica)."""

from __future__ import annotations

import json
from pathlib import Path

from qa_bot.corpus_botmaker import (
    _es_ruido_turno,
    clasificar_categoria,
    extraer_caso_sesion,
    extraer_casos,
    extraer_desde_paths,
    iter_sesiones_archivo,
)

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "botmaker_sesiones_muestra.json"


def test_clasificar_categoria():
    assert clasificar_categoria(["no tengo internet en casa"]) == "internet"
    assert clasificar_categoria(["quiero pagar la factura"]) == "facturacion"
    assert clasificar_categoria(["hola"]) == "otro"


def test_extrae_sesiones_y_anonimiza():
    sesiones = list(iter_sesiones_archivo(_FIXTURE))
    assert len(sesiones) == 4
    casos = extraer_casos(sesiones, fuente="muestra.json", categoria=None)
    assert {c.categoria for c in casos} >= {"internet", "facturacion"}
    fibra = next(c for c in casos if "internet" in c.apertura.lower())
    assert len(fibra.turnos_usuario) >= 2
    assert all(c.apertura.strip() not in {"7", "2"} for c in casos)

    factura = next(c for c in casos if c.categoria == "facturacion")
    assert "[dni]" in factura.apertura
    assert "30111222" not in factura.apertura

    radio = next(
        c for c in casos if "antena" in c.apertura.lower() or "bai" in c.apertura.lower()
    )
    assert "[telefono]" in radio.apertura
    assert "5492235551111" not in radio.apertura


def test_menu_numerico_no_genera_caso():
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    menu = next(s for s in data["items"] if s["id"] == "sess-menu-7")
    assert extraer_caso_sesion(menu) is None


def test_filtro_categoria_internet():
    sesiones = list(iter_sesiones_archivo(_FIXTURE))
    casos = extraer_casos(sesiones, categoria="internet")
    assert casos
    assert all(c.categoria == "internet" for c in casos)


def test_extraer_desde_archivo_fixture():
    casos = extraer_desde_paths([_FIXTURE], categoria=None, limit=10)
    assert len(casos) >= 2
    assert all(c.apertura for c in casos)


def test_saludo_no_es_apertura():
    assert _es_ruido_turno("Buen dia")
    assert _es_ruido_turno("No")
    assert not _es_ruido_turno("hola no tengo internet en casa")
    session = {
        "id": "sess-saludo",
        "messages": [
            {"from": "user", "content": {"type": "text", "text": "Buen dia"}},
            {"from": "user", "content": {"type": "text", "text": "No"}},
            {
                "from": "user",
                "content": {"type": "text", "text": "Hola! No tengo internet"},
            },
        ],
    }
    caso = extraer_caso_sesion(session, fuente="t.json")
    assert caso is not None
    assert caso.categoria == "internet"
    assert "internet" in caso.apertura.lower()
    assert caso.turnos_usuario[0] == caso.apertura
