---
id: blueprint-facturacion_estado_cuenta
collection: 02_facturacion_pagos
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Consultar deuda, vencimiento o estado de cuenta

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Facturación
- Intenciones: estado_cuenta
- Casos históricos agregados: 1491

## Pasos N1

### 1. `estado_cuenta_detalle`

¿Querés conocer saldo, vencimiento o estado de una factura?

### 2. `accion_1`

Consultar el dato en sistema autenticado y mostrar solo información necesaria.

### 3. `validacion_resultado`

Confirmar que la información respondió la consulta. ¿La gestión quedó resuelta?

- Opciones: si, no

## Reglas de decisión

- Si `validacion_resultado=si`: `resolved/gestion_confirmada`. Cerrar como resuelto por N1.
- Si `validacion_resultado=no`: `n2/gestion_no_resuelta`. Derivar con datos y acciones N1.
- Si `condicion_confirmada`: `n2/n2_1`. Saldo disputado, ajustes, notas de crédito o inconsistencia entre sistemas.

## Criterios de éxito

- Confirmar que la información respondió la consulta.

## Contexto obligatorio para N2

- `motivo_consulta`
- `datos_relevantes`
- `acciones_n1_realizadas`
- `resultado_validacion`

## Integraciones necesarias

- Estado de cuenta en tiempo real

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
