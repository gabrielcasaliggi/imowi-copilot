---
id: blueprint-facturacion_reclamo
collection: 02_facturacion_pagos
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Cobro o importe no reconocido

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Facturación
- Intenciones: estado_cuenta
- Casos históricos agregados: 1491

## Pasos N1

### 1. `detalle_factura`

¿Qué importe, concepto o período no reconocés?

### 2. `medio_pago`

Si corresponde a un pago, ¿qué medio usaste y en qué fecha?

### 3. `consulta_movimientos`

Consultar factura, saldo y movimientos confirmados.

### 4. `confirmacion_diferencia`

¿La diferencia continúa después de mostrar el detalle?

- Opciones: si, no

## Reglas de decisión

- Si `confirmacion_diferencia=no`: `resolved/detalle_aclarado`. Cerrar como aclarado.
- Si `confirmacion_diferencia=si`: `n2/revision_facturacion`. Crear caso con factura, período, importe y medio de pago; no prometer respuesta ni ajuste.

## Criterios de éxito

- D
- e
- t
- a
- l
- l
- e
-  
- a
- c
- l
- a
- r
- a
- d
- o
-  
- o
-  
- r
- e
- c
- l
- a
- m
- o
-  
- c
- r
- e
- a
- d
- o
-  
- c
- o
- n
-  
- i
- d
- e
- n
- t
- i
- f
- i
- c
- a
- d
- o
- r
- .

## Contexto obligatorio para N2

- `periodo_factura`
- `concepto_importe`
- `medio_pago`
- `movimientos_consultados`

## Integraciones necesarias

- Facturas y estado de cuenta
- Creación de reclamo

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
