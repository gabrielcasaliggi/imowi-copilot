"""Tests de generación global de IDs de tickets."""

from app.config import TICKET_ID_PREFIX
from app.estate import repository as repo
from app.estate.models import Organization
from tests.conftest import add_ticket


def test_next_ticket_id_es_global_entre_organizaciones(db):
    session, org_id = db
    org2 = Organization(id="org-test-2", nombre="Coop Dos", slug="coop-dos")
    session.add(org2)
    session.commit()

    # Legacy JSC cuenta para la secuencia; el nuevo ID usa el prefijo actual.
    add_ticket(session, org_id, id="JSC-1001", linea="2235400001")

    ticket = repo.create_ticket(
        session,
        org2.id,
        linea="2235400002",
        dispositivo="Samsung A22",
        descripcion_falla="Sin datos en roaming",
        origen="Reporte Cliente",
        categoria="Roaming",
        creado_por="operador@test",
        nivel="N2",
        destino="imowi_noc",
    )

    assert ticket.id == f"{TICKET_ID_PREFIX}-1002"


def test_next_ticket_id_continua_desde_ibot(db):
    session, org_id = db
    add_ticket(session, org_id, id=f"{TICKET_ID_PREFIX}-1013", linea="2235400003")
    ticket = repo.create_ticket(
        session,
        org_id,
        linea="2235400004",
        dispositivo="Motorola",
        descripcion_falla="Sin señal",
        origen="Reporte Cliente",
        categoria="Señal",
        creado_por="operador@test",
        nivel="N2",
        destino="imowi_noc",
    )
    assert ticket.id == f"{TICKET_ID_PREFIX}-1014"
