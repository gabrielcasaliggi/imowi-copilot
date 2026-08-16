---
id: blueprint-internet_adsl
collection: 01_soporte_internet
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Sin Internet — ADSL

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Soporte técnico
- Intenciones: sin_internet
- Casos históricos agregados: 6255

## Pasos N1

### 1. `estado_incidente`

Consultar automáticamente si existe una incidencia en la zona.

### 2. `dispositivos_afectados`

¿El problema ocurre en un dispositivo, en varios o en todos?

- Opciones: uno, varios, todos

### 3. `tiempo_problema`

¿Desde cuándo estás sin servicio?

### 4. `estado_led_power`

¿La luz POWER del módem está encendida?

- Opciones: si, no, no_sabe

### 5. `estado_led_dsl`

¿La luz DSL está fija, parpadeando o apagada?

- Opciones: fija, parpadeando, apagada, no_sabe

- Preguntar cuando: `estado_led_power=si`

### 6. `estado_led_internet`

¿La luz INTERNET está encendida?

- Opciones: si, no, roja, no_sabe

- Preguntar cuando: `estado_led_dsl=fija`

### 7. `cableado_telefonico`

¿El cable telefónico y el filtro están firmes y sin daño visible?

- Opciones: si, no, no_sabe

### 8. `ruido_linea`

Si usás teléfono fijo en la misma línea, ¿escuchás ruido o falta de tono?

- Opciones: sin_ruido, con_ruido, sin_tono, no_aplica

### 9. `reinicio_previo`

¿Ya reiniciaste el módem desde que comenzó el problema?

- Opciones: si, no

### 10. `reinicio_controlado`

Reiniciá la alimentación del módem con el procedimiento aprobado y esperá que DSL estabilice.

- Preguntar cuando: `reinicio_previo=no`

### 11. `validacion_navegacion`

¿La luz DSL quedó fija y ya podés navegar?

- Opciones: si, no

## Reglas de decisión

- Si `estado_incidente=activo`: `inform/incidente_masivo`. Informar estado confirmado de incidencia.
- Si `estado_led_dsl in [apagada,parpadeando] after reinicio`: `n2/sin_sincronismo_dsl`. Derivar con cableado y estado DSL.
- Si `ruido_linea in [con_ruido,sin_tono]`: `n2/posible_falla_linea`. Derivar con síntoma de línea.
- Si `validacion_navegacion=si`: `resolved/servicio_restaurado`. Cerrar como resuelto por N1.
- Si `validacion_navegacion=no`: `n2/sin_servicio_post_n1`. Derivar sin repetir diagnóstico.

## Criterios de éxito

- DSL fija y navegación confirmada.

## Contexto obligatorio para N2

- `tecnologia_servicio`
- `dispositivos_afectados`
- `tiempo_problema`
- `estado_incidente`
- `luces_equipo`
- `acciones_n1_realizadas`
- `resultado_validacion`
- `estado_led_dsl`
- `estado_led_internet`
- `ruido_linea`

## Integraciones necesarias

- Estado de red/incidentes
- Estado de línea
- Inventario CPE

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
