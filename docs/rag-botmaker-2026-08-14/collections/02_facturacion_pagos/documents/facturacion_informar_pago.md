---
id: blueprint-facturacion_informar_pago
collection: 02_facturacion_pagos
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Informar pago realizado

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Facturación
- Intenciones: informar_pago
- Casos históricos agregados: 2636

## Pasos N1

### 1. `informar_pago_detalle`

¿Querés informar un pago o consultar por qué todavía no se acreditó?

### 2. `accion_1`

Consultar estado de acreditación mediante integración; no afirmar recepción sin confirmación.

### 3. `accion_2`

Indicar plazo oficial configurado cuando el pago todavía figure pendiente.

### 4. `validacion_resultado`

Confirmar estado final: acreditado, pendiente o requiere revisión. ¿La gestión quedó resuelta?

- Opciones: si, no

## Reglas de decisión

- Si `validacion_resultado=si`: `resolved/gestion_confirmada`. Cerrar como resuelto por N1.
- Si `validacion_resultado=no`: `n2/gestion_no_resuelta`. Derivar con datos y acciones N1.
- Si `condicion_confirmada`: `n2/n2_1`. Pago fuera del plazo oficial o comprobante que requiere validación manual.

## Criterios de éxito

- Confirmar estado final: acreditado, pendiente o requiere revisión.

## Contexto obligatorio para N2

- `motivo_consulta`
- `datos_relevantes`
- `acciones_n1_realizadas`
- `resultado_validacion`

## Integraciones necesarias

- Estado de cuenta en tiempo real
- Recepción segura de comprobantes

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
