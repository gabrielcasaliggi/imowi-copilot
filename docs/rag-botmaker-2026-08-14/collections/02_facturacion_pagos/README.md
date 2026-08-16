# RAG — Facturación y pagos

Autoservicio e información sobre facturas, pagos y estado de cuenta.

> Estado: **draft**. No indexar en producción hasta completar la matriz de aprobación.

## Intenciones

- `pagar_factura` — Pagar factura (6495 casos)
- `descargar_factura_talon` — Descargar factura, boleta o talón de pago (4484 casos)
- `informar_pago` — Informar pago realizado (2636 casos)
- `solicitud_factura` — Solicitar o recibir factura (1514 casos)
- `estado_cuenta` — Consultar deuda, vencimiento o estado de cuenta (1491 casos)
- `reactivacion_pago` — Reactivar servicio después de pagar (101 casos)

## Contenido

- Documentos: 8
- Chunks: 75
- Embeddings: `embeddings.npy`, BGE-M3, 75 × 1.024, normalizados.
- Privacidad: métricas agregadas, blueprints curados y políticas propuestas; sin conversaciones.

## Uso

Aplicar filtro estricto `metadata.collection` y `metadata.rag_ready=true` en producción.
Hasta aprobación, `rag_ready` permanece en `false`.
