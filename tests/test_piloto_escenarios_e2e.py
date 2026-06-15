"""Tests E2E de los 3 escenarios del piloto operativo imowi."""

from app.domain.demo_validacion import listar_escenarios_demo
from app.services.motor_conversacional import procesar_turno_conversacional
from tests.conftest import add_ticket


def _ticket_ex(ticket) -> dict:
    return {
        "id": ticket.id,
        "linea": ticket.linea,
        "estado": ticket.estado,
        "categoria": ticket.categoria,
    }


def _turno(db, org_id, session, historial, linea, sintoma, dispositivo, categoria, ticket_ex):
    return procesar_turno_conversacional(
        db,
        org_id,
        session,
        "operador@test",
        historial,
        {
            "linea": linea,
            "sintoma": sintoma,
            "dispositivo": dispositivo,
            "completo": True,
        },
        {"accion": "seguimiento_activo", "nivel": "N2", "crear_ticket": False},
        {"diagnostico": categoria, "categoria": categoria},
        None,
        ticket_existente=ticket_ex,
    )


def test_escenario_roaming_brasil_flujo(db):
    esc = next(e for e in listar_escenarios_demo() if e["id"] == "roaming-brasil")
    session, org_id = db
    ticket = add_ticket(
        session,
        org_id,
        id="JSC-PILOT-R1",
        linea=esc["linea"],
        categoria="Roaming",
        descripcion_falla="Sin datos en Brasil",
    )
    ticket_ex = _ticket_ex(ticket)
    hist = [{"rol": "usuario", "contenido": esc["mensaje_inicial"]}]

    r1 = _turno(
        session, org_id, "sess-pilot-r1", hist, esc["linea"],
        esc["mensaje_inicial"], esc["dispositivo"], "Roaming", ticket_ex,
    )
    assert r1["flujo_operativo"]["categoria"] == "roaming"
    assert r1["flujo_operativo"]["paso_id"] == "roaming_datos_moviles"
    assert r1["usar_ia"] is False

    resp1 = r1["respuesta_deterministica"] or r1["respuesta_sugerida"]
    hist.extend([
        {"rol": "asistente", "contenido": resp1},
        {"rol": "usuario", "contenido": "verificado"},
    ])
    r2 = _turno(
        session, org_id, "sess-pilot-r1", hist, esc["linea"],
        esc["mensaje_inicial"], esc["dispositivo"], "Roaming", ticket_ex,
    )
    assert r2["flujo_operativo"]["paso_id"] == "roaming_apn"


def test_escenario_datos_local_flujo(db):
    esc = next(e for e in listar_escenarios_demo() if e["id"] == "datos-local")
    session, org_id = db
    ticket = add_ticket(
        session,
        org_id,
        id="JSC-PILOT-D1",
        linea=esc["linea"],
        categoria="Datos",
        descripcion_falla="Sin datos móviles",
    )
    ticket_ex = _ticket_ex(ticket)
    hist = [{"rol": "usuario", "contenido": esc["mensaje_inicial"]}]

    r1 = _turno(
        session, org_id, "sess-pilot-d1", hist, esc["linea"],
        esc["mensaje_inicial"], esc["dispositivo"], "Datos", ticket_ex,
    )
    assert r1["flujo_operativo"]["categoria"] == "datos"
    assert r1["flujo_operativo"]["paso_id"] == "datos_moviles"
    assert "roaming" not in (r1["flujo_operativo"].get("categoria_label") or "").lower()


def test_escenario_senal_registro_red_flujo(db):
    esc = next(e for e in listar_escenarios_demo() if e["id"] == "senal-registro-red")
    session, org_id = db
    ticket = add_ticket(
        session,
        org_id,
        id="JSC-PILOT-S1",
        linea=esc["linea"],
        categoria="Señal",
        descripcion_falla="No registra en red",
    )
    ticket_ex = _ticket_ex(ticket)
    hist = [{"rol": "usuario", "contenido": esc["mensaje_inicial"]}]

    r1 = _turno(
        session, org_id, "sess-pilot-s1", hist, esc["linea"],
        esc["mensaje_inicial"], esc["dispositivo"], "Señal", ticket_ex,
    )
    assert r1["flujo_operativo"]["categoria"] == "senal"
    assert r1["flujo_operativo"]["paso_id"] == "senal_zona"
    resp = r1["respuesta_deterministica"] or r1["respuesta_sugerida"]
    assert "zona" in resp.lower()
