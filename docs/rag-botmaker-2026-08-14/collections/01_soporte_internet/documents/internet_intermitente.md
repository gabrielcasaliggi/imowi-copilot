---
id: blueprint-internet_intermitente
collection: 01_soporte_internet
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Cortes o intermitencia

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Soporte técnico
- Intenciones: cortes_intermitencia
- Casos históricos agregados: 3350

## Pasos N1

### 1. `estado_incidente`

Consultar incidentes activos automáticamente.

### 2. `dispositivos_afectados`

¿Los cortes afectan a uno, varios o todos los dispositivos?

- Opciones: uno, varios, todos

### 3. `medio_conexion`

¿Ocurre por Wi‑Fi, por cable o por ambos?

- Opciones: wifi, cable, ambos, no_puede_probar

### 4. `frecuencia_cortes`

¿Cada cuánto se corta y cuánto tarda en volver?

### 5. `luces_durante_corte`

Cuando se corta, ¿cambia o se apaga alguna luz del equipo?

### 6. `reinicio_controlado`

Si no hay alarma física ni incidente, aplicar reinicio aprobado.

### 7. `validacion_estabilidad`

¿La conexión se mantuvo estable durante el período de prueba aprobado?

- Opciones: si, no

## Reglas de decisión

- Si `estado_incidente=activo`: `inform/incidente_masivo`. Informar incidencia confirmada.
- Si `alarma_fisica=true`: `n2/alarma_acceso`. Derivar con luces y tecnología.
- Si `validacion_estabilidad=si`: `resolved/estable`. Cerrar como resuelto N1.
- Si `validacion_estabilidad=no`: `n2/intermitencia_persistente`. Derivar con frecuencia y pruebas.

## Criterios de éxito

- Conexión estable durante prueba definida.

## Contexto obligatorio para N2

- `tecnologia_servicio`
- `dispositivos_afectados`
- `tiempo_problema`
- `estado_incidente`
- `luces_equipo`
- `acciones_n1_realizadas`
- `resultado_validacion`

## Integraciones necesarias

- Estado de red
- Inventario CPE

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
