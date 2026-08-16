---
id: blueprint-telefonia_fija
collection: 04_servicios_adicionales
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Falla o consulta de telefonía fija

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Telefonía
- Intenciones: telefonia_fija
- Casos históricos agregados: 455

## Pasos N1

### 1. `telefonia_fija_detalle`

¿No tiene tono, no llama, no recibe o presenta ruido?

### 2. `accion_1`

Consultar estado del servicio y guiar pruebas aprobadas según tecnología instalada.

### 3. `validacion_resultado`

Realizar llamada entrante y saliente cuando sea posible. ¿La gestión quedó resuelta?

- Opciones: si, no

## Reglas de decisión

- Si `validacion_resultado=si`: `resolved/gestion_confirmada`. Cerrar como resuelto por N1.
- Si `validacion_resultado=no`: `n2/gestion_no_resuelta`. Derivar con datos y acciones N1.
- Si `condicion_confirmada`: `n2/n2_1`. Sin tono persistente, falla física o provisión/configuración de línea.

## Criterios de éxito

- Realizar llamada entrante y saliente cuando sea posible.

## Contexto obligatorio para N2

- `motivo_consulta`
- `datos_relevantes`
- `acciones_n1_realizadas`
- `resultado_validacion`

## Integraciones necesarias

- Estado de línea
- Inventario de tecnología

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
