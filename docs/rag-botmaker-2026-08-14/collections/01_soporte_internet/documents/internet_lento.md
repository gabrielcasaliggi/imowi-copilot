---
id: blueprint-internet_lento
collection: 01_soporte_internet
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Baja velocidad

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Soporte técnico
- Intenciones: lentitud
- Casos históricos agregados: 1019

## Pasos N1

### 1. `estado_incidente`

Consultar incidentes activos automáticamente.

### 2. `plan_contratado`

Consultar automáticamente plan y velocidad contratada.

### 3. `dispositivos_afectados`

¿La lentitud afecta a uno, varios o todos los dispositivos?

- Opciones: uno, varios, todos

### 4. `medio_prueba`

¿La prueba fue por cable o Wi‑Fi?

- Opciones: cable, wifi, no_puede_probar

### 5. `distancia_wifi`

¿Estás cerca del router y sin obstáculos importantes?

- Opciones: si, no

- Preguntar cuando: `medio_prueba=wifi`

### 6. `resultado_medicion`

Realizá la medición con el procedimiento aprobado e indicá bajada, subida y latencia.

### 7. `uso_simultaneo`

¿Había descargas, streaming u otros equipos usando la conexión durante la prueba?

- Opciones: si, no, no_sabe

### 8. `segunda_medicion`

Repetí la prueba en condiciones controladas. ¿Mejoró?

- Opciones: si, no

## Reglas de decisión

- Si `estado_incidente=activo`: `inform/incidente_masivo`. Informar incidencia confirmada.
- Si `medio_prueba=wifi and cable_ok`: `resolved/cobertura_wifi`. Continuar con internet_wifi si necesita optimización.
- Si `segunda_medicion=si`: `resolved/medicion_normalizada`. Cerrar con recomendaciones aprobadas.
- Si `segunda_medicion=no and medicion_valida_fuera_parametro`: `n2/velocidad_fuera_parametro`. Derivar con ambas mediciones.

## Criterios de éxito

- M
- e
- d
- i
- c
- i
- ó
- n
-  
- v
- á
- l
- i
- d
- a
-  
- a
- c
- o
- r
- d
- e
-  
- a
- l
-  
- p
- l
- a
- n
-  
- o
-  
- c
- a
- u
- s
- a
-  
- W
- i
- ‑
- F
- i
-  
- i
- d
- e
- n
- t
- i
- f
- i
- c
- a
- d
- a
- .

## Contexto obligatorio para N2

- `tecnologia_servicio`
- `dispositivos_afectados`
- `tiempo_problema`
- `estado_incidente`
- `luces_equipo`
- `acciones_n1_realizadas`
- `resultado_validacion`
- `plan_contratado`
- `resultado_medicion`

## Integraciones necesarias

- Plan contratado
- Estado de red
- Servidor de medición aprobado

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
