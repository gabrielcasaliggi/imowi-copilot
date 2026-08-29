---
id: blueprint-internet_wifi
collection: 01_soporte_internet
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Cobertura o conexión Wi‑Fi

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Soporte técnico
- Intenciones: wifi_conectividad
- Casos históricos agregados: 1905

## Pasos N1

### 1. `red_visible`

¿La red Wi‑Fi aparece en el dispositivo?

- Opciones: si, no

### 2. `dispositivos_afectados`

¿Falla uno, varios o todos los dispositivos?

- Opciones: uno, varios, todos

### 3. `ubicacion_prueba`

¿También falla cerca del router?

- Opciones: si, no

### 4. `conexion_cableada`

¿Por cable hay navegación?

- Opciones: si, no, no_puede_probar

### 5. `repetidor_wifi`

¿Tiene repetidor/extensor? Si internet anda bien cerca del módem pero mal lejos, el repetidor puede recibir señal débil.

### 6. `repetidor_ubicacion`

Regla de media distancia: mover el repetidor a un enchufe más cerca del router (no en la zona sin señal). ¿Mejoró la señal?

### 7. `repetidor_cable_ap`

Si es posible, conectar repetidor al router con cable UTP (modo Punto de Acceso) para no perder velocidad.

### 8. `error_wifi`

¿Qué ocurre: clave incorrecta, no conecta o conecta sin Internet?

- Opciones: clave_incorrecta, no_conecta, sin_internet

### 9. `olvidar_red`

Aplicar guía aprobada para olvidar y volver a conectar la red.

- Preguntar cuando: `dispositivos_afectados=uno`

### 10. `validacion_wifi`

¿El dispositivo conectó y navega correctamente?

- Opciones: si, no

## Buenas prácticas domiciliarias

- Router/ONT elevado, ventilado, alejado de microondas, espejos, metal y peceras.
- Banda 2.4 GHz: más alcance, más interferencia. 5 GHz: más velocidad, menos alcance.
- Desconectar dispositivos IoT/Smart TV en standby que consumen airtime.
- Cambiar clave Wi‑Fi ~1 vez/año para sacar equipos viejos o vecinos colgados.

## Reglas de decisión

- Si `conexion_cableada=no`: `route/falla_general`. Volver al flujo internet según tecnología.
- Si `ubicacion_prueba=no and conexion_cableada=si`: `resolved/cobertura_wifi`. Informar limitación de cobertura y opciones aprobadas.
- Si `repetidor_ubicacion=si`: confirmar mejora; orientar prueba prolongada.
- Si `validacion_wifi=si`: `resolved/wifi_restaurado`. Cerrar resuelto N1.
- Si `validacion_wifi=no`: `n2/wifi_persistente`. Derivar con pruebas realizadas.

## Criterios de éxito

- Conexión y navegación Wi‑Fi confirmadas.

## Contexto obligatorio para N2

- `tecnologia_servicio`
- `dispositivos_afectados`
- `tiempo_problema`
- `estado_incidente`
- `luces_equipo`
- `acciones_n1_realizadas`
- `resultado_validacion`
- `error_wifi`
- `repetidor_presente`

## Integraciones necesarias

- Inventario CPE

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
