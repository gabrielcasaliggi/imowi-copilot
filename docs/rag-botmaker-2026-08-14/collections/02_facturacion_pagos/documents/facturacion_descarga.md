---
id: blueprint-facturacion_descarga
collection: 02_facturacion_pagos
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Descargar factura, boleta o talón de pago

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Facturación
- Intenciones: descargar_factura_talon
- Casos históricos agregados: 4484

## Pasos N1

### 1. `descargar_factura_talon_detalle`

¿Necesitás factura, boleta o talón/cupón para pagar?

### 2. `accion_1`

Ofrecer el documento o enlace oficial configurado para el cliente autenticado.

### 3. `accion_2`

Si hay varios períodos, pedir cuál necesita antes de entregar el archivo.

### 4. `validacion_resultado`

Confirmar que pudo abrir o descargar el documento. ¿La gestión quedó resuelta?

- Opciones: si, no

## Reglas de decisión

- Si `validacion_resultado=si`: `resolved/gestion_confirmada`. Cerrar como resuelto por N1.
- Si `validacion_resultado=no`: `n2/gestion_no_resuelta`. Derivar con datos y acciones N1.
- Si `condicion_confirmada`: `n2/n2_1`. Documento inexistente, datos inconsistentes o período no disponible.
- Si `condicion_confirmada`: `n2/n2_2`. El canal no puede autenticar al titular de forma segura.

## Criterios de éxito

- Confirmar que pudo abrir o descargar el documento.

## Contexto obligatorio para N2

- `motivo_consulta`
- `datos_relevantes`
- `acciones_n1_realizadas`
- `resultado_validacion`

## Integraciones necesarias

- Consulta autenticada de facturas
- Entrega segura de archivo/enlace

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
