---
id: blueprint-internet
collection: 01_soporte_internet
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Enrutador de consultas de Internet

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Soporte técnico
- Intenciones: sin_internet, cortes_intermitencia, lentitud, wifi_conectividad
- Casos históricos agregados: 12529

## Pasos N1

### 1. `tipo_problema_internet`

¿Qué problema tenés: sin conexión, cortes, lentitud, Wi‑Fi o cambio de clave?

- Opciones: sin_conexion, cortes, lentitud, wifi, cambio_clave

### 2. `tecnologia_servicio`

¿Tu servicio es Fibra, ADSL o Inalámbrico?

- Opciones: ftth, adsl, radio, no_sabe

- Preguntar cuando: `tecnologia_no_disponible_en_sistema`

## Reglas de decisión

- Si `tipo_problema_internet=sin_conexion and tecnologia_servicio=ftth`: `route/ftth`. Continuar con internet_ftth.
- Si `tipo_problema_internet=sin_conexion and tecnologia_servicio=adsl`: `route/adsl`. Continuar con internet_adsl.
- Si `tipo_problema_internet=sin_conexion and tecnologia_servicio=radio`: `route/radio`. Continuar con internet_radio.
- Si `tipo_problema_internet=cortes`: `route/intermitencia`. Continuar con internet_intermitente.
- Si `tipo_problema_internet=lentitud`: `route/lentitud`. Continuar con internet_lento.
- Si `tipo_problema_internet=wifi`: `route/wifi`. Continuar con internet_wifi.
- Si `tipo_problema_internet=cambio_clave`: `route/clave_wifi`. Continuar con cambio_clave_wifi.

## Criterios de éxito

- Consulta derivada al flujo técnico correcto sin repetir preguntas.

## Contexto obligatorio para N2

- `tecnologia_servicio`
- `dispositivos_afectados`
- `tiempo_problema`
- `estado_incidente`
- `luces_equipo`
- `acciones_n1_realizadas`
- `resultado_validacion`

## Integraciones necesarias

- Inventario de tecnología del cliente

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
