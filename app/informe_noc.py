"""Arma el informe técnico objetivo para el NOC (velocidad de resolución)."""

from __future__ import annotations


def construir_informe_noc(
    *,
    problema: str = "",
    alcance: str = "",
    acciones_realizadas: str = "",
    datos_verificados: str = "",
    falla_libre: str = "",
) -> str:
    """
    Formato fijo que el NOC puede leer sin abrir el chat.
    Solo incluye secciones con contenido real.
    """
    secciones: list[str] = []
    if problema.strip():
        secciones.append(f"PROBLEMA: {problema.strip()}")
    if alcance.strip():
        secciones.append(f"ALCANCE: {alcance.strip()}")
    if acciones_realizadas.strip():
        secciones.append(f"ACCIONES DEL OPERADOR: {acciones_realizadas.strip()}")
    if datos_verificados.strip():
        secciones.append(f"DATOS VERIFICADOS: {datos_verificados.strip()}")

    if secciones:
        return "\n".join(secciones)

    return falla_libre.strip()
