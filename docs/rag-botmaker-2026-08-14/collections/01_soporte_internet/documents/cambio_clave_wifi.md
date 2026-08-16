---
id: blueprint-cambio_clave_wifi
collection: 01_soporte_internet
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Cambiar contraseña o nombre Wi‑Fi

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Soporte técnico
- Intenciones: cambio_clave_wifi
- Casos históricos agregados: 366

## Pasos N1

### 1. `cambio_clave_wifi_detalle`

¿Querés cambiar contraseña, nombre de red o ambos?

### 2. `cambio_clave_wifi_contexto`

¿Tenés acceso al equipo o existe gestión remota autorizada?

### 3. `accion_1`

Usar flujo específico del modelo/equipo validado; no improvisar credenciales ni parámetros.

### 4. `accion_2`

Advertir que los dispositivos deberán reconectarse con la nueva clave.

### 5. `validacion_resultado`

Probar conexión de un dispositivo con la nueva configuración. ¿La gestión quedó resuelta?

- Opciones: si, no

## Reglas de decisión

- Si `validacion_resultado=si`: `resolved/gestion_confirmada`. Cerrar como resuelto por N1.
- Si `validacion_resultado=no`: `n2/gestion_no_resuelta`. Derivar con datos y acciones N1.
- Si `condicion_confirmada`: `n2/n2_1`. Equipo no identificado, sin acceso autorizado o cambio fallido.

## Criterios de éxito

- Probar conexión de un dispositivo con la nueva configuración.

## Contexto obligatorio para N2

- `motivo_consulta`
- `datos_relevantes`
- `acciones_n1_realizadas`
- `resultado_validacion`

## Integraciones necesarias

- Inventario de equipo/CPE
- Gestión remota autorizada o guía por modelo

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
