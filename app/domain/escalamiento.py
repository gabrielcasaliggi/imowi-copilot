"""Detección determinística de intención de escalamiento."""

from __future__ import annotations

ESCALAMIENTO_FRASES = (
    "escalar",
    "escalam",
    "al noc",
    "enviar al noc",
    "mandar al noc",
    "generar ticket",
    "crear ticket",
    "registrar ticket",
    "hacer ticket",
    "no funciona",
    "sigue igual",
    "sigue sin",
    "no se resolv",
    "persiste",
    "mismo problema",
    "aún no",
    "aun no",
    "no sirvio",
    "no sirvió",
    "sin solucion",
    "voy a escalar",
    "se escalará",
    "escalar el caso",
    "registrar el caso",
    "registrado para el noc",
    "se registrará",
    "equipo noc",
    "caso al noc",
    "pasar a n2",
    "derivar a proveedor",
    "mandar al carrier",
    "confirmo persistencia",
    "confirmar persistencia",
    "te confirmo persistencia",
    "excepto los sms",
    "excepto el sms",
)


def texto_dialogo_reciente(historial: list[dict], n: int = 8) -> str:
    return " ".join(
        m.get("contenido", "").lower()
        for m in historial[-n:]
        if m.get("rol") == "usuario"
    )


def detectar_escalamiento(historial: list[dict]) -> bool:
    texto = texto_dialogo_reciente(historial)
    return any(frase in texto for frase in ESCALAMIENTO_FRASES)
