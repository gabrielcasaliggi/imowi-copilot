"""Cierre persistente de tickets desde el pipeline conversacional."""

from app.agents.pipeline import _cerrar_ticket_si_corresponde
from app.estate import repository as repo
from tests.conftest import add_ticket


def test_pipeline_cierra_ticket_existente_si_caso_resuelto(db):
    session, org_id = db
    ticket = add_ticket(
        session,
        org_id,
        id="JSC-CLOSE-1",
        linea="2235551234",
        categoria="Roaming",
        descripcion_falla="Sin datos en roaming",
    )
    traces: list[str] = []

    ticket_dict, cerrado = _cerrar_ticket_si_corresponde(
        session,
        org_id,
        {
            "estado_conversacion": "caso_resuelto",
            "caso_conversacion": {
                "datos_triaje": {
                    "hechos": {
                        "datos_moviles_activos": True,
                        "apn_configurado": True,
                        "resuelto": True,
                    }
                }
            },
        },
        {"linea": ticket.linea, "sintoma": ticket.descripcion_falla},
        {"id": ticket.id, "estado": ticket.estado, "nivel": "N2"},
        traces,
    )

    actualizado = repo.get_ticket(session, org_id, ticket.id)
    assert cerrado is True
    assert ticket_dict is not None
    assert ticket_dict["estado"] == "Cerrado"
    assert actualizado is not None
    assert actualizado.estado == "Cerrado"
    assert actualizado.estado_sla == "Cerrado"
    assert "cerrado por resolución" in " ".join(traces)
