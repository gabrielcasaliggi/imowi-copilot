---
id: blueprint-facturacion_pago
collection: 02_facturacion_pagos
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Pagar factura

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Facturación
- Intenciones: pagar_factura
- Casos históricos agregados: 6495

## Pasos N1

### 1. `pagar_factura_detalle`

¿Querés pagar ahora o consultar medios de pago?

### 2. `accion_1`

Entregar únicamente enlace o medio de pago oficial configurado.

### 3. `accion_2`

Ofrecer factura/talón si el usuario necesita identificar el período.

### 4. `validacion_resultado`

Confirmar acceso al medio de pago; no afirmar acreditación sin consultarla. ¿La gestión quedó resuelta?

- Opciones: si, no

## Reglas de decisión

- Si `validacion_resultado=si`: `resolved/gestion_confirmada`. Cerrar como resuelto por N1.
- Si `validacion_resultado=no`: `n2/gestion_no_resuelta`. Derivar con datos y acciones N1.
- Si `condicion_confirmada`: `n2/n2_1`. Enlace inválido, importe discutido o pago duplicado.

## Criterios de éxito

- Confirmar acceso al medio de pago; no afirmar acreditación sin consultarla.

## Contexto obligatorio para N2

- `motivo_consulta`
- `datos_relevantes`
- `acciones_n1_realizadas`
- `resultado_validacion`

## Integraciones necesarias

- Generación de enlace oficial de pago

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
