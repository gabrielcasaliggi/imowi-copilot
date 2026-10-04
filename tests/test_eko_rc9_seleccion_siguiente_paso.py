"""RC-9 (ADR contrato de turno): tras elegir servicio el journey da el siguiente paso y retoma el problema declarado."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import eko_journeys as ej


@pytest.mark.parametrize(
    "texto",
    ["tengo problemas con mi línea de imowi", "no me anda la tele sensa", "se corta la señal", "sin datos desde ayer"],
)
def test_detecta_problema_declarado(texto):
    assert ej._declares_problem(texto)


@pytest.mark.parametrize("texto", ["1", "quiero ver el servicio de sensa tv", "el de lemuramatiBAI", "listame mis servicios"])
def test_no_toma_como_problema_una_seleccion_o_un_pedido(texto):
    assert not ej._declares_problem(texto)


@pytest.mark.parametrize(
    "tipo,fragmento",
    [("movil", "sin señal"), ("tv", "Sensa"), ("internet", "Internet"), ("voip", "Contame")],
)
def test_siguiente_paso_por_tipo_de_servicio(tipo, fragmento):
    assert fragmento in ej._next_step_question(SimpleNamespace(service_type=tipo))


def test_mensaje_de_seleccion_retoma_solo_si_habia_problema():
    ref = SimpleNamespace(service_type="movil")
    con = ej._selection_done_message("Imowi 5 GB", "2235550001", ref, "no puedo llamar")
    sin = ej._selection_done_message("Imowi 5 GB", "2235550001", ref, "")
    assert con.startswith("Listo: seleccioné «Imowi 5 GB». (cuenta 2235550001)") and "Retomo" in con and con.endswith("?")
    assert sin.startswith("Listo: seleccioné «Imowi 5 GB». (cuenta 2235550001)") and "Retomo" not in sin and sin.endswith("?")
