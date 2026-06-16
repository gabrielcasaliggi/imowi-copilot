"""Tests del motor conversacional N1."""

from app.domain.conversacion import EstadoConversacion, usuario_confirmo_resolucion, usuario_confirmo_ticket
from app.services.motor_conversacional import (
    ajustar_clasificacion_por_estado,
    debe_usar_ia,
    detectar_linea_cambiada,
    procesar_turno_conversacional,
)
from tests.conftest import add_ticket


def test_no_crea_ticket_sin_confirmacion():
    clasif = {
        "accion": "crear_ticket_n1",
        "nivel": "N1",
        "regla_aplicada": "ticket_n1_demo",
        "pasos_n1": [],
    }
    caso = {"estado": EstadoConversacion.GUIANDO_RESOLUCION.value, "kb_agotada": False}
    historial = [{"rol": "usuario", "contenido": "cliente sin datos línea 2235402690 samsung a22"}]
    out = ajustar_clasificacion_por_estado(clasif, caso, historial)
    assert out["crear_ticket"] is False


def test_crea_ticket_con_escalamiento():
    clasif = {
        "accion": "crear_ticket_n1",
        "nivel": "N1",
        "regla_aplicada": "ticket_n1_demo",
    }
    caso = {"estado": EstadoConversacion.ESPERANDO_CONFIRMACION.value}
    historial = [{"rol": "usuario", "contenido": "sigue igual, generar ticket por favor"}]
    out = ajustar_clasificacion_por_estado(clasif, caso, historial)
    assert out["crear_ticket"] is True


def test_anomalia_correlacionada_crea_ticket_siempre():
    clasif = {
        "accion": "crear_ticket_n2",
        "regla_aplicada": "anomalia_red_correlacionada",
    }
    out = ajustar_clasificacion_por_estado(clasif, {}, [])
    assert out["crear_ticket"] is True


def test_confirmacion_resolucion_cierra_sin_ticket():
    clasif = {"accion": "resolver_n1", "pasos_n1": ["Paso 1"]}
    historial = [
        {"rol": "usuario", "contenido": "probé el paso"},
        {"rol": "usuario", "contenido": "ya funciona, gracias"},
    ]
    assert usuario_confirmo_resolucion(historial)
    out = ajustar_clasificacion_por_estado(clasif, {}, historial)
    assert out["accion"] == "resolver_n1"
    assert out["crear_ticket"] is False


def test_no_usa_ia_en_recolectando_datos():
    assert debe_usar_ia(
        EstadoConversacion.RECOLECTANDO_DATOS,
        {"accion": "pedir_datos", "datos_faltantes": ["linea"]},
        [],
    ) is False


def test_usa_ia_solo_sin_flujo_operativo():
    flujo = {
        "categoria": "senal",
        "paso_id": "senal_zona",
        "paso_mensaje": "Confirmar si el problema ocurre en una sola zona o en varias ubicaciones.",
        "completado": False,
    }
    hist_largo = [{"rol": "usuario", "contenido": f"mensaje {i}"} for i in range(8)]
    assert debe_usar_ia(
        EstadoConversacion.GUIANDO_RESOLUCION,
        {"accion": "resolver_n1", "pasos_n1": ["Verificar APN"]},
        hist_largo,
        flujo,
    ) is False
    assert debe_usar_ia(
        EstadoConversacion.GUIANDO_RESOLUCION,
        {"accion": "resolver_n1", "pasos_n1": ["Verificar APN"]},
        hist_largo + [{"rol": "usuario", "contenido": "¿qué hago ahora?"}],
        flujo,
    ) is True
    assert debe_usar_ia(
        EstadoConversacion.BUSCANDO_KB,
        {"accion": "resolver_n1"},
        hist_largo,
        None,
    ) is True
    assert debe_usar_ia(
        EstadoConversacion.TICKET_CREADO,
        {"accion": "seguimiento_activo", "crear_ticket": False},
        [{"rol": "usuario", "contenido": "ya lo verificamos"}],
        flujo,
    ) is False
    assert debe_usar_ia(
        EstadoConversacion.TICKET_CREADO,
        {"accion": "estado_ticket", "crear_ticket": False},
        [{"rol": "usuario", "contenido": "creaste el ticket?"}],
        {"paso_id": "roaming_cerrar_seguimiento", "completado": True},
    ) is True
    assert debe_usar_ia(
        EstadoConversacion.TICKET_CREADO,
        {"accion": "seguimiento_activo", "crear_ticket": False},
        [{"rol": "usuario", "contenido": "creaste el ticket?"}],
        {"paso_id": "roaming_cerrar_seguimiento", "completado": True},
    ) is True


def test_confirmacion_ticket_detectada():
    historial = [{"rol": "usuario", "contenido": "sí, confirmo que registres el ticket"}]
    assert usuario_confirmo_ticket(historial)


def test_accion_operador_confirmar_ticket():
    clasif = {"accion": "crear_ticket_n1", "regla_aplicada": "ticket_n1_demo"}
    out = ajustar_clasificacion_por_estado(
        clasif,
        {"estado": EstadoConversacion.ESPERANDO_CONFIRMACION.value},
        [],
        accion_operador="confirmar_ticket",
    )
    assert out["crear_ticket"] is True


def test_accion_operador_caso_resuelto():
    clasif = {"accion": "crear_ticket_n1", "regla_aplicada": "ticket_n1_demo"}
    out = ajustar_clasificacion_por_estado(
        clasif,
        {"estado": EstadoConversacion.GUIANDO_RESOLUCION.value},
        [],
        accion_operador="caso_resuelto",
    )
    assert out["accion"] == "resolver_n1"
    assert out["crear_ticket"] is False


def test_ticket_existente_evita_duplicado():
    clasif = {"accion": "crear_ticket_n1", "regla_aplicada": "ticket_n1_demo"}
    ticket_existente = {"id": "TK-001", "linea": "2235402690", "estado": "Abierto"}
    out = ajustar_clasificacion_por_estado(
        clasif,
        {"estado": EstadoConversacion.ESPERANDO_CONFIRMACION.value},
        [{"rol": "usuario", "contenido": "sí, crear ticket"}],
        ticket_existente=ticket_existente,
    )
    assert out["crear_ticket"] is False
    assert out["ticket_existente_id"] == "TK-001"


def test_detectar_linea_cambiada():
    caso_prev = {"id": "caso-1", "linea_msisdn": "2235402690"}
    datos = {"linea": "2235551234"}
    cambio = detectar_linea_cambiada(caso_prev, datos, None)
    assert cambio is not None
    assert cambio["anterior"] == "2235402690"
    assert cambio["nueva"] == "2235551234"


def test_nuevo_reclamo_no_marca_linea_cambiada():
    caso_prev = {"id": "caso-1", "linea_msisdn": "2235402690"}
    datos = {"linea": "2235551234"}
    assert detectar_linea_cambiada(caso_prev, datos, "nuevo_reclamo") is None


def _triaje(linea: str) -> dict:
    return {
        "linea": linea,
        "sintoma": "Sin datos móviles",
        "dispositivo": "Samsung A22",
        "completo": True,
    }


def _clasif_n1() -> dict:
    return {
        "accion": "crear_ticket_n1",
        "nivel": "N1",
        "regla_aplicada": "ticket_n1_demo",
        "pasos_n1": [],
    }


def test_dos_lineas_crean_casos_distintos(db):
    session, org_id = db
    clasif = _clasif_n1()
    diag = {"diagnostico": "Caso aislado", "categoria": "General"}

    r1 = procesar_turno_conversacional(
        session,
        org_id,
        "sess-1",
        "operador",
        [{"rol": "usuario", "contenido": "línea 2235402690 sin datos"}],
        _triaje("2235402690"),
        clasif,
        diag,
        None,
    )
    r2 = procesar_turno_conversacional(
        session,
        org_id,
        "sess-1",
        "operador",
        [{"rol": "usuario", "contenido": "línea 2235551234 sin datos"}],
        _triaje("2235551234"),
        clasif,
        diag,
        None,
        accion_operador="nuevo_reclamo",
    )

    assert r1["caso_conversacion"]["linea_msisdn"] == "2235402690"
    assert r2["caso_conversacion"]["linea_msisdn"] == "2235551234"
    assert r1["caso_id"] != r2["caso_id"]


def test_linea_cambiada_en_misma_sesion(db):
    session, org_id = db
    clasif = _clasif_n1()
    diag = {"diagnostico": "Caso aislado", "categoria": "General"}

    procesar_turno_conversacional(
        session,
        org_id,
        "sess-2",
        "operador",
        [{"rol": "usuario", "contenido": "línea 2235402690"}],
        _triaje("2235402690"),
        clasif,
        diag,
        None,
    )

    r = procesar_turno_conversacional(
        session,
        org_id,
        "sess-2",
        "operador",
        [{"rol": "usuario", "contenido": "ahora línea 2235551234"}],
        _triaje("2235551234"),
        clasif,
        diag,
        None,
    )

    assert r["linea_cambiada"] is not None
    assert r["linea_cambiada"]["nueva"] == "2235551234"
    assert "nuevo reclamo" in r["respuesta_deterministica"].lower()


def test_procesar_turno_con_ticket_existente(db):
    session, org_id = db
    ticket = add_ticket(session, org_id, linea="2235402690", categoria="General")
    ticket_existente = {
        "id": ticket.id,
        "linea": ticket.linea,
        "estado": ticket.estado,
        "categoria": ticket.categoria,
    }

    r = procesar_turno_conversacional(
        session,
        org_id,
        "sess-3",
        "operador",
        [{"rol": "usuario", "contenido": "sigue sin datos"}],
        _triaje("2235402690"),
        _clasif_n1(),
        {"diagnostico": "Caso aislado", "categoria": "General"},
        None,
        ticket_existente=ticket_existente,
    )

    assert r["clasificacion_ajustada"]["crear_ticket"] is False
    assert r["estado_conversacion"] == EstadoConversacion.TICKET_CREADO.value


def test_sms_crea_ticket_carrier_con_confirmacion_persistencia(db):
    session, org_id = db
    hist = [
        {
            "rol": "usuario",
            "contenido": (
                "El cliente con linea 2233567656 tiene problemas con los sms "
                "que provienen de plataformas como membresias ejemplo netflix apple"
            ),
        },
        {
            "rol": "asistente",
            "contenido": "Verificar en JSC que la línea esté activa, sin bloqueo de servicios y con mensajería habilitada.",
        },
        {"rol": "usuario", "contenido": "si ya lo hicimos y no hay bloqueos"},
        {
            "rol": "asistente",
            "contenido": "Escalar a carrier/proveedor con línea, ejemplos de remitentes, horarios aproximados y tipo de SMS afectado.",
        },
        {"rol": "usuario", "contenido": "podes realizar el ticket ?"},
        {
            "rol": "asistente",
            "contenido": (
                "Para crear un ticket, necesito confirmar que el problema persiste después de las verificaciones realizadas."
            ),
        },
        {"rol": "usuario", "contenido": "si los problemas persisten"},
    ]

    r = procesar_turno_conversacional(
        session,
        org_id,
        "sess-sms-ticket",
        "operador",
        hist,
        {
            "linea": "2233567656",
            "sintoma": hist[0]["contenido"],
            "dispositivo": "",
            "completo": True,
        },
        {"accion": "resolver_n1", "nivel": "N1", "crear_ticket": False},
        {"diagnostico": "SMS / A2P", "categoria": "SMS / A2P"},
        None,
    )

    assert r["flujo_operativo"]["categoria"] == "sms"
    assert r["clasificacion_ajustada"]["accion"] == "crear_ticket_n2"
    assert r["clasificacion_ajustada"]["crear_ticket"] is True
    assert r["clasificacion_ajustada"]["destino"] == "carrier"
    assert r["estado_conversacion"] == EstadoConversacion.TICKET_CREADO.value
