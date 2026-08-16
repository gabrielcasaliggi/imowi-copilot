# RAG — Soporte técnico de Internet

Diagnóstico guiado N1 para conectividad, CPE y Wi-Fi.

> Estado: **draft**. No indexar en producción hasta completar la matriz de aprobación.

## Intenciones

- `sin_internet` — Sin Internet o servicio caído (6255 casos)
- `cortes_intermitencia` — Cortes o conexión intermitente (3350 casos)
- `wifi_conectividad` — Problema de cobertura o conexión Wi‑Fi (1905 casos)
- `lentitud` — Baja velocidad o lentitud (1019 casos)
- `cambio_clave_wifi` — Cambiar contraseña o nombre Wi‑Fi (366 casos)
- `estado_reclamo` — Consultar estado de reclamo técnico (170 casos)

## Contenido

- Documentos: 9
- Chunks: 130
- Embeddings: `embeddings.npy`, BGE-M3, 130 × 1.024, normalizados.
- Privacidad: métricas agregadas, blueprints curados y políticas propuestas; sin conversaciones.

## Uso

Aplicar filtro estricto `metadata.collection` y `metadata.rag_ready=true` en producción.
Hasta aprobación, `rag_ready` permanece en `false`.
