---
id: blueprint-cambio_plan
collection: 03_comercial_administracion
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Cambiar plan o velocidad

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Comercial
- Intenciones: cambio_plan
- Casos históricos agregados: 241

## Pasos N1

### 1. `cambio_plan_detalle`

¿Querés aumentar, reducir o conocer opciones de plan?

### 2. `accion_1`

Consultar elegibilidad, precio y condiciones vigentes antes de ofrecer el cambio.

### 3. `validacion_resultado`

Confirmar plan, precio, vigencia y número de gestión. ¿La gestión quedó resuelta?

- Opciones: si, no

## Reglas de decisión

- Si `validacion_resultado=si`: `resolved/gestion_confirmada`. Cerrar como resuelto por N1.
- Si `validacion_resultado=no`: `n2/gestion_no_resuelta`. Derivar con datos y acciones N1.
- Si `condicion_confirmada`: `n2/n2_1`. Excepción comercial, tecnología incompatible o reducción con condiciones especiales.

## Criterios de éxito

- Confirmar plan, precio, vigencia y número de gestión.

## Contexto obligatorio para N2

- `motivo_consulta`
- `datos_relevantes`
- `acciones_n1_realizadas`
- `resultado_validacion`

## Integraciones necesarias

- Catálogo y elegibilidad
- Gestión de cambio de plan

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
