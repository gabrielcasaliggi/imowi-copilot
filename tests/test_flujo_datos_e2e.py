"""Test E2E del flujo datos móviles locales."""

from app.services.motor_conversacional import procesar_turno_conversacional
from tests.conftest import add_ticket


def _turno(db, org_id, historial, ticket_ex):
    return procesar_turno_conversacional(
        db,
        org_id,
        "sess-datos-e2e",
        "operador@test",
        historial,
        {
            "linea": "2235402690",
            "sintoma": "Cliente sin datos móviles en Güemes, Samsung A22.",
            "dispositivo": "Samsung A22",
            "completo": True,
        },
        {
            "accion": "seguimiento_activo",
            "nivel": "N1",
            "crear_ticket": False,
        },
        {"diagnostico": "Datos móviles", "categoria": "Datos"},
        None,
        ticket_existente=ticket_ex,
    )


def test_flujo_datos_avanza_sin_roaming(db):
    session, org_id = db
    ticket = add_ticket(
        session,
        org_id,
        id="JSC-2001",
        linea="2235402690",
        categoria="Datos",
        descripcion_falla="Sin datos móviles",
    )
    ticket_ex = {"id": ticket.id, "linea": ticket.linea, "estado": ticket.estado, "categoria": ticket.categoria}

    hist = [{"rol": "usuario", "contenido": "Cliente sin datos móviles en Güemes, Samsung A22."}]
    r1 = _turno(session, org_id, hist, ticket_ex)
    assert r1["flujo_operativo"]["categoria"] == "datos"
    assert r1["flujo_operativo"]["paso_id"] == "datos_moviles"

    resp1 = r1["respuesta_deterministica"] or r1["respuesta_sugerida"]
    hist.extend([
        {"rol": "asistente", "contenido": resp1},
        {"rol": "usuario", "contenido": "verificado"},
    ])
    r2 = _turno(session, org_id, hist, ticket_ex)
    assert r2["flujo_operativo"]["paso_id"] == "datos_apn"
