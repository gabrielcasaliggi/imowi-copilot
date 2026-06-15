"""Escenarios precargados para validación con imowi — guion operativo reproducible."""

from __future__ import annotations

from typing import Any

ESCENARIOS_DEMO: list[dict[str, Any]] = [
    {
        "id": "roaming-brasil",
        "titulo": "Roaming Brasil",
        "descripcion": "Cliente sin datos en el exterior; flujo roaming de 7 pasos.",
        "linea": "2235551234",
        "dispositivo": "Samsung A54",
        "cooperativa": "coop-batan",
        "categoria_flujo": "roaming",
        "mensaje_inicial": "Cliente sin datos en Brasil, línea 2235551234, Samsung A54",
        "turnos_guion": [
            {
                "orden": 1,
                "operador": "Cliente sin datos en Brasil, línea 2235551234, Samsung A54",
                "esperado": "Ficha JSC, categoría Roaming, paso 1 datos/itinerancia",
                "verificar": ["ficha_jsc", "flujo_roaming", "paso_datos_moviles"],
            },
            {
                "orden": 2,
                "operador": "verificado",
                "esperado": "Paso 2 — APN de roaming",
                "verificar": ["paso_apn"],
            },
            {
                "orden": 3,
                "operador": "ok",
                "esperado": "Paso 3 — roaming en JSC",
                "verificar": ["paso_jsc"],
            },
            {
                "orden": 4,
                "operador": "no estaba activado el servicio de roaming",
                "esperado": "Paso 4 — activar roaming en JSC",
                "verificar": ["paso_activar_jsc"],
            },
            {
                "orden": 5,
                "operador": "activado en jsc",
                "esperado": "Paso 5 — reinicio / modo avión",
                "verificar": ["paso_reinicio"],
            },
            {
                "orden": 6,
                "operador": "hecho",
                "esperado": "Paso 6 — prueba de llamada",
                "verificar": ["paso_llamada"],
            },
            {
                "orden": 7,
                "operador": "Registrar ticket NOC",
                "esperado": "Ticket JSC con timeline de pasos operativos",
                "verificar": ["ticket_noc", "timeline_pasos"],
                "accion": "forzar_escalamiento",
            },
        ],
        "checklist_imowi": [
            "¿Los pasos del flujo coinciden con el playbook de roaming?",
            "¿La ficha JSC aporta datos útiles (APN, roaming)?",
            "¿El timeline del ticket refleja cada paso confirmado?",
            "¿El resumen NOC es accionable para el ingeniero?",
        ],
    },
    {
        "id": "datos-local",
        "titulo": "Sin datos local",
        "descripcion": "Datos móviles en zona local; flujo datos de 6 pasos.",
        "linea": "2235560001",
        "dispositivo": "Samsung A22",
        "cooperativa": "coop-batan",
        "categoria_flujo": "datos",
        "mensaje_inicial": "Cliente sin datos móviles en Güemes, línea 2235560001, Samsung A22",
        "turnos_guion": [
            {
                "orden": 1,
                "operador": "Cliente sin datos móviles en Güemes, línea 2235560001, Samsung A22",
                "esperado": "Categoría Datos, paso 1 datos móviles activos",
                "verificar": ["flujo_datos", "paso_datos_moviles"],
            },
            {
                "orden": 2,
                "operador": "verificado",
                "esperado": "Paso 2 — configurar APN",
                "verificar": ["paso_apn"],
            },
            {
                "orden": 3,
                "operador": "apn correcto",
                "esperado": "Paso 3 — reinicio de red",
                "verificar": ["paso_reinicio"],
            },
            {
                "orden": 4,
                "operador": "reiniciado",
                "esperado": "Paso 4 — prueba de llamadas",
                "verificar": ["paso_llamadas"],
            },
            {
                "orden": 5,
                "operador": "llamadas ok pero sin datos",
                "esperado": "Paso 5 — descarte SIM",
                "verificar": ["paso_sim"],
            },
            {
                "orden": 6,
                "operador": "Registrar ticket NOC",
                "esperado": "Escalamiento con evidencia acumulada",
                "verificar": ["ticket_noc", "timeline_pasos"],
                "accion": "forzar_escalamiento",
            },
        ],
        "checklist_imowi": [
            "¿El flujo no mezcla pasos de roaming?",
            "¿Se detecta correctamente el síntoma local vs itinerancia?",
            "¿Los hechos confirmados aparecen en la guía operativa?",
        ],
    },
    {
        "id": "senal-registro-red",
        "titulo": "No registra en red",
        "descripcion": "Equipo sin registro en red; flujo señal de 5 pasos.",
        "linea": "2235560002",
        "dispositivo": "Samsung A22",
        "cooperativa": "coop-batan",
        "categoria_flujo": "senal",
        "mensaje_inicial": "Línea 2235560002, síntoma no se registra en la red, Samsung A22",
        "turnos_guion": [
            {
                "orden": 1,
                "operador": "Línea 2235560002, síntoma no se registra en la red, Samsung A22",
                "esperado": "Categoría Señal, paso 1 alcance geográfico",
                "verificar": ["flujo_senal", "pregunta_zona"],
            },
            {
                "orden": 2,
                "operador": "en varias zonas",
                "esperado": "Paso 2 — prueba de llamadas",
                "verificar": ["paso_llamadas"],
            },
            {
                "orden": 3,
                "operador": "no puede hacer llamadas",
                "esperado": "Paso 3 — reinicio / modo avión",
                "verificar": ["paso_reinicio"],
            },
            {
                "orden": 4,
                "operador": "hecho y sigue igual",
                "esperado": "Paso 4 — escalar a NOC",
                "verificar": ["paso_noc"],
            },
            {
                "orden": 5,
                "operador": "Registrar ticket NOC",
                "esperado": "Ticket con motivo de escalamiento y timeline",
                "verificar": ["ticket_noc", "timeline_pasos"],
                "accion": "forzar_escalamiento",
            },
        ],
        "checklist_imowi": [
            "¿Se detecta 'no se registra en la red' como señal (no datos)?",
            "¿La guía pide zona antes de NOC?",
            "¿El ticket NOC incluye zonas afectadas y pruebas realizadas?",
        ],
    },
]

CHECKLIST_GENERAL_IMOWI = [
    "Utilidad de los pasos operativos vs playbook actual",
    "Datos faltantes en ficha JSC o en el resumen NOC",
    "Claridad del timeline para seguimiento cooperativa → NOC",
    "Riesgo de deriva conversacional (KB, DNI, pasos repetidos)",
    "Tiempo estimado de resolución N1 con el copilot",
    "¿Integrarían esto en la operación diaria? ¿Qué faltaría?",
]


def listar_escenarios_demo() -> list[dict[str, Any]]:
    return ESCENARIOS_DEMO


def obtener_escenario_demo(escenario_id: str) -> dict[str, Any] | None:
    for esc in ESCENARIOS_DEMO:
        if esc["id"] == escenario_id:
            return esc
    return None
