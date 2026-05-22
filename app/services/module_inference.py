"""Inferencia de módulo/bloque vía RAG (reemplaza diccionario hardcodeado)."""

from __future__ import annotations

from app.knowledge import buscar_contexto
from app.models import MensajeHistorial


def _texto_historial(historial: list[MensajeHistorial]) -> str:
    return "\n".join(
        f"{'USUARIO' if m.rol == 'usuario' else 'ASISTENTE'}: {m.contenido}"
        for m in historial
    )


def inferir_modulo(
    historial: list[MensajeHistorial],
    modulo_hint: str = "",
) -> tuple[str, str]:
    texto = _texto_historial(historial)
    resultado = buscar_contexto(texto)

    if resultado.encontrado and resultado.bloque:
        return resultado.bloque.id, resultado.bloque.titulo

    return "escalamiento", "Escalamiento NOC — sin KB aplicable"
