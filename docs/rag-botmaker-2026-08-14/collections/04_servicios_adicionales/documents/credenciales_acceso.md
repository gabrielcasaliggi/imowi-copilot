---
id: blueprint-credenciales_acceso
collection: 04_servicios_adicionales
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Recuperar o cambiar credenciales de acceso

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Autogestión
- Intenciones: credenciales_acceso
- Casos históricos agregados: 465

## Pasos N1

### 1. `credenciales_acceso_detalle`

¿La clave corresponde a Wi‑Fi, Oficina Virtual, correo u otro servicio?

### 2. `accion_1`

Derivar al flujo autenticado específico; nunca pedir ni repetir la clave actual.

### 3. `validacion_resultado`

Confirmar acceso sin registrar la nueva credencial en conversación. ¿La gestión quedó resuelta?

- Opciones: si, no

## Reglas de decisión

- Si `validacion_resultado=si`: `resolved/gestion_confirmada`. Cerrar como resuelto por N1.
- Si `validacion_resultado=no`: `n2/gestion_no_resuelta`. Derivar con datos y acciones N1.
- Si `condicion_confirmada`: `n2/n2_1`. No puede validar identidad o el recupero automático falla.

## Criterios de éxito

- Confirmar acceso sin registrar la nueva credencial en conversación.

## Contexto obligatorio para N2

- `motivo_consulta`
- `datos_relevantes`
- `acciones_n1_realizadas`
- `resultado_validacion`

## Integraciones necesarias

- Recuperación segura por servicio
- Autenticación de titular

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
