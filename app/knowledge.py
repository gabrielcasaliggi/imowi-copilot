"""Fachada pública sobre el motor RAG de knowledge_rag.py."""

from __future__ import annotations

from app.knowledge_rag import (
    ResultadoBusqueda,
    buscar_contexto,
    cargar_base_conocimiento,
    esta_cargado,
    estadisticas,
    formatear_contexto_para_prompt,
    formatear_modo_escalamiento,
    listar_muestra_modulos,
    parsear_markdown,
    resolver_ruta_base_conocimiento,
)

__all__ = [
    "ResultadoBusqueda",
    "buscar_contexto",
    "cargar_base_conocimiento",
    "esta_cargado",
    "estadisticas",
    "formatear_contexto_para_prompt",
    "formatear_modo_escalamiento",
    "listar_muestra_modulos",
    "parsear_markdown",
    "resolver_ruta_base_conocimiento",
]
