---
id: blueprint-facturacion_factura
collection: 02_facturacion_pagos
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Solicitar o recibir factura

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Facturación
- Intenciones: solicitud_factura
- Casos históricos agregados: 1514

## Pasos N1

### 1. `solicitud_factura_detalle`

¿Qué período y formato de factura necesitás?

### 2. `accion_1`

Consultar y entregar la factura desde sistema autenticado.

### 3. `validacion_resultado`

Confirmar recepción y apertura del documento. ¿La gestión quedó resuelta?

- Opciones: si, no

## Reglas de decisión

- Si `validacion_resultado=si`: `resolved/gestion_confirmada`. Cerrar como resuelto por N1.
- Si `validacion_resultado=no`: `n2/gestion_no_resuelta`. Derivar con datos y acciones N1.
- Si `condicion_confirmada`: `n2/n2_1`. Factura inexistente, período incorrecto o datos fiscales a modificar.

## Criterios de éxito

- Confirmar recepción y apertura del documento.

## Contexto obligatorio para N2

- `motivo_consulta`
- `datos_relevantes`
- `acciones_n1_realizadas`
- `resultado_validacion`

## Integraciones necesarias

- Consulta autenticada de facturas
- Entrega segura de documentos

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
