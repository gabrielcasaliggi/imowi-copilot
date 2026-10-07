"""Fix 3 (H21, Paso 4): tecnología del ``selected_service_ref`` desde BillTrack (solo lectura)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import portal_services as ps
from app.services.eko_service_selection import ServiceRef

ABONADO = SimpleNamespace(dni="11111111")
RAW = [
    SimpleNamespace(id="S1", login="fibra@test", service_type_code="INTFO"),
    SimpleNamespace(id="S2", login="radio@test", service_type_code="INTBA"),
    SimpleNamespace(id="S3", login="raro@test", service_type_code="XXX"),
]


def _ref(service_id: str = "", login: str = "", service_type: str = "internet") -> ServiceRef:
    return ServiceRef(service_id=service_id, login=login, service_type=service_type, client_number="1")


@pytest.fixture
def billtrack(monkeypatch):
    llamadas = []

    def fake(db, abonado):
        llamadas.append(abonado.dni)
        return RAW, None

    monkeypatch.setattr(ps, "_load_raw_services", fake)
    return llamadas


@pytest.mark.parametrize(
    ("ref", "esperado"),
    [
        (_ref("S1"), "internet_ftth"),
        (_ref("S2"), "internet_radio"),
        (_ref("", "RADIO@test"), "internet_radio"),  # sin id: match por login
        (_ref("S3"), None),  # código desconocido: no se infiere
        (_ref("NO"), None),
        (_ref("S1", service_type="mobile"), None),
        (None, None),
    ],
)
def test_tecnologia_por_servicio_seleccionado(billtrack, ref, esperado):
    db = SimpleNamespace(info={})
    assert ps.tecnologia_servicio_seleccionado(db, ABONADO, ref) == esperado


def test_billtrack_caido_no_infiere(monkeypatch):
    monkeypatch.setattr(ps, "_load_raw_services", lambda db, ab: (None, "source_error"))
    assert ps.tecnologia_servicio_seleccionado(SimpleNamespace(info={}), ABONADO, _ref("S1")) is None


def test_una_sola_consulta_a_billtrack_por_turno(billtrack):
    db = SimpleNamespace(info={})
    ps.tecnologia_servicio_seleccionado(db, ABONADO, _ref("S1"))
    ps.tecnologia_servicio_seleccionado(db, ABONADO, _ref("S2"))
    assert billtrack == ["11111111"]

