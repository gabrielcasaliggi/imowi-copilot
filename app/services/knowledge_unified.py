"""KB unificada: RAG global (Markdown) + artículos tenant (SQLite)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.estate import repository as repo
from app.knowledge import buscar_contexto, formatear_contexto_para_prompt


def buscar_unificado(
    db: Session,
    org_id: str,
    query: str,
    *,
    limit_tenant: int = 5,
) -> dict:
    """
    Consulta ambas fuentes de conocimiento y devuelve contexto consolidado.
    Prioriza tenant si hay match; complementa con RAG global.
    """
    consulta = (query or "").strip()
    tenant_hits = repo.search_kb(db, org_id, consulta, limit=limit_tenant) if consulta else []
    rag = buscar_contexto(consulta) if consulta else None

    articulos: list[dict] = []
    for a in tenant_hits:
        articulos.append({
            "fuente": "tenant",
            "titulo": a.titulo,
            "categoria": a.categoria,
            "contenido": a.contenido,
            "id": a.id,
        })

    rag_encontrado = bool(rag and rag.encontrado)
    if rag_encontrado and rag.bloque:
        articulos.append({
            "fuente": "global",
            "titulo": rag.bloque.titulo,
            "categoria": rag.bloque.id,
            "contenido": rag.bloque.contenido,
            "id": rag.bloque.id,
            "puntaje": rag.puntaje,
        })

    modo = "escalamiento"
    if rag_encontrado:
        modo = rag.modo
    elif tenant_hits:
        modo = "resolucion"

    titulo_principal = ""
    if tenant_hits:
        titulo_principal = tenant_hits[0].titulo
    elif rag_encontrado and rag.bloque:
        titulo_principal = rag.bloque.titulo

    ctx_partes = []
    if tenant_hits:
        ctx_partes.append(
            "\n".join(f"- [Tenant] {a.titulo} ({a.categoria}): {a.contenido[:300]}" for a in tenant_hits)
        )
    if rag_encontrado:
        ctx_partes.append(formatear_contexto_para_prompt(rag))

    return {
        "encontrado": bool(tenant_hits or rag_encontrado),
        "modo": modo,
        "titulo_principal": titulo_principal,
        "articulos": articulos,
        "kb_contexto": "\n\n".join(ctx_partes),
        "rag": {
            "encontrado": rag_encontrado,
            "modo": rag.modo if rag else "escalamiento",
            "puntaje": rag.puntaje if rag else 0.0,
            "bloque_id": rag.bloque.id if rag and rag.bloque else None,
        },
        "tenant_count": len(tenant_hits),
    }
