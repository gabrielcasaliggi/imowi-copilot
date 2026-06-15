"""Matriz piloto — escenarios clave de validación operativa."""

import pytest

from app.domain.flujos_operativos import detectar_categoria_flujo
from app.jsc.contract import mapear_ticket_a_jsc
from app.services.interprete_conversacional import (
    detectar_intencion_normalizada,
    extraer_hechos_normalizados,
)
from app.services.motor_conversacional import procesar_turno_conversacional
from tests.conftest import add_ticket


@pytest.mark.parametrize(
    "mensaje,categoria",
    [
        ("Cliente sin datos en Brasil, línea 2235551234", "roaming"),
        ("Sin datos en Uruguay, línea 2235402690", "roaming"),
        ("Cliente sin datos móviles en Güemes", "datos"),
        ("No registra en red, línea 2235560002", "senal"),
        ("Cambió el chip y no conecta", "sim"),
    ],
)
def test_matriz_categoria_flujo(mensaje, categoria):
    assert detectar_categoria_flujo(mensaje) == categoria


def test_matriz_llamadas_ok_datos_no():
    hechos = extraer_hechos_normalizados("puede llamar pero whatsapp no carga")
    assert hechos.get("llamadas_ok") is True
    assert hechos.get("datos_ok") is False


def test_matriz_consulta_ticket():
    r = detectar_intencion_normalizada("¿creaste el ticket?", tiene_ticket=True, hechos={})
    assert r["tipo"] == "estado_ticket"


def test_matriz_correccion_operador():
    r = detectar_intencion_normalizada(
        "no es así, el usuario sigue con problemas", tiene_ticket=True, hechos={}
    )
    assert r["tipo"] == "correccion"


def test_matriz_persistencia_post_n1(db):
    session, org_id = db
    hist = [
        {"rol": "usuario", "contenido": "Cliente sin datos en Brasil, linea 2235551234, Samsung A54"},
        {"rol": "asistente", "contenido": "Verificar datos móviles e itinerancia."},
        {"rol": "usuario", "contenido": "verificado"},
        {"rol": "asistente", "contenido": "Revisar APN roaming."},
        {"rol": "usuario", "contenido": "revisado"},
        {"rol": "asistente", "contenido": "Verificar roaming en JSC."},
        {"rol": "usuario", "contenido": "habilitado"},
        {"rol": "asistente", "contenido": "Reiniciar equipo."},
        {"rol": "usuario", "contenido": "hecho sigue igual"},
        {"rol": "asistente", "contenido": "Prueba de llamada."},
        {"rol": "usuario", "contenido": "no puede hacer llamadas y sigue igual"},
    ]
    r = procesar_turno_conversacional(
        session,
        org_id,
        "sess-matriz-p1",
        "operador@test",
        hist,
        {
            "linea": "2235551234",
            "sintoma": "Cliente sin datos en Brasil, linea 2235551234, Samsung A54",
            "dispositivo": "Samsung A54",
            "completo": True,
        },
        {"accion": "resolver_n1", "nivel": "N1", "crear_ticket": False},
        {"diagnostico": "Roaming internacional", "categoria": "Roaming"},
        None,
    )
    assert r["clasificacion_ajustada"]["accion"] == "crear_ticket_n2"
    assert r["clasificacion_ajustada"]["crear_ticket"] is True


def test_matriz_ticket_jsc_mapping(db):
    session, org_id = db
    t = add_ticket(
        session,
        org_id,
        id="JSC-MATRIZ-1",
        linea="2235551234",
        descripcion_falla="Sin datos roaming",
        categoria="Roaming",
    )
    payload = mapear_ticket_a_jsc(
        {
            "id": t.id,
            "linea": t.linea,
            "descripcion_falla": t.descripcion_falla,
            "nivel": "N2",
            "categoria": t.categoria,
            "creado_por": "batan",
            "motivo_escalamiento": "Persiste post N1",
            "acciones_n1_realizadas": "APN verificado",
            "destino": "imowi_noc",
        },
        org_nombre="Cooperativa Batán",
        org_id=org_id,
    )
    assert payload.msisdn == "2235551234"
    assert payload.nivel == "N2"
    assert payload.ticket_local_id == "JSC-MATRIZ-1"
    assert payload.cooperativa == "Cooperativa Batán"
