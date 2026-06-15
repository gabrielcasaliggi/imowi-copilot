"""Tests de la base operativa temporal de anomalías."""

from datetime import UTC, datetime, timedelta

from app.estate import repository as repo
from tests.conftest import add_network_element


def test_anomalia_vencida_desaparece_de_la_base_operativa(db):
    session, org_id = db
    add_network_element(
        session,
        org_id,
        elemento_red="Celda-Test",
        ultima_actualizacion=datetime.now(UTC) - timedelta(minutes=45),
    )

    assert repo.telemetry_anomalies(session, org_id) == []

    [elemento] = repo.list_telemetry(session, org_id)
    assert elemento.estado_actual == "Normal"
    assert elemento.valor_actual == "OK"


def test_anomalia_vigente_sigue_activa(db):
    session, org_id = db
    add_network_element(
        session,
        org_id,
        elemento_red="Celda-Test",
        ultima_actualizacion=datetime.now(UTC) - timedelta(minutes=5),
    )

    anomalias = repo.telemetry_anomalies(session, org_id)
    assert len(anomalias) == 1
    assert anomalias[0].elemento_red == "Celda-Test"
