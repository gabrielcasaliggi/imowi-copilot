# RAGs Botmaker para atención ISP

Paquete local generado desde 80.848 sesiones y 66.056 casos útiles. Contiene cinco colecciones especializadas, 23 intenciones y 27 blueprints N1.

## Estado de seguridad

**Borrador, no productivo.** Solo incluye métricas agregadas, contenido curado de blueprints y políticas propuestas. No contiene conversaciones ni texto de clientes. Los derivados v4 bloqueados por privacidad no se usaron.

Todos los chunks tienen `metadata.rag_ready=false`. Cambiar a `true` solamente después de completar `approval-matrix.csv` y aprobar cada documento.

## Archivos

- `router.json`: intención a colección.
- `collections/*/documents/`: documentos para revisión humana.
- `collections/*/chunks.jsonl`: chunks de cada índice vectorial.
- `collections/*/embeddings.npy`: vectores BGE-M3 normalizados, alineados por fila con `chunks.jsonl`.
- `collections/*/embedding-metadata.jsonl`: correspondencia explícita entre índice vectorial e ID de chunk.
- `all-chunks.jsonl`: corpus consolidado para cargas por lote.
- `all-embeddings.npy`: matriz consolidada de 301 × 1.024 en `float32`.
- `retrieval-config.json`: modelo, dimensión, normalización y plantilla usada.
- `chunk.schema.json`: contrato mínimo del chunk.
- `approval-matrix.csv`: gate técnico, funcional, privacidad e integraciones.
- `manifest.json`: versiones, conteos y hashes SHA-256.

## Flujo de recuperación recomendado

1. Clasificar intención.
2. Elegir colección mediante `router.json`.
3. Generar embedding de consulta con BGE-M3 normalizado y buscar por producto punto/coseno dentro de esa colección.
4. Filtrar siempre `rag_ready=true`, versión vigente y tecnología aplicable.
5. Combinar evidencia RAG con resultados de APIs transaccionales.
6. Aplicar reglas del playbook y validar resultado.
7. Derivar a N2 con contexto completo cuando corresponda.

El RAG explica y recupera procedimientos. No sustituye APIs de deuda, pagos, facturas, cobertura, incidentes, inventario o visitas.
