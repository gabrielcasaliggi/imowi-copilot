# RAG — Comercial y administración

Cobertura, contratación, instalación y gestiones administrativas.

> Estado: **draft**. No indexar en producción hasta completar la matriz de aprobación.

## Intenciones

- `baja_servicio` — Solicitud de baja del servicio (1431 casos)
- `cobertura_contratacion` — Consultar cobertura o contratar servicio (932 casos)
- `seguimiento_instalacion` — Consultar instalación o visita técnica (502 casos)
- `cambio_plan` — Cambiar plan o velocidad (241 casos)
- `cambio_titularidad` — Cambio de titularidad (231 casos)

## Contenido

- Documentos: 5
- Chunks: 46
- Embeddings: `embeddings.npy`, BGE-M3, 46 × 1.024, normalizados.
- Privacidad: métricas agregadas, blueprints curados y políticas propuestas; sin conversaciones.

## Uso

Aplicar filtro estricto `metadata.collection` y `metadata.rag_ready=true` en producción.
Hasta aprobación, `rag_ready` permanece en `false`.
