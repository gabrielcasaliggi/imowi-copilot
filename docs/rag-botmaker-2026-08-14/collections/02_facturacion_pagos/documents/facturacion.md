---
id: blueprint-facturacion
collection: 02_facturacion_pagos
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Enrutador de facturación

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Facturación
- Intenciones: pagar_factura, descargar_factura_talon, informar_pago, solicitud_factura, estado_cuenta
- Casos históricos agregados: 16620

## Pasos N1

### 1. `tipo_consulta_facturacion`

¿Qué necesitás: pagar, descargar factura/talón, informar un pago, recibir factura, consultar deuda o reclamar un cobro?

- Opciones: pagar, descargar, informar_pago, recibir_factura, estado_cuenta, cobro_no_reconocido

## Reglas de decisión

- Si `tipo_consulta_facturacion=pagar`: `route/pagar`. Continuar con facturacion_pago.
- Si `tipo_consulta_facturacion=descargar`: `route/descargar`. Continuar con facturacion_descarga.
- Si `tipo_consulta_facturacion=informar_pago`: `route/informar_pago`. Continuar con facturacion_informar_pago.
- Si `tipo_consulta_facturacion=recibir_factura`: `route/recibir_factura`. Continuar con facturacion_factura.
- Si `tipo_consulta_facturacion=estado_cuenta`: `route/estado_cuenta`. Continuar con facturacion_estado_cuenta.
- Si `tipo_consulta_facturacion=cobro_no_reconocido`: `route/cobro_no_reconocido`. Continuar con facturacion_reclamo.

## Criterios de éxito

- Consulta derivada al flujo correcto.

## Contexto obligatorio para N2

- `tipo_consulta_facturacion`
- `detalle_consulta`

## Integraciones necesarias

- Estado de cuenta y facturas

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
