---
id: blueprint-movil
collection: 04_servicios_adicionales
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Portabilidad o servicio móvil

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Móvil
- Intenciones: movil_portabilidad
- Casos históricos agregados: 527

## Pasos N1

### 1. `movil_portabilidad_detalle`

¿Consultás portabilidad, activación, eSIM o una falla de línea móvil?

### 2. `accion_1`

Mostrar requisitos/estado únicamente desde sistemas vigentes.

### 3. `validacion_resultado`

Confirmar estado o próximo paso de gestión. ¿La gestión quedó resuelta?

- Opciones: si, no

## Reglas de decisión

- Si `validacion_resultado=si`: `resolved/gestion_confirmada`. Cerrar como resuelto por N1.
- Si `validacion_resultado=no`: `n2/gestion_no_resuelta`. Derivar con datos y acciones N1.
- Si `condicion_confirmada`: `n2/n2_1`. Validación de identidad, provisión o falla de red que exceda autogestión.

## Criterios de éxito

- Confirmar estado o próximo paso de gestión.

## Contexto obligatorio para N2

- `motivo_consulta`
- `datos_relevantes`
- `acciones_n1_realizadas`
- `resultado_validacion`

## Integraciones necesarias

- Estado de línea/portabilidad
- Autenticación de titular

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
