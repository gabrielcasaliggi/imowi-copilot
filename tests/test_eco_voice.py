"""Tests de voz Eco + contexto abonado + historial chat."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.diagnostico_n1 import MIN_TURNOS_ANTES_ESCALAR
from app.services.eco_voice import (
    TEMPERATURE_N1,
    build_contexto_abonado,
    enrich_contexto_desde_integraciones,
    historial_canal_a_mensajes_chat,
    normalizar_monto_padron,
    parse_monto,
    sanitizar_montos_respuesta_cliente,
    system_prompt_eco_n1,
    texto_monto_ars,
)


def test_parametros_n1_basicos():
    assert TEMPERATURE_N1 == 0.4
    assert MIN_TURNOS_ANTES_ESCALAR == 4


def test_contexto_abonado_invitado():
    txt = build_contexto_abonado(None)
    assert "invitado" in txt.lower()
    assert "integrar NMS" in txt
    assert "integrar Fiserv" in txt


def test_contexto_abonado_identificado():
    abo = SimpleNamespace(
        nombre="María Pérez",
        dni="30111222",
        servicio="internet",
        plan="100Mb",
        estado="activo",
        deuda_monto="0",
        linea_msisdn="2235551234",
    )
    txt = build_contexto_abonado(abo)
    assert "identificado" in txt
    assert "María Pérez" in txt
    assert "30***222" in txt or "***" in txt
    assert "100Mb" in txt
    assert "servicios_contratados" in txt
    assert "internet fijo" in txt.lower()
    # Placeholders listos para conectar APIs
    assert "ont_estado" in txt
    assert "pago_qr_reciente" in txt
    assert "NUNCA dólares" not in txt
    assert "deuda_monto: 0" in txt


def test_montos_sin_anotaciones_prompt():
    leak = "0 (pesos argentinos / ARS — NUNCA dólares ni USD)"
    assert normalizar_monto_padron(leak) == "0"
    assert parse_monto(leak) == 0.0
    assert texto_monto_ars(leak) == "0,00 pesos"
    sucio = (
        "El saldo es 0.00 (pesos argentinos / ARS — NUNCA dólares ni USD) pesos."
    )
    limpio = sanitizar_montos_respuesta_cliente(sucio)
    assert "NUNCA" not in limpio
    assert "pesos argentinos / ARS" not in limpio
    assert "0.00" in limpio


def test_enrich_hook_vacio_hasta_integracion():
    empty = enrich_contexto_desde_integraciones(None)
    assert empty["ont_estado"] == ""
    assert empty["pago_qr_reciente"] == ""
    assert empty.get("pppoe_estado", "") == ""


def test_contexto_incluye_pppoe_placeholder():
    txt = build_contexto_abonado(None)
    assert "pppoe" in txt.lower()
    assert "uisp" in txt.lower()
    assert "integrar UISP" in txt


def test_contexto_con_extras_pppoe():
    abo = SimpleNamespace(
        nombre="María Pérez",
        dni="30111222",
        servicio="internet",
        plan="100Mb",
        estado="activo",
        deuda_monto="0",
        linea_msisdn="2235551234",
    )
    txt = build_contexto_abonado(
        abo,
        extras={
            "pppoe_resumen": "tipo=Fibra Optica; login=4640854; estado=conectado; ip=1.2.3.4",
            "uisp_resumen": "login=4640854; estado=en_linea; sitio=Torre Norte; senal=-58dBm",
        },
    )
    assert "conectado" in txt
    assert "1.2.3.4" in txt
    assert "4640854" in txt
    assert "en_linea" in txt
    assert "Torre Norte" in txt


def test_historial_a_chat_roles():
    hist = [
        {"autor": "cliente", "texto": "no anda internet"},
        {"autor": "bot", "texto": "¿Reiniciaste el router?"},
        {"autor": "cliente", "texto": "sí y sigue igual"},
    ]
    msgs = historial_canal_a_mensajes_chat(hist, max_msgs=14)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert "internet" in msgs[0]["content"]


def test_system_prompt_incluye_empatia_y_json():
    p = system_prompt_eco_n1(
        intencion="wifi",
        turnos=1,
        min_turnos_antes_escalar=4,
        contexto_abonado="CONTEXTO_ABONADO:\n- modo: invitado",
    )
    assert "frustrado" in p.lower() or "frustración" in p.lower() or "frustr" in p.lower()
    assert "JSON" in p
    assert "escalate" in p
    assert "CONTEXTO_ABONADO" in p
    assert "turno 2" in p


def test_doble_tema_y_prioridad():
    from app.domain.flujos_abonado import (
        clasificar_intencion,
        detectar_temas_duales,
        parece_consulta_nueva,
        pide_humano,
        resolver_prioridad_tema,
    )

    msg = "hola internet anda cada vez peor y encima me vino aumento en la fatura"
    assert set(detectar_temas_duales(msg)) == {"tecnico", "facturacion"}
    assert resolver_prioridad_tema("por el internet") == "tecnico"
    assert resolver_prioridad_tema("el aumento") == "facturacion"
    assert pide_humano("que me atiendan ya") is True
    assert pide_humano("quiero un asesor") is True

    # "factura de internet" NO es doble tema técnico+factura
    solo_factura = (
        "Queria saber cuanto me vino en mi factura de internet "
        "y cual es la web para abonarla?"
    )
    assert detectar_temas_duales(solo_factura) == ["facturacion"]
    assert clasificar_intencion(solo_factura) == "facturacion"

    # Negar técnico no es pedido de agente
    corr = "no es un problema tecnico, necesito saber cuanto me vino en la factura"
    assert pide_humano(corr) is False
    assert parece_consulta_nueva(corr) is True
    assert clasificar_intencion(corr) == "facturacion_estado_cuenta"
    assert pide_humano("mandame un tecnico") is True


def test_bloquea_handoff_y_pago_prematuro(monkeypatch):
    import json

    from app.services.diagnostico_n1 import diagnosticar_turno

    def _fake(*_a, **_k):
        return json.dumps(
            {
                "accion": "ask",
                "mensaje": (
                    "¿Te gustaría que un asesor te contacte por este medio "
                    "o preferís que te llamen?"
                ),
                "paso_cubierto": "x",
                "motivo": "ia",
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("app.llm.chat_completion", _fake)
    out = diagnosticar_turno(
        intencion="facturacion",
        checklist=[
            {"id": "identificar_cuenta", "pregunta": "¿Me pasás el DNI?"},
            {"id": "detalle_importe", "pregunta": "¿Qué monto ves?"},
        ],
        historial_mensajes=[],
        mensaje_cliente="la de este mes y son 5000 pesos mas",
        turnos_diagnostico=2,
        pasos_cubiertos=["triaje_motivo", "detalle_importe"],
    )
    assert out["accion"] == "ask"
    assert out["motivo"] == "bloqueado_handoff_prematuro"
    assert "asesor" not in (out.get("mensaje") or "").lower()
    assert "dni" in (out.get("mensaje") or "").lower() or "socio" in (out.get("mensaje") or "").lower()

    def _fake_pago(*_a, **_k):
        return json.dumps(
            {
                "accion": "ask",
                "mensaje": "¿Qué medio de pago utilizó y en qué fecha realizó el movimiento?",
                "paso_cubierto": "x",
                "motivo": "ia",
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("app.llm.chat_completion", _fake_pago)
    out2 = diagnosticar_turno(
        intencion="facturacion",
        checklist=[{"id": "identificar_cuenta", "pregunta": "¿DNI?"}],
        historial_mensajes=[],
        mensaje_cliente="que me atiendan ya",
        turnos_diagnostico=3,
        pasos_cubiertos=[],
        forzar_agente=True,
    )
    assert out2["accion"] == "escalate"
    assert out2["motivo"] == "pedido_humano"


def test_cierre_escalamiento_los_no_es_cortante():
    from app.services.canal_abonado import _mensaje_cierre_escalamiento
    from app.services.diagnostico_n1 import detectar_falla_optica_escalar

    assert (
        detectar_falla_optica_escalar(
            "tengo ua luz roja de los",
            [
                {
                    "autor": "bot",
                    "texto": "¿La luz PON está verde y la LOS apagada?",
                }
            ],
        )
        == "los_confirmada"
    )
    msg = _mensaje_cierre_escalamiento(
        "IBOT-1016",
        motivo="los_confirmada",
        mensaje_ia=(
            "La luz LOS en rojo indica que la fibra no está llegando bien a la cajita. "
            "Eso ya no lo resolvemos reiniciando: hace falta una visita técnica. "
            "Te derivo con un agente para coordinarla."
        ),
        nota_temas=" También dejé anotado el tema de aumento/factura para el agente.",
        intencion="internet_ftth",
    )
    assert "Avancé todo lo posible" not in msg
    assert "LOS" in msg or "fibra" in msg.lower()
    assert "IBOT-1016" in msg
    assert "visita" in msg.lower()
    assert "factura" in msg.lower() or "aumento" in msg.lower()


def test_cierre_escalamiento_tv_sensa_no_usa_plantilla_fibra():
    from app.services.canal_abonado import _mensaje_cierre_escalamiento

    msg = _mensaje_cierre_escalamiento(
        "IBOT-1022",
        motivo="los_confirmada",
        mensaje_ia=(
            "La luz LOS en rojo indica que la fibra no está llegando bien a la cajita. "
            "Eso ya no lo resolvemos reiniciando: hace falta una visita técnica. "
            "Te derivo con un agente para coordinarla."
        ),
        intencion="tv_sensa",
    )
    assert "LOS" not in msg
    assert "fibra" not in msg.lower()
    assert "cajita" not in msg.lower()
    assert "IBOT-1022" in msg
    assert "agente" in msg.lower()


def test_tv_sensa_no_escala_optica_con_historial_ftth(monkeypatch):
    """Regresión: error de cuenta Sensa no debe terminar en visita por LOS/fibra."""
    from app.domain.flujos_abonado import PLAYBOOKS
    from app.services.diagnostico_n1 import diagnosticar_turno

    def _fake_llm(*_a, **_k):
        return (
            '{"accion":"escalate","mensaje":"La luz LOS en rojo indica que la fibra '
            'no está llegando bien a la cajita.","paso_cubierto":"","motivo":"los_confirmada"}'
        )

    monkeypatch.setattr("app.llm.chat_completion", _fake_llm)
    historial = [
        {"autor": "bot", "texto": "Dale, vamos con Sensa. ¿Tenés internet en el equipo?"},
        {"autor": "cliente", "texto": "Si"},
        {"autor": "bot", "texto": "¿Desde qué equipo: Smart TV, celular, tablet o PC?"},
        {"autor": "cliente", "texto": "Smart tv"},
        {"autor": "bot", "texto": "¿Navegás internet en ese Smart TV?"},
        {"autor": "cliente", "texto": "Si"},
        {"autor": "bot", "texto": "¿La app de Sensa abre o tira error?"},
        {"autor": "cliente", "texto": "Un error"},
        {"autor": "bot", "texto": "¿Qué error te aparece?"},
        {"autor": "cliente", "texto": "Usuario incorrecto"},
        {
            "autor": "bot",
            "texto": (
                "¿Confirmás si usás el usuario y la contraseña que te enviamos "
                "por mail o por WhatsApp?"
            ),
        },
        # Historial contaminado de un tema FTTH previo en la misma conversación
        {"autor": "bot", "texto": "¿La luz PON está verde y la LOS apagada?"},
        {"autor": "cliente", "texto": "no, roja"},
    ]
    out = diagnosticar_turno(
        intencion="tv_sensa",
        checklist=PLAYBOOKS["tv_sensa"],
        historial_mensajes=historial,
        mensaje_cliente="Si",
        turnos_diagnostico=6,
        pasos_cubiertos=[
            "internet_en_disp",
            "dispositivo_sensa",
            "navega_en_disp",
            "app_sensa",
        ],
    )
    assert out["accion"] == "escalate"
    assert out["motivo"] == "bloqueado_optica_fuera_de_intencion"
    msg = (out.get("mensaje") or "").lower()
    assert "los" not in msg
    assert "fibra" not in msg
    assert "cajita" not in msg
    assert "sensa" in msg or "cuenta" in msg or "usuario" in msg


def test_aviso_deuda_elige_pago_o_tecnico():
    from types import SimpleNamespace

    from app.services.canal_abonado import (
        _elige_pago_o_tecnico,
        _intencion_es_tecnica,
        _texto_aviso_deuda_tecnico,
    )

    assert _intencion_es_tecnica("internet") is True
    assert _intencion_es_tecnica("internet_ftth") is True
    assert _intencion_es_tecnica("facturacion") is False
    assert _elige_pago_o_tecnico("quiero pagar") == "pago"
    assert _elige_pago_o_tecnico("seguimos con internet") == "tecnico"
    assert _elige_pago_o_tecnico("después pago, seguí con el diagnóstico") == "tecnico"
    assert (
        _elige_pago_o_tecnico(
            "la factura la pago despues ahora tengo un problema con el servicio"
        )
        == "tecnico"
    )
    assert _elige_pago_o_tecnico("la pago después, seguí con el móvil") == "tecnico"
    abo = SimpleNamespace(deuda_monto="86479.89")
    txt = _texto_aviso_deuda_tecnico(abo, "internet")
    assert "86.479,89" in txt or "86479" in txt
    assert "pesos" in txt.lower()
    assert "$" not in txt
    assert "pagar" in txt.lower()
    assert "diagnóstico" in txt.lower() or "diagnostico" in txt.lower()
    assert "de el " not in txt.lower()
    movil_txt = _texto_aviso_deuda_tecnico(abo, "movil")
    assert "diagnóstico del móvil" in movil_txt.lower() or "diagnostico del movil" in movil_txt.lower()
    assert "pesos" in movil_txt.lower()


def test_declara_solo_movil_sin_fijo():
    from app.domain.flujos_abonado import clasificar_intencion, declara_solo_movil_sin_fijo

    assert declara_solo_movil_sin_fijo("no tengo internet solo tengo imowi") is True
    assert declara_solo_movil_sin_fijo("no tengo internet, solo tengo telefonia movil") is True
    assert declara_solo_movil_sin_fijo("me quedé sin internet") is False
    assert declara_solo_movil_sin_fijo("no tengo internet") is False  # corte ambiguo
    assert declara_solo_movil_sin_fijo("no tengo internet", "movil") is False
    assert clasificar_intencion("no tengo internet solo tengo imowi", "internet") == "movil"
    assert clasificar_intencion("hola", "internet") == "general"
    assert clasificar_intencion("hola no me anda internet", "internet") == "internet"
    assert clasificar_intencion("hol", "movil") == "general"
    assert clasificar_intencion("no tengo internet", "internet") == "internet"
    assert clasificar_intencion("no tengo internet", "movil") == "general"
    assert clasificar_intencion("me quedé sin internet", "internet") == "internet"


def test_menu_consulta_segun_padron():
    from app.domain.flujos_abonado import (
        es_saludo_corto,
        parse_menu_servicio,
        parse_menu_tipo_consulta,
        texto_menu_consulta,
        texto_menu_tipo_consulta,
        texto_sin_internet_contratado,
    )

    assert es_saludo_corto("hol") is True
    assert es_saludo_corto("hola") is True
    from app.domain.flujos_abonado import es_saludo_solo

    assert es_saludo_solo("hol") is True
    assert es_saludo_solo("hola no me anda internet") is False
    movil = texto_menu_consulta("movil").lower()
    assert "telefonía móvil" in movil or "telefonia movil" in movil.replace("í", "i")
    assert "imowi" not in movil
    assert "internet," not in movil
    inet = texto_menu_consulta("internet").lower()
    assert "internet" in inet
    assert "imowi" not in inet
    ambos = texto_menu_consulta("ambos").lower()
    assert "internet" in ambos and "móvil" in ambos
    assert "imowi" not in ambos
    aviso = texto_sin_internet_contratado("movil").lower()
    assert "no figura internet" in aviso
    assert "telefonía" in aviso or "telefonia" in aviso.replace("í", "i")
    assert "imowi" not in aviso
    aviso2 = texto_sin_internet_contratado("movil", insistencia=2).lower()
    assert aviso2 != aviso
    assert "móvil" in aviso2 or "movil" in aviso2 or "agente" in aviso2

    tipo = texto_menu_tipo_consulta().lower()
    assert "técnico" in tipo or "tecnico" in tipo
    assert "comercial" in tipo
    assert "administrativo" in tipo or "facturación" in tipo or "facturacion" in tipo

    assert parse_menu_servicio("telefonía móvil") == "movil"
    assert parse_menu_servicio("factura") == "facturacion"
    assert parse_menu_servicio("internet fibra") == "internet"
    assert (
        parse_menu_servicio("Quiero dar de baja todo el internet la aplicación sensa")
        == "comercial"
    )
    assert parse_menu_tipo_consulta("técnico") == "tecnico"
    assert parse_menu_tipo_consulta("comercial") == "comercial"
    assert parse_menu_tipo_consulta("administrativo facturación") == "facturacion"

def test_aviso_deuda_no_interpreta_no_tengo_internet_como_diagnostico():
    from app.services.canal_abonado import _elige_pago_o_tecnico

    assert _elige_pago_o_tecnico("no tengo internet") is None
    assert _elige_pago_o_tecnico("seguimos con internet") == "tecnico"
    assert _elige_pago_o_tecnico("saque todo xq se fue demaciado mucho para pagar") is None
    assert _elige_pago_o_tecnico("quiero pagar") == "pago"


def test_pon_verde_no_pide_cable_amarillo(monkeypatch):
    from app.services.diagnostico_n1 import (
        detectar_enlace_optico_ok,
        diagnosticar_turno,
    )

    hist = [
        {
            "autor": "bot",
            "texto": (
                "¿la luz PON está en verde fijo y la luz LOS está apagada? "
                "Contame qué colores ves."
            ),
        }
    ]
    assert detectar_enlace_optico_ok("sisi, luz verde fija", hist) is True
    assert detectar_enlace_optico_ok("tengo luz roja de los", hist) is False

    def _boom(*_a, **_k):
        raise AssertionError("no debería llamar al LLM con PON verde clara")

    monkeypatch.setattr("app.llm.chat_completion", _boom)
    out = diagnosticar_turno(
        intencion="internet_ftth",
        checklist=[
            {"id": "luces_los", "pregunta": "¿PON?"},
            {"id": "cable_fibra", "pregunta": "¿Cable amarillo?"},
            {"id": "wifi_vs_cable_ftth", "pregunta": "¿Solo WiFi?"},
        ],
        historial_mensajes=hist,
        mensaje_cliente="sisi, luz verde fija",
        turnos_diagnostico=2,
        pasos_cubiertos=["reinicio_ont"],
    )
    assert out["accion"] == "ask"
    assert out["motivo"] == "pon_verde_enlace_ok"
    assert "amarillo" not in (out.get("mensaje") or "").lower()
    assert "anda internet" in (out.get("mensaje") or "").lower() or "servicio" in (
        out.get("mensaje") or ""
    ).lower()
