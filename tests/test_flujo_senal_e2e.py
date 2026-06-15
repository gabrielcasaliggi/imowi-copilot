"""Test E2E del flujo señal/cobertura vía motor conversacional."""

from app.services.motor_conversacional import procesar_turno_conversacional
from tests.conftest import add_ticket


def _turno(db, org_id, historial, ticket_ex):
    return procesar_turno_conversacional(
        db,
        org_id,
        "sess-senal-e2e",
        "operador@test",
        historial,
        {
            "linea": "2235402690",
            "sintoma": "Cliente sin señal en la línea, Samsung A22.",
            "dispositivo": "Samsung A22",
            "completo": True,
        },
        {
            "accion": "seguimiento_activo",
            "nivel": "N2",
            "crear_ticket": False,
        },
        {"diagnostico": "Sin señal", "categoria": "Señal"},
        None,
        ticket_existente=ticket_ex,
    )


def test_flujo_senal_avanza_hasta_noc(db):
    session, org_id = db
    ticket = add_ticket(
        session,
        org_id,
        id="JSC-3001",
        linea="2235402690",
        categoria="Señal",
        descripcion_falla="Sin señal",
    )
    ticket_ex = {
        "id": ticket.id,
        "linea": ticket.linea,
        "estado": ticket.estado,
        "categoria": ticket.categoria,
    }

    hist = [{"rol": "usuario", "contenido": "Cliente sin señal en la línea, Samsung A22."}]
    r1 = _turno(session, org_id, hist, ticket_ex)
    assert r1["flujo_operativo"]["categoria"] == "senal"
    assert r1["flujo_operativo"]["paso_id"] == "senal_zona"
    resp1 = r1["respuesta_deterministica"] or r1["respuesta_sugerida"]

    hist.extend([
        {"rol": "asistente", "contenido": resp1},
        {"rol": "usuario", "contenido": "en varias zonas"},
    ])
    r2 = _turno(session, org_id, hist, ticket_ex)
    assert r2["flujo_operativo"]["paso_id"] == "senal_llamadas"
    resp2 = r2["respuesta_deterministica"] or r2["respuesta_sugerida"]

    hist.extend([
        {"rol": "asistente", "contenido": resp2},
        {"rol": "usuario", "contenido": "no puede hacer llamadas"},
    ])
    r3 = _turno(session, org_id, hist, ticket_ex)
    assert r3["flujo_operativo"]["paso_id"] == "senal_reinicio"
    resp3 = r3["respuesta_deterministica"] or r3["respuesta_sugerida"]

    hist.extend([
        {"rol": "asistente", "contenido": resp3},
        {"rol": "usuario", "contenido": "hecho y sigue igual"},
    ])
    r4 = _turno(session, org_id, hist, ticket_ex)
    assert r4["flujo_operativo"]["paso_id"] == "senal_ticket_noc"
    resp4 = r4["respuesta_deterministica"] or r4["respuesta_sugerida"]
    assert "NOC" in resp4
