"""Tests para síntoma 'no se registra en la red' con ticket previo."""

from app.domain.flujos_operativos import evaluar_flujo, sintoma_cambio_categoria
from app.services.intenciones_seguimiento import detectar_intencion_seguimiento
from app.services.motor_conversacional import procesar_turno_conversacional
from app.services.respuestas_conversacion import respuesta_por_estado
from app.domain.conversacion import EstadoConversacion
from tests.conftest import add_ticket


def test_sintoma_registro_red_es_senal():
    ev = evaluar_flujo({}, "linea 2235482698, síntoma no se registra en la red, modelo a22")
    assert ev["categoria"] == "senal"
    assert ev["paso_id"] == "senal_zona"
    assert ev["completado"] is False


def test_cambio_de_sintoma_resetea_categoria():
    assert sintoma_cambio_categoria("sin datos en Brasil", "no se registra en la red") is True


def test_nuevo_reclamo_no_fuerza_seguimiento_activo():
    hist = [
        {"rol": "usuario", "contenido": "sin datos en Brasil"},
        {"rol": "asistente", "contenido": "verificar apn"},
        {"rol": "usuario", "contenido": "linea 2235482698, síntoma no se registra en la red, modelo a22"},
    ]
    caso = {"ticket_id": "JSC-1006", "datos_triaje": {"sintoma": "sin datos en Brasil"}}
    r = detectar_intencion_seguimiento(hist, caso=caso, ticket={"id": "JSC-1006"})
    assert r["tipo"] == "continuar"


def test_respuesta_registro_red_pide_zona(db):
    session, org_id = db
    ticket = add_ticket(
        session,
        org_id,
        id="JSC-1006",
        linea="2235482698",
        categoria="Señal",
        descripcion_falla="no se registra en la red",
    )
    ticket_ex = {"id": ticket.id, "linea": ticket.linea, "estado": "Abierto", "categoria": "Señal"}
    hist = [{"rol": "usuario", "contenido": "linea 2235482698, síntoma no se registra en la red, modelo a22"}]

    r = procesar_turno_conversacional(
        session,
        org_id,
        "sess-registro-red",
        "operador@test",
        hist,
        {
            "linea": "2235482698",
            "sintoma": "linea 2235482698, síntoma no se registra en la red, modelo a22",
            "dispositivo": "A22",
            "completo": True,
            "hechos": {},
        },
        {"accion": "resolver_n1", "nivel": "N2", "crear_ticket": False},
        {"diagnostico": "Sin registro en red", "categoria": "Señal"},
        None,
        ticket_existente=ticket_ex,
    )

    resp = r["respuesta_deterministica"] or r["respuesta_sugerida"]
    assert r["flujo_operativo"]["categoria"] == "senal"
    assert "zona" in resp.lower()
    assert "NOC" not in resp or "zona" in resp.lower()
