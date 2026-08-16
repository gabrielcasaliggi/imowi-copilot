---
id: blueprint-cambio_titularidad
collection: 03_comercial_administracion
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Cambio de titularidad

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Administración
- Intenciones: cambio_titularidad
- Casos históricos agregados: 231

## Pasos N1

### 1. `cambio_titularidad_detalle`

¿Es cambio de titular, corrección de datos o sucesión del servicio?

### 2. `accion_1`

Informar requisitos vigentes y abrir gestión autenticada sin exponer documentos en texto libre.

### 3. `validacion_resultado`

Entregar identificador y estado de gestión cuando el sistema lo permita. ¿La gestión quedó resuelta?

- Opciones: si, no

## Reglas de decisión

- Si `validacion_resultado=si`: `resolved/gestion_confirmada`. Cerrar como resuelto por N1.
- Si `validacion_resultado=no`: `n2/gestion_no_resuelta`. Derivar con datos y acciones N1.
- Si `condicion_confirmada`: `n2/n2_1`. Validación documental, deuda, disputa o excepción contractual.

## Criterios de éxito

- Entregar identificador y estado de gestión cuando el sistema lo permita.

## Contexto obligatorio para N2

- `motivo_consulta`
- `datos_relevantes`
- `acciones_n1_realizadas`
- `resultado_validacion`

## Integraciones necesarias

- Gestión administrativa segura
- Carga protegida de documentación

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
