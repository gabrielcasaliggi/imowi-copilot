"""H18 (cambio acotado de 2.2B): «la de »/«el de » solo eligen servicio seguidos de un servicio; el dígito suelto u
ordinal solo selecciona con el menú abierto."""

from __future__ import annotations

import pytest

from app.services.eko_service_selection import looks_like_selection_utterance as sel


@pytest.mark.parametrize("texto", ["ok pruebo la de 5", "la de 5", "el de 100", "tengo 5 equipos", "100", "la de casa", "el de siempre"])
def test_un_numero_o_un_de_suelto_no_selecciona(texto):
    assert not sel(texto)


@pytest.mark.parametrize("texto", ["la de imowi", "el de sensa", "la de fibra", "el de internet", "la de móvil", "el de tv"])
def test_de_seguido_de_servicio_sigue_seleccionando(texto):
    assert sel(texto)


@pytest.mark.parametrize("texto", ["2", "el 2", "la 3"])
def test_digito_u_ordinal_solo_con_menu_abierto(texto):
    assert not sel(texto)
    assert sel(texto, menu_open=True)


@pytest.mark.parametrize("texto", ["la de 5", "tengo 5 equipos", "100"])
def test_numero_en_frase_no_selecciona_ni_con_menu_abierto(texto):
    assert not sel(texto, menu_open=True)


@pytest.mark.parametrize("texto", ["ahora revisame el de tupaciretaBAI", "la de 2235550001", "el de tupaciretacuidabai"])
def test_de_seguido_de_login_sigue_seleccionando(texto):
    assert sel(texto)
