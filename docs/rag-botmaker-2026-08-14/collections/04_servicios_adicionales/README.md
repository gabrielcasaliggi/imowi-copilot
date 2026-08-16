# RAG — Servicios adicionales

Atención especializada para TV, telefonía, móvil y accesos.

> Estado: **draft**. No indexar en producción hasta completar la matriz de aprobación.

## Intenciones

- `movil_portabilidad` — Portabilidad o servicio móvil (527 casos)
- `tv_sensa` — Consulta o falla de TV Sensa (485 casos)
- `credenciales_acceso` — Recuperar o cambiar credenciales de acceso (465 casos)
- `telefonia_fija` — Falla o consulta de telefonía fija (455 casos)
- `guia_telefonica` — Consultar guía telefónica (140 casos)

## Contenido

- Documentos: 5
- Chunks: 45
- Embeddings: `embeddings.npy`, BGE-M3, 45 × 1.024, normalizados.
- Privacidad: métricas agregadas, blueprints curados y políticas propuestas; sin conversaciones.

## Uso

Aplicar filtro estricto `metadata.collection` y `metadata.rag_ready=true` en producción.
Hasta aprobación, `rag_ready` permanece en `false`.
