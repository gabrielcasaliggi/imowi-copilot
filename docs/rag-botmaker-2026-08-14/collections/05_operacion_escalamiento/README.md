# RAG — Operación N1 y escalamiento

Contrato transversal de atención, validación y handoff contextual a N2.

> Estado: **draft**. No indexar en producción hasta completar la matriz de aprobación.

## Intenciones

- `hablar_agente` — Solicitud directa de agente (1590 casos)

## Contenido

- Documentos: 4
- Chunks: 5
- Embeddings: `embeddings.npy`, BGE-M3, 5 × 1.024, normalizados.
- Privacidad: métricas agregadas, blueprints curados y políticas propuestas; sin conversaciones.

## Uso

Aplicar filtro estricto `metadata.collection` y `metadata.rag_ready=true` en producción.
Hasta aprobación, `rag_ready` permanece en `false`.
