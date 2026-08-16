---
id: blueprint-cobertura
collection: 03_comercial_administracion
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Consultar cobertura o contratar servicio

> Borrador derivado de patrones agregados. No habilitar en producción sin aprobación humana.

## Objetivo y alcance

- Área: Comercial
- Intenciones: cobertura_contratacion
- Casos históricos agregados: 932

## Pasos N1

### 1. `cobertura_contratacion_detalle`

¿Buscás cobertura, planes disponibles o seguimiento de instalación?

### 2. `accion_1`

Consultar cobertura y oferta vigentes; no prometer disponibilidad sin sistema.

### 3. `validacion_resultado`

Confirmar siguiente paso: sin cobertura, oferta disponible o solicitud registrada. ¿La gestión quedó resuelta?

- Opciones: si, no

## Reglas de decisión

- Si `validacion_resultado=si`: `resolved/gestion_confirmada`. Cerrar como resuelto por N1.
- Si `validacion_resultado=no`: `n2/gestion_no_resuelta`. Derivar con datos y acciones N1.
- Si `condicion_confirmada`: `n2/n2_1`. Dirección dudosa, obra especial, excepción comercial o instalación demorada.

## Criterios de éxito

- Confirmar siguiente paso: sin cobertura, oferta disponible o solicitud registrada.

## Contexto obligatorio para N2

- `motivo_consulta`
- `datos_relevantes`
- `acciones_n1_realizadas`
- `resultado_validacion`

## Integraciones necesarias

- Mapa de cobertura
- Catálogo vigente
- Alta de prospecto

## Gate de publicación

- [ ] Privacidad validada
- [ ] Flujo confirmado por responsables N1/N2
- [ ] Integraciones y mensajes probados
- [ ] Criterios de derivación aprobados
- [ ] Aprobado para RAG productivo
