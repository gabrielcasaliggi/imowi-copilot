"""H16 (cambio acotado de 2.2B): «la fibra» / «el internet» / «mi internet» solo eligen servicio si son la única intención."""

from __future__ import annotations

import pytest

from app.domain.flujos_abonado import confirma_paso_hecho
from app.services.eko_service_selection import ServiceRef, looks_like_selection_utterance

REF = ServiceRef(service_id="int1", login="lemuramatiBAI", service_type="internet", client_number="1", label="Internet", product="Internet")


@pytest.mark.parametrize("texto", ["la fibra", "el internet", "mi internet", "quiero la fibra", "revisá el internet"])
def test_la_referencia_sola_sigue_siendo_seleccion(texto):
    assert looks_like_selection_utterance(texto)


@pytest.mark.parametrize(
    "texto",
    [
        "ya lo hice. la potencia de la fibra es buena?",
        "que potencia tengo en la fibra",
        "me anda lento mi internet",
        "ok y la potencia de la fibra esta bien?",
        "el internet no funciona",
        "¿cuánto da la fibra?",
    ],
)
def test_una_pregunta_o_un_sintoma_no_es_seleccion(texto):
    assert not looks_like_selection_utterance(texto)


def test_con_un_servicio_ya_seleccionado_la_referencia_ambigua_no_re_selecciona():
    assert not looks_like_selection_utterance("la fibra", selected_ref=REF)
    assert looks_like_selection_utterance("el fijo", selected_ref=REF)  # las referencias de 2.5D-2 no cambian
    # H18: el dígito suelto selecciona solo con el menú abierto
    assert not looks_like_selection_utterance("2", selected_ref=REF)
    assert looks_like_selection_utterance("2", selected_ref=REF, menu_open=True)


@pytest.mark.parametrize("texto", ["ya lo hice. la potencia de la fibra es buena?", "listo, y la potencia?", "Ya reinicié"])
def test_confirma_paso_hecho_aunque_siga_una_pregunta(texto):
    assert confirma_paso_hecho(texto)
    assert not confirma_paso_hecho("no lo hice todavía")


@pytest.mark.parametrize(
    "texto",
    [
        "ya lo hice. la potencia de la fibra es buena?",
        "me anda lento. tengo buena potencia?",
        "si esta en verde pero me anda lento. que potencia tengo en la fibra",
        "ok y la potencia de la fibra esta bien?",
        "señal de la fibra",
    ],
)
def test_las_preguntas_por_la_potencia_de_la_fibra_se_reconocen(texto):
    from app.domain.flujos_abonado import cliente_pregunta_potencia_onu

    assert cliente_pregunta_potencia_onu(texto)


@pytest.mark.parametrize("texto", ["más potencia al wifi", "el router tiene poca potencia", "la antena tiene buena potencia", "me anda lento"])
def test_otras_cosas_no_son_pregunta_por_la_potencia_de_la_ont(texto):
    from app.domain.flujos_abonado import cliente_pregunta_potencia_onu

    assert not cliente_pregunta_potencia_onu(texto)


@pytest.mark.parametrize(("texto", "acepta"), [("sí", True), ("dale", True), ("si por favor", True), ("ok", True), ("me anda lento", False), ("ya anda", False), ("100", False)])
def test_acepta_derivacion_solo_con_afirmativos_explicitos(texto, acepta):
    from app.domain.flujos_abonado import acepta_derivacion_clara

    assert acepta_derivacion_clara(texto) is acepta
