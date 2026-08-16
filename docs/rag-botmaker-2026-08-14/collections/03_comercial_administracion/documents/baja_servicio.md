---
id: blueprint-baja_servicio
collection: 03_comercial_administracion
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Solicitud de baja del servicio

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Administración
- Intenciones: baja_servicio
- Casos históricos agregados: 1431

## Pasos N1

### 1. `baja_servicio_detalle`

¿Solicitás baja total, de un producto adicional o cambio de titular?

### 2. `accion_1`

Informar requisitos y canal oficial sin obstaculizar la solicitud.

### 3. `accion_2`

Registrar intención y datos mínimos mediante autenticación segura.

### 4. `validacion_resultado`

Entregar número/estado de gestión cuando exista integración confirmada. ¿La gestión quedó resuelta?

- Opciones: si, no

## Reglas de decisión

- Si `validacion_resultado=si`: `resolved/gestion_confirmada`. Cerrar como resuelto por N1.
- Si `validacion_resultado=no`: `n2/gestion_no_resuelta`. Derivar con datos y acciones N1.
- Si `condicion_confirmada`: `n2/n2_1`. La baja requiere validación administrativa o gestión de equipos/saldo.

## Criterios de éxito

- Entregar número/estado de gestión cuando exista integración confirmada.

## Contexto obligatorio para N2

- `motivo_consulta`
- `datos_relevantes`
- `acciones_n1_realizadas`
- `resultado_validacion`

## Integraciones necesarias

- Gestión de bajas
- Autenticación de titular

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
