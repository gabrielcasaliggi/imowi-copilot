"""Tests del motor de flujos operativos por categoría."""

from app.domain.flujos_operativos import (
    detectar_categoria_flujo,
    evaluar_flujo,
    resolver_paso_flujo,
    traza_flujo,
)
from app.services.intenciones_seguimiento import extraer_hechos_conversacion


def test_detecta_categoria_roaming():
    assert detectar_categoria_flujo("sin datos en Brasil") == "roaming"


def test_detecta_registro_en_red_como_senal():
    assert detectar_categoria_flujo("no se registra en la red") == "senal"


def test_sms_no_dispara_flujo_senal():
    sintoma = "No llegan mensajes de texto desde plataformas de mensajería como Apple"
    ev = evaluar_flujo({}, sintoma)
    assert ev["categoria"] == "sms"
    assert ev["categoria_label"] == "SMS / mensajería"
    assert ev["paso_id"] == "sms_alcance"
    assert "señal" not in (ev["paso_mensaje"] or "").lower()


def test_sms_preserva_categoria_aunque_operador_mencione_senal():
    sintoma = (
        "La línea 2234567890 no recibe mensajes de texto desde Apple. "
        "Entiendo que esto no debe a señal."
    )
    ev = evaluar_flujo({}, sintoma)
    assert ev["categoria"] == "sms"
    assert ev["paso_id"] == "sms_alcance"


def test_flujo_general_no_marca_completado_sin_paso():
    ev = evaluar_flujo({}, "consulta administrativa")
    assert ev["categoria"] == "general"
    assert ev["paso_id"] == "general_triaje"
    assert ev["completado"] is False


def test_flujo_roaming_orden_pasos():
    hechos = {}
    p1 = resolver_paso_flujo(hechos, "sin datos en Brasil")
    assert p1 is not None
    assert p1.id == "roaming_datos_moviles"

    hechos["datos_moviles_activos"] = True
    p2 = resolver_paso_flujo(hechos, "sin datos en Brasil")
    assert p2 is not None
    assert p2.id == "roaming_apn"

    hechos["apn_configurado"] = True
    p3 = resolver_paso_flujo(hechos, "sin datos en Brasil")
    assert p3 is not None
    assert p3.id == "roaming_jsc"


def test_flujo_roaming_hallazgo_jsc_inactivo():
    hechos = {
        "datos_moviles_activos": True,
        "apn_configurado": True,
        "roaming_verificado": True,
        "roaming_jsc_inactivo": True,
    }
    paso = resolver_paso_flujo(hechos, "sin datos en Brasil")
    assert paso is not None
    assert paso.id == "roaming_activar_jsc"


def test_evaluar_flujo_incluye_hechos_resumen():
    hechos = {"datos_moviles_activos": True, "apn_configurado": True}
    ev = evaluar_flujo(hechos, "sin datos en Brasil")
    assert ev["categoria"] == "roaming"
    assert ev["paso_id"] == "roaming_jsc"
    assert ev["paso_label"] == "3. Roaming en JSC"
    assert ev["categoria_label"] == "Roaming internacional"
    assert any("datos_móviles=ok" in h for h in ev["hechos_resumen"])
    assert "📋 [Flujo Operativo]" in traza_flujo(hechos, "sin datos en Brasil")


def test_replay_historial_alinea_con_flujo():
    hist = [
        {"rol": "usuario", "contenido": "Cliente sin datos en Brasil, linea 2235482698, Samsung A22."},
        {"rol": "asistente", "contenido": "Verificar que datos móviles e itinerancia de datos estén activos en el equipo."},
        {"rol": "usuario", "contenido": "verificado"},
        {"rol": "asistente", "contenido": 'Revisar el APN de datos para roaming (ej. "internet.coopbatan.ar") y probar navegación.'},
        {"rol": "usuario", "contenido": "ok"},
    ]
    hechos = extraer_hechos_conversacion(hist, {})
    ev = evaluar_flujo(hechos, "Cliente sin datos en Brasil")
    assert ev["paso_id"] == "roaming_jsc"


def test_flujo_senal_orden_operativo():
    hechos = {}
    p1 = resolver_paso_flujo(hechos, "cliente sin señal en la línea")
    assert p1 is not None
    assert p1.id == "senal_zona"

    hechos["multiples_zonas"] = True
    hechos["zona_unica"] = False
    p2 = resolver_paso_flujo(hechos, "cliente sin señal en la línea")
    assert p2 is not None
    assert p2.id == "senal_llamadas"

    hechos["llamadas_ok"] = False
    p3 = resolver_paso_flujo(hechos, "cliente sin señal en la línea")
    assert p3 is not None
    assert p3.id == "senal_reinicio"

    hechos["reinicio_o_modo_avion"] = True
    p4 = resolver_paso_flujo(hechos, "cliente sin señal en la línea")
    assert p4 is not None
    assert p4.id == "senal_ticket_noc"


def test_replay_historial_senal_varias_zonas():
    hist = [
        {"rol": "usuario", "contenido": "Cliente sin señal, línea 2235402690, Samsung A22."},
        {"rol": "asistente", "contenido": "Confirmar si el problema de señal ocurre en una sola zona o en varias ubicaciones."},
        {"rol": "usuario", "contenido": "en varias zonas"},
        {"rol": "asistente", "contenido": "Verificar si el cliente puede hacer y recibir llamadas de prueba."},
        {"rol": "usuario", "contenido": "no puede hacer llamadas"},
    ]
    hechos = extraer_hechos_conversacion(hist, {})
    ev = evaluar_flujo(hechos, "Cliente sin señal")
    assert ev["paso_id"] == "senal_reinicio"
    assert "varias_zonas=ok" in ev["hechos_resumen"]
    assert "llamadas=falla" in ev["hechos_resumen"]
