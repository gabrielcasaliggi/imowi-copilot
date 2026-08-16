---
id: blueprint-estado_reclamo
collection: 01_soporte_internet
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Consultar estado de reclamo técnico

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Soporte técnico
- Intenciones: estado_reclamo
- Casos históricos agregados: 170

## Pasos N1

### 1. `estado_reclamo_detalle`

¿Tenés un reclamo u orden abierta que querés consultar?

### 2. `accion_1`

Consultar estado real y última actualización; no prometer fecha no registrada.

### 3. `validacion_resultado`

Confirmar que el usuario comprendió estado y próximo hito. ¿La gestión quedó resuelta?

- Opciones: si, no

## Reglas de decisión

- Si `validacion_resultado=si`: `resolved/gestion_confirmada`. Cerrar como resuelto por N1.
- Si `validacion_resultado=no`: `n2/gestion_no_resuelta`. Derivar con datos y acciones N1.
- Si `condicion_confirmada`: `n2/n2_1`. Orden vencida, sin actualización o información contradictoria.

## Criterios de éxito

- Confirmar que el usuario comprendió estado y próximo hito.

## Contexto obligatorio para N2

- `motivo_consulta`
- `datos_relevantes`
- `acciones_n1_realizadas`
- `resultado_validacion`

## Integraciones necesarias

- R
- e
- c
- l
- a
- m
- o
- s
-  
- y
-  
- ó
- r
- d
- e
- n
- e
- s
-  
- d
- e
-  
- t
- r
- a
- b
- a
- j
- o

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
