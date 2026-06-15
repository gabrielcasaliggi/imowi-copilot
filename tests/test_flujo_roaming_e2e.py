"""Test E2E del seguimiento roaming vía motor conversacional."""

from app.domain.conversacion import EstadoConversacion
from app.services.motor_conversacional import procesar_turno_conversacional
from tests.conftest import add_ticket


def _triaje(linea: str) -> dict:
    return {
        "linea": linea,
        "sintoma": "Cliente sin datos en Brasil, linea 2235482698, Samsung A22.",
        "dispositivo": "Samsung A22",
        "completo": True,
    }


def _clasif_seguimiento() -> dict:
    return {
        "accion": "seguimiento_activo",
        "nivel": "N2",
        "crear_ticket": False,
        "regla_aplicada": "triaje_completo_n2",
    }


def _diag() -> dict:
    return {"diagnostico": "Roaming internacional", "categoria": "Roaming"}


def _turno(db, org_id, historial, ticket_existente):
    return procesar_turno_conversacional(
        db,
        org_id,
        "sess-roaming-e2e",
        "operador@test",
        historial,
        _triaje("2235482698"),
        _clasif_seguimiento(),
        _diag(),
        None,
        ticket_existente=ticket_existente,
    )


def test_seguimiento_roaming_avanza_por_turnos(db):
    session, org_id = db
    ticket = add_ticket(
        session,
        org_id,
        id="JSC-1086",
        linea="2235482698",
        categoria="Roaming",
        descripcion_falla="Sin datos en Brasil",
    )
    ticket_ex = {
        "id": ticket.id,
        "linea": ticket.linea,
        "estado": ticket.estado,
        "categoria": ticket.categoria,
    }

    hist: list[dict] = [
        {"rol": "usuario", "contenido": "Cliente sin datos en Brasil, linea 2235482698, Samsung A22."},
    ]
    r1 = _turno(session, org_id, hist, ticket_ex)
    assert r1["estado_conversacion"] == EstadoConversacion.TICKET_CREADO.value
    assert r1["flujo_operativo"]["categoria"] == "roaming"
    assert r1["flujo_operativo"]["paso_id"] == "roaming_datos_moviles"
    resp1 = r1["respuesta_deterministica"] or r1["respuesta_sugerida"]
    assert "datos móviles" in resp1.lower()

    hist.extend([
        {"rol": "asistente", "contenido": resp1},
        {"rol": "usuario", "contenido": "verificado"},
    ])
    r2 = _turno(session, org_id, hist, ticket_ex)
    assert r2["flujo_operativo"]["paso_id"] == "roaming_apn"
    resp2 = r2["respuesta_deterministica"] or r2["respuesta_sugerida"]
    assert "APN" in resp2

    hist.extend([
        {"rol": "asistente", "contenido": resp2},
        {"rol": "usuario", "contenido": "ok"},
    ])
    r3 = _turno(session, org_id, hist, ticket_ex)
    assert r3["flujo_operativo"]["paso_id"] == "roaming_jsc"

    hist.extend([
        {"rol": "asistente", "contenido": r3["respuesta_deterministica"] or r3["respuesta_sugerida"]},
        {"rol": "usuario", "contenido": "no estaba activado el servicio de roaming"},
    ])
    r4 = _turno(session, org_id, hist, ticket_ex)
    assert r4["flujo_operativo"]["paso_id"] == "roaming_activar_jsc"
    resp4 = r4["respuesta_deterministica"] or r4["respuesta_sugerida"]
    assert "Activar roaming" in resp4
