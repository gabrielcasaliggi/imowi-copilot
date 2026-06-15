"""Tests del adaptador JSC local."""

from app.estate.models import LineaJSC
from app.jsc import connector as jsc


def test_buscar_linea_normaliza_prefijo_pais_o_carrier(db):
    session, org_id = db
    session.add(
        LineaJSC(
            organizacion_id=org_id,
            msisdn="2235474856",
            abonado="Cliente Telviso",
            plan="Móvil",
        )
    )
    session.commit()

    row = jsc.buscar_linea(session, org_id, "5492235474856")

    assert row is not None
    assert row.msisdn == "2235474856"
