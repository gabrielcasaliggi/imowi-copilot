---
id: blueprint-reactivacion_pago
collection: 02_facturacion_pagos
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Reactivar servicio después de pagar

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Facturación
- Intenciones: reactivacion_pago
- Casos históricos agregados: 101

## Pasos N1

### 1. `reactivacion_pago_detalle`

¿El pago ya figura acreditado y el servicio continúa suspendido?

### 2. `accion_1`

Verificar acreditación y estado administrativo antes de ejecutar/ofrecer reactivación.

### 3. `validacion_resultado`

Confirmar habilitación administrativa y recuperación efectiva del servicio. ¿La gestión quedó resuelta?

- Opciones: si, no

## Reglas de decisión

- Si `validacion_resultado=si`: `resolved/gestion_confirmada`. Cerrar como resuelto por N1.
- Si `validacion_resultado=no`: `n2/gestion_no_resuelta`. Derivar con datos y acciones N1.
- Si `condicion_confirmada`: `n2/n2_1`. Pago no acreditado, bloqueo distinto de deuda o reactivación fallida.

## Criterios de éxito

- Confirmar habilitación administrativa y recuperación efectiva del servicio.

## Contexto obligatorio para N2

- `motivo_consulta`
- `datos_relevantes`
- `acciones_n1_realizadas`
- `resultado_validacion`

## Integraciones necesarias

- Estado de cuenta
- Estado administrativo y reactivación autorizada

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
