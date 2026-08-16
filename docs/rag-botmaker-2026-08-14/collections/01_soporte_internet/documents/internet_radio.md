---
id: blueprint-internet_radio
collection: 01_soporte_internet
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Sin Internet — Inalámbrico/Radio

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Soporte técnico
- Intenciones: sin_internet
- Casos históricos agregados: 6255

## Pasos N1

### 1. `estado_incidente`

Consultar automáticamente si existe una incidencia en la zona/nodo.

### 2. `dispositivos_afectados`

¿El problema ocurre en un dispositivo, en varios o en todos?

- Opciones: uno, varios, todos

### 3. `tiempo_problema`

¿Desde cuándo estás sin servicio?

### 4. `energia_poe`

¿El inyector/fuente de la antena y el router tienen energía?

- Opciones: si, no, no_sabe

### 5. `cables_poe`

¿Los cables de energía y red están firmes y sin daño visible? No desconectes el cable de la antena si no está identificado.

- Opciones: si, no, no_sabe

### 6. `luces_router`

¿Qué estado muestran POWER, WAN/Internet y Wi‑Fi en el router?

### 7. `estado_cpe`

Consultar automáticamente si la antena/CPE está en línea y con señal válida.

### 8. `reinicio_previo`

¿Ya realizaste un reinicio desde que empezó el problema?

- Opciones: si, no

### 9. `reinicio_controlado`

Aplicar únicamente el procedimiento de reinicio aprobado para CPE y router.

- Preguntar cuando: `reinicio_previo=no and estado_cpe!=alarma_fisica`

### 10. `validacion_navegacion`

Después de estabilizar los equipos, ¿ya podés navegar?

- Opciones: si, no

## Reglas de decisión

- Si `estado_incidente=activo`: `inform/incidente_nodo`. Informar estado confirmado de incidencia.
- Si `energia_poe=no after toma_verificada`: `n2/equipo_sin_energia`. Derivar posible fuente/PoE.
- Si `estado_cpe in [offline,senal_fuera_parametro]`: `n2/cpe_radio`. Derivar con telemetría disponible.
- Si `validacion_navegacion=si`: `resolved/servicio_restaurado`. Cerrar como resuelto por N1.
- Si `validacion_navegacion=no`: `n2/sin_servicio_post_n1`. Derivar con diagnóstico completo.

## Criterios de éxito

- CPE/router estabilizados y navegación confirmada.

## Contexto obligatorio para N2

- `tecnologia_servicio`
- `dispositivos_afectados`
- `tiempo_problema`
- `estado_incidente`
- `luces_equipo`
- `acciones_n1_realizadas`
- `resultado_validacion`
- `energia_poe`
- `estado_cpe`

## Integraciones necesarias

- Estado de nodos/incidentes
- Telemetría CPE radio
- Inventario CPE

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
