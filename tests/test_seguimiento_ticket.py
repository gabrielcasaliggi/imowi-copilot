"""Tests de registro automático de pasos en timeline del ticket."""

from app.estate import repository as repo
from app.services.seguimiento_ticket import registrar_avances_en_ticket, serializar_timeline
from tests.conftest import add_ticket


def test_registra_paso_confirmado_en_ticket(db):
    session, org_id = db
    ticket = add_ticket(session, org_id, id="JSC-9001", linea="2235402690", categoria="Roaming")
    hechos_prev: dict = {}
    hechos_new = {"datos_moviles_activos": True, "pasos_realizados": ["Datos móviles habilitados"]}
    datos = {"sintoma": "sin datos en Brasil", "linea": "2235402690"}

    traces, hechos_out = registrar_avances_en_ticket(
        session,
        org_id,
        ticket.id,
        hechos_prev=hechos_prev,
        hechos_new=hechos_new,
        datos_triaje=datos,
        ultimo_operador="verificado",
        actor="operador@test",
        flujo_operativo={"paso_id": "roaming_apn"},
        ticket_nivel="N2",
        ticket_estado="Abierto",
    )

    assert traces
    assert "roaming_datos_moviles" in hechos_out.get("pasos_ticket_registrados", [])
    timeline = serializar_timeline(session, org_id, ticket.id)
    assert any(e["tipo"] == "paso_operativo" for e in timeline)
    assert any("Datos e itinerancia" in e["titulo"] for e in timeline)


def test_no_duplica_paso_ya_registrado(db):
    session, org_id = db
    ticket = add_ticket(session, org_id, id="JSC-9002", linea="2235402690")
    hechos_prev = {"datos_moviles_activos": True, "pasos_ticket_registrados": ["roaming_datos_moviles"]}
    hechos_new = dict(hechos_prev)

    traces, _ = registrar_avances_en_ticket(
        session,
        org_id,
        ticket.id,
        hechos_prev=hechos_prev,
        hechos_new=hechos_new,
        datos_triaje={"sintoma": "sin datos en Brasil"},
        ultimo_operador="ok",
        actor="operador@test",
        flujo_operativo={"paso_id": "roaming_apn"},
    )
    assert traces == []
    assert len(serializar_timeline(session, org_id, ticket.id)) == 0


def test_registra_resumen_noc_en_escalamiento_senal(db):
    session, org_id = db
    ticket = add_ticket(session, org_id, id="JSC-9003", linea="2235402690", categoria="Señal")
    hechos_new = {
        "multiples_zonas": True,
        "llamadas_ok": False,
        "reinicio_o_modo_avion": True,
        "pasos_realizados": ["Afectación en varias zonas", "Llamadas verificadas: fallan"],
    }

    traces, hechos_out = registrar_avances_en_ticket(
        session,
        org_id,
        ticket.id,
        hechos_prev={},
        hechos_new=hechos_new,
        datos_triaje={"sintoma": "sin señal", "linea": "2235402690"},
        ultimo_operador="sigue igual",
        actor="operador@test",
        flujo_operativo={"paso_id": "senal_ticket_noc"},
        ticket_nivel="N2",
        ticket_estado="Abierto",
    )

    assert "senal_ticket_noc" in hechos_out.get("pasos_ticket_registrados", [])
    timeline = serializar_timeline(session, org_id, ticket.id)
    assert any(e["tipo"] == "resumen_noc" for e in timeline)
    updated = repo.get_ticket(session, org_id, ticket.id)
    assert updated is not None
    assert updated.estado == "En Revisión"
    assert updated.destino == "imowi_noc"
