"""EKO-CTX-2 — cortes_zona desde ctx y fuera pago_qr_reciente."""

from __future__ import annotations

import copy

from app.services.canal_diagnostico_ia import _extras_servicio_y_planta
from app.services.eko_context import format_n1_contexto

FACTS = {
    "customer": {"display_name": "Ana", "line_msisdn": ""},
    "account": {"client_number": "1", "status": "activo", "plan": "x"},
    "billing": {"status": "stale", "balance": {"amount": "0"}},
    "services": {"status": "ok", "items": []},
    "tickets": {"status": "ok", "items": []},
}


def _txt(ctx):
    return format_n1_contexto(FACTS, extras=_extras_servicio_y_planta(ctx, None, None))


def test_outage_masivo_activo_informado():
    txt = _txt({"outage_id": "o1", "outage_nas": "NAS-SECRETO-1"})
    assert "- cortes_zona: incidente masivo activo en la zona, ya informado al abonado" in txt
    assert "NAS-SECRETO-1" not in txt and "o1" not in txt.split("cortes_zona")[1].splitlines()[0]


def test_outage_individual():
    txt = _txt({"outage_id": "o1", "outage_individual": True})
    assert "- cortes_zona: el abonado indicó que el problema es individual" in txt
    assert "masivo" not in txt


def test_outage_resuelto_avisado():
    txt = _txt({"outage_resuelto_avisado": "o1"})
    assert "- cortes_zona: incidente de la zona resuelto, ya avisado al abonado" in txt


def test_sin_outage_omite_linea_y_sin_placeholder():
    txt = _txt({})
    assert "cortes_zona" not in txt
    assert "integrar operaciones" not in txt
    assert "pago_qr_reciente" not in txt and "Fiserv" not in txt


def test_invitado_sin_pago_qr_reciente():
    txt = format_n1_contexto({"customer": None}, extras={})
    assert "pago_qr_reciente" not in txt
    assert "cortes_zona" not in txt
    assert "modo: invitado" in txt


def test_ctx_no_cambia():
    ctx = {"outage_id": "o1", "outage_individual": True, "outage_nas": "N"}
    before = copy.deepcopy(ctx)
    _extras_servicio_y_planta(ctx, None, None)
    assert ctx == before
