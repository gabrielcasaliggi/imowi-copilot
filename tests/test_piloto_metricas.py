"""Tests de métricas del piloto operativo."""

from app.services import piloto_metricas


def test_registrar_eventos_y_resumen(db):
    session, org_id = db

    piloto_metricas.registrar_evento_piloto(
        session,
        org_id,
        "escenario_iniciado",
        session_id="sess-m1",
        escenario_id="roaming-brasil",
        categoria="roaming",
        actor="operador@test",
    )
    piloto_metricas.registrar_evento_piloto(
        session,
        org_id,
        "paso_confirmado",
        session_id="sess-m1",
        escenario_id="roaming-brasil",
        categoria="roaming",
        paso_id="roaming_datos_moviles",
        actor="operador@test",
    )
    piloto_metricas.registrar_evento_piloto(
        session,
        org_id,
        "ticket_creado",
        session_id="sess-m1",
        escenario_id="roaming-brasil",
        ticket_id="JSC-9999",
        actor="operador@test",
    )

    resumen = piloto_metricas.resumen_metricas_piloto(session, org_id)
    assert resumen["total_eventos"] == 3
    assert resumen["por_tipo"]["escenario_iniciado"] == 1
    assert resumen["por_tipo"]["paso_confirmado"] == 1
    assert resumen["por_tipo"]["ticket_creado"] == 1
    assert resumen["por_escenario"]["roaming-brasil"]["iniciados"] == 1
    assert resumen["por_escenario"]["roaming-brasil"]["pasos"] == 1
    assert resumen["por_escenario"]["roaming-brasil"]["tickets"] == 1


def test_reset_limpia_eventos_piloto(db):
    session, org_id = db
    from app.estate import repository as repo

    piloto_metricas.registrar_evento_piloto(session, org_id, "reset_demo", actor="test")
    res = repo.reset_demo_validacion(session, org_id)
    assert res["eventos_piloto_eliminados"] == 1
    resumen = piloto_metricas.resumen_metricas_piloto(session, org_id)
    assert resumen["total_eventos"] == 0
