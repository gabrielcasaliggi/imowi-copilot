"""RC-10 — «id» dentro de un login no es un service_id (regresión dedicada 2.2B)."""

from __future__ import annotations

import pytest

from app.services.eko_service_selection import _extract_service_id, resolve_service_selection

CATALOGO = [
    {"id": "int1", "login": "lemuramatiBAI", "type": "internet", "label": "Casa", "active": True},
    {"id": "int2", "login": "tupaciretacuidaBAI", "type": "internet", "label": "Local", "active": True},
]


@pytest.mark.parametrize(
    "texto",
    [
        "tupaciretacuidaBAI",
        "ahora revisame el de tupaciretacuidaBAI",
        "revisame tupaciretacuidaBAI",
        "Guido22",
        "el valid2 anda",
        "la cuenta de Aida",
        "idBAI",
    ],
)
def test_id_dentro_de_otra_palabra_no_es_service_id(texto):
    assert _extract_service_id(texto) == ""


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("service_id: svc-1", "svc-1"),
        ("service id svc-2", "svc-2"),
        ("id svc-3", "svc-3"),
        ("ID=ABC-12", "ABC-12"),
        ("mi id: 12345", "12345"),
        ("12345678", "12345678"),
    ],
)
def test_ids_explicitos_siguen_extrayendose(texto, esperado):
    assert _extract_service_id(texto) == esperado


def test_un_login_con_id_ya_no_se_deniega_como_id_ajeno():
    res = resolve_service_selection(
        texto="ahora revisame el de tupaciretacuidaBAI", catalog=CATALOGO, client_number="1"
    )
    assert res.reason_code != "foreign_or_unknown_service_id"
    assert res.status != "denied"


def test_un_service_id_ajeno_sigue_denegado():
    res = resolve_service_selection(texto="service_id: ajeno-9", catalog=CATALOGO, client_number="1")
    assert res.status == "denied" and res.reason_code == "foreign_or_unknown_service_id"
