---
id: blueprint-guia_telefonica
collection: 04_servicios_adicionales
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Consultar guía telefónica

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Telefonía
- Intenciones: guia_telefonica
- Casos históricos agregados: 140

## Pasos N1

### 1. `guia_telefonica_detalle`

¿Buscás acceso a la guía o información sobre su uso?

### 2. `accion_1`

Entregar acceso oficial y explicar búsqueda sin revelar datos no públicos.

### 3. `validacion_resultado`

Confirmar acceso a la guía. ¿La gestión quedó resuelta?

- Opciones: si, no

## Reglas de decisión

- Si `validacion_resultado=si`: `resolved/gestion_confirmada`. Cerrar como resuelto por N1.
- Si `validacion_resultado=no`: `n2/gestion_no_resuelta`. Derivar con datos y acciones N1.
- Si `condicion_confirmada`: `n2/n2_1`. Solicitud de modificación o exclusión de datos.

## Criterios de éxito

- Confirmar acceso a la guía.

## Contexto obligatorio para N2

- `motivo_consulta`
- `datos_relevantes`
- `acciones_n1_realizadas`
- `resultado_validacion`

## Integraciones necesarias

- G
- u
- í
- a
-  
- t
- e
- l
- e
- f
- ó
- n
- i
- c
- a
-  
- o
- f
- i
- c
- i
- a
- l

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
