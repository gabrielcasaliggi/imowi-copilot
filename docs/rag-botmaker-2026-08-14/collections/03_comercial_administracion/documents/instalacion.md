---
id: blueprint-instalacion
collection: 03_comercial_administracion
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Consultar instalación o visita técnica

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Instalaciones
- Intenciones: seguimiento_instalacion
- Casos históricos agregados: 502

## Pasos N1

### 1. `seguimiento_instalacion_detalle`

¿Consultás fecha, franja horaria o estado de una instalación/visita?

### 2. `accion_1`

Consultar agenda/orden vigente y comunicar solo datos confirmados.

### 3. `validacion_resultado`

Confirmar fecha, franja o estado; registrar aceptación cuando corresponda. ¿La gestión quedó resuelta?

- Opciones: si, no

## Reglas de decisión

- Si `validacion_resultado=si`: `resolved/gestion_confirmada`. Cerrar como resuelto por N1.
- Si `validacion_resultado=no`: `n2/gestion_no_resuelta`. Derivar con datos y acciones N1.
- Si `condicion_confirmada`: `n2/n2_1`. Reprogramación no disponible, orden inconsistente o técnico demorado sin estado.

## Criterios de éxito

- Confirmar fecha, franja o estado; registrar aceptación cuando corresponda.

## Contexto obligatorio para N2

- `motivo_consulta`
- `datos_relevantes`
- `acciones_n1_realizadas`
- `resultado_validacion`

## Integraciones necesarias

- A
- g
- e
- n
- d
- a
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
