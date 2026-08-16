---
id: blueprint-tv_sensa
collection: 04_servicios_adicionales
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Consulta o falla de TV Sensa

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: TV
- Intenciones: tv_sensa
- Casos históricos agregados: 485

## Pasos N1

### 1. `tv_sensa_detalle`

¿Es acceso, reproducción, canales o funcionamiento de la aplicación?

### 2. `accion_1`

Verificar estado del servicio y aplicar guía aprobada para dispositivo/aplicación.

### 3. `validacion_resultado`

Confirmar acceso y reproducción de contenido. ¿La gestión quedó resuelta?

- Opciones: si, no

## Reglas de decisión

- Si `validacion_resultado=si`: `resolved/gestion_confirmada`. Cerrar como resuelto por N1.
- Si `validacion_resultado=no`: `n2/gestion_no_resuelta`. Derivar con datos y acciones N1.
- Si `condicion_confirmada`: `n2/n2_1`. Cuenta/provisión inconsistente o falla persistente de plataforma.

## Criterios de éxito

- Confirmar acceso y reproducción de contenido.

## Contexto obligatorio para N2

- `motivo_consulta`
- `datos_relevantes`
- `acciones_n1_realizadas`
- `resultado_validacion`

## Integraciones necesarias

- Estado de suscripción
- Estado de plataforma

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
