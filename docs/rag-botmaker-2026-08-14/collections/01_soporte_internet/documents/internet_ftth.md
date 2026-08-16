---
id: blueprint-internet_ftth
collection: 01_soporte_internet
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Sin Internet — Fibra/FTTH

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

¿La luz POWER de la ONT está encendida?

- Opciones: si, no, no_sabe

### 5. `estado_led_los`

¿La luz LOS está apagada, roja fija o roja parpadeando?

- Opciones: apagada, roja_fija, roja_parpadeando, no_sabe

- Preguntar cuando: `estado_led_power=si`

### 6. `estado_led_pon`

¿La luz PON está fija, parpadeando o apagada?

- Opciones: fija, parpadeando, apagada, no_sabe

- Preguntar cuando: `estado_led_power=si and estado_led_los=apagada`

### 7. `conexion_cableada`

¿Tampoco navega un equipo conectado por cable?

- Opciones: tampoco_navega, por_cable_funciona, no_puede_probar

- Preguntar cuando: `dispositivos_afectados!=uno`

### 8. `cables_ont`

Sin desconectar la fibra, ¿los cables de energía y red están firmes y sin daño visible?

- Opciones: si, no, no_sabe

### 9. `reinicio_previo`

¿Ya reiniciaste la ONT/router desde que comenzó el problema?

- Opciones: si, no

### 10. `reinicio_controlado`

Desconectá solo la alimentación eléctrica, esperá el tiempo aprobado y volvé a conectarla. Avisame cuando las luces estabilicen.

- Preguntar cuando: `reinicio_previo=no and estado_led_los=apagada`

### 11. `luces_post_reinicio`

Después del reinicio, ¿POWER y PON quedaron fijas y LOS apagada?

- Opciones: si, no

- Preguntar cuando: `reinicio_controlado=completed`

### 12. `validacion_navegacion`

Probá abrir dos sitios o servicios. ¿Ya navega correctamente?

- Opciones: si, no

## Reglas de decisión

- Si `estado_incidente=activo`: `inform/incidente_masivo`. Informar incidencia y estado/ETA solo si sistema lo confirma; no reiniciar ni derivar duplicado.
- Si `estado_led_power=no and energia_verificada`: `n2/equipo_sin_energia`. Derivar con posible falla de fuente/ONT.
- Si `estado_led_los in [roja_fija,roja_parpadeando]`: `n2/alarma_optica`. Derivar como alarma óptica; no pedir manipular fibra.
- Si `estado_led_pon in [apagada,parpadeando] after wait_aprobado`: `n2/ont_sin_registro`. Derivar con estado PON registrado.
- Si `validacion_navegacion=si`: `resolved/servicio_restaurado`. Cerrar como resuelto por N1.
- Si `validacion_navegacion=no`: `n2/sin_servicio_post_n1`. Derivar con diagnóstico y acciones realizadas.

## Criterios de éxito

- Navegación confirmada en un dispositivo.
- Luces finales registradas.

## Contexto obligatorio para N2

- `tecnologia_servicio`
- `dispositivos_afectados`
- `tiempo_problema`
- `estado_incidente`
- `luces_equipo`
- `acciones_n1_realizadas`
- `resultado_validacion`

## Integraciones necesarias

- Estado de red/incidentes
- Estado administrativo
- Inventario CPE

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
