"""Tests anti-deriva y fallbacks para el piloto operativo."""

from app.domain.conversacion import EstadoConversacion
from app.domain.flujos_operativos import evaluar_flujo
from app.services.motor_conversacional import debe_usar_ia, procesar_turno_conversacional
from app.services.respuestas_conversacion import respuesta_por_estado


def test_debe_usar_ia_false_con_flujo_activo():
    flujo = evaluar_flujo({}, "sin datos en Brasil")
    assert flujo["paso_mensaje"]
    usar = debe_usar_ia(
        EstadoConversacion.TICKET_CREADO,
        {"accion": "seguimiento_activo"},
        [{"rol": "usuario", "contenido": "ok"}],
        flujo,
    )
    assert usar is False


def test_debe_usar_ia_false_guiando_resolucion():
    usar = debe_usar_ia(
        EstadoConversacion.GUIANDO_RESOLUCION,
        {"accion": "resolver_n1"},
        [],
        {"paso_mensaje": "Verificar APN", "completado": False},
    )
    assert usar is False


def test_linea_sin_jsc_no_bloquea_flujo():
    resp = respuesta_por_estado(
        EstadoConversacion.GUIANDO_RESOLUCION,
        datos={"linea": "2299999999", "sintoma": "sin datos"},
        clasificacion={"accion": "resolver_n1"},
        diagnostico={"ficha_jsc": None},
        ticket=None,
        hechos={},
    )
    assert resp is not None
    assert "No encontré" not in resp
    assert "datos móviles" in resp.lower()


def test_flujo_activo_no_pide_dni():
    hechos = {}
    flujo = evaluar_flujo(hechos, "sin datos en Brasil, linea 2235551234")
    resp = respuesta_por_estado(
        EstadoConversacion.TICKET_CREADO,
        datos={"linea": "2235551234", "sintoma": "sin datos en Brasil"},
        clasificacion={"accion": "seguimiento_activo"},
        diagnostico={"ficha_jsc": {"msisdn": "2235551234"}},
        ticket={"id": "JSC-1"},
        hechos=hechos,
    )
    assert resp
    lower = resp.lower()
    assert "dni" not in lower
    assert "portabilidad" not in lower


def test_ticket_creado_se_informa_aunque_haya_flujo_pendiente():
    resp = respuesta_por_estado(
        EstadoConversacion.TICKET_CREADO,
        datos={"linea": "2235551234", "sintoma": "sin datos en Brasil"},
        clasificacion={"accion": "crear_ticket_n2", "nivel": "N2", "destino": "imowi_noc"},
        diagnostico={"ficha_jsc": {"msisdn": "2235551234"}},
        ticket={"id": "JSC-1002", "nivel": "N2", "destino": "imowi_noc"},
        hechos={},
    )

    assert resp is not None
    assert "Registré el ticket JSC-1002" in resp
    assert "N2" in resp


def test_pregunta_creaste_ticket_responde_estado_real():
    from app.services.intenciones_seguimiento import detectar_intencion_seguimiento

    hist = [
        {"rol": "usuario", "contenido": "Cliente sin datos en Brasil, linea 2235551234"},
        {"rol": "asistente", "contenido": "Listo. Registré el ticket JSC-1002 como N2 para imowi_noc."},
        {"rol": "usuario", "contenido": "creaste el ticket?"},
    ]
    intencion = detectar_intencion_seguimiento(
        hist,
        caso={"ticket_id": "JSC-1002"},
        ticket={"id": "JSC-1002", "estado": "Abierto", "nivel": "N2"},
    )
    resp = respuesta_por_estado(
        EstadoConversacion.TICKET_CREADO,
        datos={"linea": "2235551234", "sintoma": "sin datos en Brasil"},
        clasificacion={"accion": "estado_ticket"},
        diagnostico={"ficha_jsc": {"msisdn": "2235551234"}},
        ticket={"id": "JSC-1002", "estado": "Abierto", "nivel": "N2"},
        hechos={},
        intencion_seguimiento=intencion,
    )

    assert intencion["tipo"] == "estado_ticket"
    assert resp is not None
    assert "Sí, el ticket JSC-1002 ya quedó registrado" in resp
    assert "pruebas que confirmes quedan agregadas" in resp


def test_no_funciona_no_marca_datos_ok_al_responder_gracias():
    from app.services.intenciones_seguimiento import extraer_hechos_conversacion, detectar_intencion_seguimiento
    from app.services.respuestas_conversacion import respuesta_por_estado

    hist = [
        {"rol": "usuario", "contenido": "Cliente sin datos en Brasil, linea 2235551234"},
        {"rol": "asistente", "contenido": "Prueba de llamada"},
        {"rol": "usuario", "contenido": "llamada si, datos no"},
        {"rol": "asistente", "contenido": "Seguimiento NOC"},
        {"rol": "usuario", "contenido": "no es asi, el usuario sigue con problemas"},
        {"rol": "asistente", "contenido": "Datos y llamadas quedaron OK"},
        {"rol": "usuario", "contenido": "gracias"},
    ]
    hechos = extraer_hechos_conversacion(hist)
    assert hechos.get("datos_ok") is False
    intencion = detectar_intencion_seguimiento(
        hist,
        caso={"ticket_id": "JSC-1002"},
        ticket={"id": "JSC-1002", "estado": "Abierto", "nivel": "N2"},
    )
    resp = respuesta_por_estado(
        EstadoConversacion.TICKET_CREADO,
        datos={"linea": "2235551234", "sintoma": "sin datos en Brasil"},
        clasificacion={"accion": "agradecimiento"},
        diagnostico={},
        ticket={"id": "JSC-1002", "estado": "Abierto", "nivel": "N2"},
        hechos=hechos,
        intencion_seguimiento=intencion,
    )
    assert intencion["tipo"] == "agradecimiento"
    assert "sigue abierto" in resp.lower()
    assert "cerramos" not in resp.lower()


def test_correccion_persistencia_no_cierra_ticket():
    from app.services.intenciones_seguimiento import extraer_hechos_conversacion, detectar_intencion_seguimiento
    from app.services.respuestas_conversacion import respuesta_por_estado

    hist = [
        {"rol": "usuario", "contenido": "Cliente sin datos en Brasil, linea 2235551234"},
        {"rol": "asistente", "contenido": "Prueba de llamada"},
        {"rol": "usuario", "contenido": "llamada si, datos no"},
        {"rol": "asistente", "contenido": "¿Cerramos el ticket?"},
        {"rol": "usuario", "contenido": "no es asi, el usuario sigue con problemas"},
    ]
    hechos_prev = {
        "datos_moviles_activos": True,
        "apn_configurado": True,
        "roaming_verificado": True,
        "reinicio_o_modo_avion": True,
        "llamadas_ok": True,
        "categoria_flujo": "roaming",
    }
    hechos = extraer_hechos_conversacion(hist, hechos_prev)
    intencion = detectar_intencion_seguimiento(
        hist,
        caso={"ticket_id": "JSC-1002"},
        ticket={"id": "JSC-1002", "estado": "Abierto", "nivel": "N2"},
    )
    resp = respuesta_por_estado(
        EstadoConversacion.TICKET_CREADO,
        datos={"linea": "2235551234", "sintoma": "sin datos en Brasil"},
        clasificacion={"accion": "correccion"},
        diagnostico={},
        ticket={"id": "JSC-1002", "estado": "Abierto", "nivel": "N2"},
        hechos=hechos,
        intencion_seguimiento=intencion,
    )
    assert intencion["tipo"] == "correccion"
    assert "me adelanté" in resp.lower()
    assert "sigue" in resp.lower() or "mantengo" in resp.lower()
    assert "cerramos" not in resp.lower()


def test_reclamo_vago_luego_uruguay_avanza_roaming():
    from app.services.intenciones_seguimiento import extraer_hechos_conversacion
    from app.agents.triaje import extraer_datos

    hist = [
        {"rol": "usuario", "contenido": "tengo un problema con la linea 2235402692"},
        {"rol": "asistente", "contenido": "Confirmar zona, alcance del problema y si afecta señal, datos o solo llamadas."},
        {"rol": "usuario", "contenido": "no tiene datos saliendo de argentina, se encuentra en uruguay"},
    ]
    datos = extraer_datos(hist)
    hechos = extraer_hechos_conversacion(hist)
    flujo = evaluar_flujo(hechos, datos["sintoma"])

    assert hechos.get("alcance_confirmado") is True
    assert hechos.get("categoria_flujo") == "roaming"
    assert hechos.get("datos_ok") is False
    assert "uruguay" in datos["sintoma"].lower() or "argentina" in datos["sintoma"].lower()
    assert flujo["categoria"] == "roaming"
    assert flujo["paso_id"] == "roaming_datos_moviles"
    assert "Confirmar zona" not in (flujo.get("paso_mensaje") or "")


def test_categoria_roaming_no_deriva_a_datos():
    from app.services.intenciones_seguimiento import extraer_hechos_conversacion

    hist = [
        {"rol": "usuario", "contenido": "Cliente sin datos en Brasil, linea 2235551234, Samsung A54"},
        {"rol": "asistente", "contenido": "Verificar datos móviles e itinerancia."},
        {"rol": "usuario", "contenido": "verificado"},
        {"rol": "asistente", "contenido": 'Revisar el APN de datos para roaming (ej. "internet.coopbatan.ar") y probar navegación.'},
        {"rol": "usuario", "contenido": "no navega"},
        {"rol": "asistente", "contenido": "Verificar en JSC roaming internacional."},
        {"rol": "usuario", "contenido": "están habilitados"},
        {"rol": "asistente", "contenido": "Reiniciar el equipo o activar modo avión 10 segundos."},
        {"rol": "usuario", "contenido": "ya se hizo sigue igual"},
    ]
    h = extraer_hechos_conversacion(hist)
    flujo = evaluar_flujo(h, "Cliente sin datos en Brasil, linea 2235551234")
    assert h.get("categoria_flujo") == "roaming"
    assert h.get("reinicio_o_modo_avion") is True
    assert flujo["categoria"] == "roaming"
    assert flujo["paso_id"] == "roaming_llamada_prueba"


def test_revisado_y_no_navega_avanzan_apn():
    from app.services.intenciones_seguimiento import extraer_hechos_conversacion

    hist = [
        {"rol": "usuario", "contenido": "Cliente sin datos en Brasil, linea 2235551234"},
        {"rol": "asistente", "contenido": "Verificar datos móviles e itinerancia."},
        {"rol": "usuario", "contenido": "verificado"},
        {"rol": "asistente", "contenido": 'Revisar el APN de datos para roaming (ej. "internet.coopbatan.ar") y probar navegación.'},
        {"rol": "usuario", "contenido": "revisado"},
    ]
    h1 = extraer_hechos_conversacion(hist)
    assert h1.get("apn_configurado") is True
    flujo1 = evaluar_flujo(h1, "sin datos en Brasil")
    assert flujo1["paso_id"] == "roaming_jsc"

    hist.append({"rol": "asistente", "contenido": 'Revisar el APN de datos para roaming (ej. "internet.coopbatan.ar") y probar navegación.'})
    hist.append({"rol": "usuario", "contenido": "no navega"})
    h2 = extraer_hechos_conversacion(hist)
    assert h2.get("apn_configurado") is True
    assert h2.get("datos_ok") is False
    flujo2 = evaluar_flujo(h2, "sin datos en Brasil")
    assert flujo2["paso_id"] == "roaming_jsc"


def test_llamada_si_datos_no_avanza_roaming():
    from app.services.intenciones_seguimiento import extraer_hechos_conversacion

    hechos_prev = {
        "datos_moviles_activos": True,
        "apn_configurado": True,
        "roaming_verificado": True,
        "reinicio_o_modo_avion": True,
        "categoria_flujo": "roaming",
    }
    hist = [
        {"rol": "usuario", "contenido": "Cliente sin datos en Brasil, linea 2235551234, Samsung A54"},
        {"rol": "asistente", "contenido": "Verificar si el equipo registra red visitada y puede cursar una llamada de prueba."},
        {"rol": "usuario", "contenido": "llamada si, datos no"},
    ]
    h = extraer_hechos_conversacion(hist, hechos_prev)
    flujo = evaluar_flujo(h, "Cliente sin datos en Brasil, linea 2235551234")
    assert h.get("llamadas_ok") is True
    assert h.get("datos_ok") is False
    assert h.get("resuelto") is False
    assert flujo["paso_id"] == "roaming_cerrar_seguimiento"


def test_persistencia_post_n1_prepara_ticket_noc(db):
    session, org_id = db
    hist = [
        {"rol": "usuario", "contenido": "Cliente sin datos en Brasil, linea 2235551234, Samsung A54"},
        {"rol": "asistente", "contenido": "Verificar datos móviles e itinerancia."},
        {"rol": "usuario", "contenido": "verificado"},
        {"rol": "asistente", "contenido": 'Revisar el APN de datos para roaming (ej. "internet.coopbatan.ar") y probar navegación.'},
        {"rol": "usuario", "contenido": "revisado"},
        {"rol": "asistente", "contenido": "Verificar en JSC que la línea tenga roaming internacional y datos roaming habilitados."},
        {"rol": "usuario", "contenido": "están habilitados"},
        {"rol": "asistente", "contenido": "Reiniciar el equipo o activar modo avión 10 segundos para forzar nuevo registro."},
        {"rol": "usuario", "contenido": "ya se hizo sigue igual"},
        {"rol": "asistente", "contenido": "Verificar si el equipo registra red visitada y puede cursar una llamada de prueba."},
        {"rol": "usuario", "contenido": "no puede hacer llamadas y sigue igual"},
    ]

    r = procesar_turno_conversacional(
        session,
        org_id,
        "sess-persistencia-ticket",
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

    assert r["flujo_operativo"]["paso_id"] == "roaming_cerrar_seguimiento"
    assert r["clasificacion_ajustada"]["accion"] == "crear_ticket_n2"
    assert r["clasificacion_ajustada"]["crear_ticket"] is True
    assert r["clasificacion_ajustada"]["destino"] == "imowi_noc"
