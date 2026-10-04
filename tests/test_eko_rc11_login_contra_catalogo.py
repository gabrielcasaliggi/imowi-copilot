"""RC-11 — el login se resuelve contra el catálogo del abonado, no con la regex ``INT*``."""

from __future__ import annotations

import pytest

from app.services.eko_service_selection import _login_from_catalog, resolve_service_selection

CAT = [
    {"id": "int1", "login": "lemuramatiBAI", "type": "internet", "label": "Casa", "product": "Casa", "active": True},
    {"id": "int2", "login": "tupaciretacuidaBAI", "type": "internet", "label": "Local", "product": "Local", "active": True},
    {"id": "int3", "login": "tupaciretaBAI", "type": "internet", "label": "Campo", "product": "Campo", "active": True},
    {"id": "m1", "login": "2235550001", "type": "movil", "label": "Imowi 5 GB", "product": "Imowi 5 GB", "active": True},
    {"id": "tv1", "login": "", "type": "tv", "label": "Sensa", "product": "Sensa TV", "active": True},
]


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("ahora revisame el de tupaciretaBAI", "tupaciretaBAI"),
        ("revisá TUPACIRETACUIDABAI por favor", "tupaciretacuidaBAI"),
        ("lemuramatiBAI", "lemuramatiBAI"),
        ("mi línea 2235550001", "2235550001"),
        ("la de tupaciretaBAI.", "tupaciretaBAI"),
    ],
)
def test_login_nombrado_en_el_texto(texto, esperado):
    assert _login_from_catalog(texto, CAT) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "tupaciretaBAI2",  # no es palabra completa
        "xtupaciretaBAI",
        "el de tupaciretaBAI y lemuramatiBAI",  # dos → no adivina
        "quiero ver mi tele",
        "",
        "un login ajeno otroBAI",
    ],
)
def test_no_adivina(texto):
    assert _login_from_catalog(texto, CAT) == ""


def test_substring_de_otro_login_no_cuenta():
    # «tupaciretaBAI» está contenido en «xxtupaciretaBAI» pero no en «tupaciretacuidaBAI»
    assert _login_from_catalog("tupaciretacuidaBAI", CAT) == "tupaciretacuidaBAI"


def test_resolve_selecciona_el_servicio_nombrado():
    res = resolve_service_selection(
        texto="ahora revisame el de tupaciretaBAI", catalog=CAT, client_number="1"
    )
    assert res.status == "selected"
    assert res.ref.service_id == "int3" and res.ref.login == "tupaciretaBAI"
    assert res.ref.client_number == "1"


def test_resolve_con_login_con_id_adentro():
    res = resolve_service_selection(
        texto="ahora revisame el de tupaciretacuidaBAI", catalog=CAT, client_number="1"
    )
    assert res.status == "selected" and res.ref.service_id == "int2"


def test_resolve_sin_login_nombrado_sigue_preguntando():
    res = resolve_service_selection(texto="el de casa y el de campo", catalog=CAT, client_number="1")
    assert res.status != "selected" or res.ref is None


def test_login_ajeno_no_se_selecciona():
    res = resolve_service_selection(texto="revisame ajenoBAI", catalog=CAT, client_number="1")
    assert res.status != "selected"


def test_login_int_clasico_sigue_andando():
    cat = [{"id": "a", "login": "INT600", "type": "internet", "label": "x", "product": "x", "active": True},
           {"id": "b", "login": "INT300", "type": "internet", "label": "y", "product": "y", "active": True}]
    res = resolve_service_selection(texto="quiero INT300", catalog=cat, client_number="1")
    assert res.status == "selected" and res.ref.service_id == "b"
