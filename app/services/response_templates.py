"""Plantillas de respuesta operativa — inspiradas en helpdesk, adaptadas a NOC telco."""

from __future__ import annotations

PLANTILLAS_RESPUESTA: list[dict[str, str]] = [
    {
        "id": "persistencia_n1",
        "nombre": "Confirmar persistencia",
        "categoria": "General",
        "contenido": (
            "Registré las verificaciones N1 realizadas. "
            "¿El cliente sigue con el mismo inconveniente después de las pruebas?"
        ),
    },
    {
        "id": "escalamiento_noc",
        "nombre": "Escalamiento NOC",
        "categoria": "Escalamiento",
        "contenido": (
            "Con las pruebas N1 documentadas, escalamos el caso al NOC imowi "
            "para revisión de red. Ticket registrado con el contexto operativo."
        ),
    },
    {
        "id": "escalamiento_carrier_sms",
        "nombre": "Escalamiento carrier SMS",
        "categoria": "SMS / A2P",
        "contenido": (
            "Las verificaciones JSC están OK y el problema SMS/A2P persiste. "
            "Escalamos a carrier con línea, remitente de ejemplo y horario del incidente."
        ),
    },
    {
        "id": "solicitar_datos_sms",
        "nombre": "Pedir datos SMS",
        "categoria": "SMS / A2P",
        "contenido": (
            "Para el escalamiento al carrier necesito: "
            "ejemplo de remitente (Apple, Netflix, etc.) y horario aproximado del fallo."
        ),
    },
    {
        "id": "roaming_jsc",
        "nombre": "Roaming — verificar JSC",
        "categoria": "Roaming",
        "contenido": (
            "Verifiquemos en JSC que la línea tenga roaming internacional activo "
            "y datos en itinerancia habilitados antes de seguir con pruebas en el equipo."
        ),
    },
    {
        "id": "datos_apn",
        "nombre": "Datos — validar APN",
        "categoria": "Datos",
        "contenido": (
            "Confirmemos que el APN esté configurado según el plan del abonado "
            "y que los datos móviles estén activos. Luego reinicio o modo avión."
        ),
    },
    {
        "id": "senal_pruebas",
        "nombre": "Señal — pruebas básicas",
        "categoria": "Señal",
        "contenido": (
            "Indiquemos si el falla es en una sola zona o varias ubicaciones, "
            "si las llamadas funcionan y si ya se probó reinicio o cambio de SIM."
        ),
    },
    {
        "id": "cierre_resuelto",
        "nombre": "Cierre resuelto",
        "categoria": "Cierre",
        "contenido": (
            "Con las pruebas confirmadas, el caso queda resuelto en N1. "
            "Si el inconveniente vuelve a aparecer, iniciar un nuevo reclamo con pruebas actuales."
        ),
    },
    {
        "id": "cuenta_deuda",
        "nombre": "Cuenta con deuda",
        "categoria": "Facturación",
        "contenido": (
            "La línea presenta restricción de cuenta (deuda/suspensión). "
            "Antes de escalar a red, verificar estado contable con la cooperativa."
        ),
    },
]


def listar_plantillas(*, categoria: str = "") -> list[dict[str, str]]:
    if not categoria:
        return list(PLANTILLAS_RESPUESTA)
    cat = categoria.lower()
    return [p for p in PLANTILLAS_RESPUESTA if cat in p["categoria"].lower() or p["categoria"] == "General"]
