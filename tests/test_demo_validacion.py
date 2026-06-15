"""Tests API y dominio modo demo validación."""

from app.domain.demo_validacion import listar_escenarios_demo, obtener_escenario_demo
from app.estate import repository as repo


def test_escenarios_demo_tres_categorias():
    esc = listar_escenarios_demo()
    assert len(esc) == 3
    ids = {e["id"] for e in esc}
    assert ids == {"roaming-brasil", "datos-local", "senal-registro-red"}
    assert obtener_escenario_demo("inexistente") is None


def test_reset_demo_validacion_limpia_org(db):
    session, org_id = db
    from tests.conftest import add_ticket

    add_ticket(session, org_id, id="JSC-DEMO-1", linea="2235551234")
    repo.upsert_caso_conversacion(
        session,
        org_id,
        "sess-demo",
        usuario="operador@test",
        estado="guiando_resolucion",
        linea_msisdn="2235551234",
        datos_triaje={"linea": "2235551234"},
        clasificacion={},
    )
    res = repo.reset_demo_validacion(session, org_id, incluir_tickets=True)
    assert res["casos_eliminados"] >= 1
    assert res["tickets_eliminados"] >= 1
    assert not repo.list_tickets(session, org_id)
