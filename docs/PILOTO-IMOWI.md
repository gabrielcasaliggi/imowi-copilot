# Piloto Operativo Imowi — Guía y criterio Go/No-Go

**Producto:** imowi Operations Hub — Piloto Operativo Controlado  
**Duración sugerida:** 2 semanas  
**Participantes:** 2–3 operadores N1 cooperativa + 1 referente NOC imowi

---

## Objetivo del piloto

Validar si el copilot **reduce incertidumbre del operador**, **estandariza pasos N1** y **entrega tickets NOC auditables** — sin reemplazar JSC ni contable.

---

## Preparación (día 0)

1. Login operador: `batan` / `batan`
2. Ejecutar reset: botón **Reset demo** o `./scripts/reset-demo-validacion.sh coop-batan`
3. Verificar panel **Validación imowi** y **Estado del piloto** en sidebar
4. Repasar guion: [DEMO-VALIDACION.md](./DEMO-VALIDACION.md)

---

## Sesión guiada (90 min)

| Bloque | Duración | Actividad |
|--------|----------|-----------|
| Intro | 10 min | Mensaje: no reemplaza JSC; unifica operación |
| Escenario 1 | 25 min | Roaming Brasil — seguir guion turno a turno |
| Escenario 2 | 20 min | Sin datos local |
| Escenario 3 | 20 min | No registra en red |
| Debrief | 15 min | Checklist + métricas |

Entre escenarios: **Reset demo** para estado limpio.

---

## Qué observar en cada escenario

### Durante el chat
- ¿Aparece la **Guía operativa** con el paso correcto?
- ¿La **Ficha JSC** aporta APN / roaming / cuenta?
- ¿El bot **no pide DNI, portabilidad ni KB irrelevante**?
- ¿Las confirmaciones (`verificado`, `ok`) avanzan el paso?

### Al escalar
- Botón **Registrar ticket NOC**
- Ticket con ID `JSC-xxxx`
- **Historial del ticket** con eventos `paso_operativo`
- Resumen NOC antes del cierre de flujo

### Panel Estado del piloto
- Escenario activo
- Pasos confirmados (contador)
- Ticket y estado

---

## Métricas del piloto

Consultar vía API o panel sidebar:

```
GET /api/v1/demo/metricas
```

| Métrica | Meta piloto |
|---------|-------------|
| Escenarios iniciados | ≥ 3 (uno por tipo) |
| Pasos confirmados | ≥ 12 total |
| Tickets NOC creados | ≥ 3 |
| Resets | según sesiones |

Eventos registrados automáticamente:
- `escenario_iniciado` — al pulsar Iniciar
- `paso_confirmado` — cada paso operativo confirmado
- `ticket_creado` — escalamiento NOC
- `reset_demo` — limpieza entre escenarios

---

## Checklist feedback (completar con imowi)

### Por escenario

| Pregunta | Roaming | Datos | Señal |
|----------|---------|-------|-------|
| Pasos correctos vs playbook (1-5) | | | |
| Ficha JSC útil (1-5) | | | |
| Timeline auditable (1-5) | | | |
| Sin deriva conversacional | | | |

### General
- [ ] ¿Lo usarían en operación diaria?
- [ ] ¿Qué dato falta en JSC/contable?
- [ ] ¿El resumen NOC es accionable?
- [ ] Tiempo estimado vs proceso actual
- [ ] Comentarios libres: _______________

---

## Criterio Go / No-Go

### Go — Piloto extendido (30–45 días)

Se cumplen **al menos 4 de 5**:

1. **Playbooks:** imowi confirma que pasos roaming/datos/señal son correctos o ajustables en < 1 semana
2. **Tickets:** ≥ 80% de escalamientos incluyen timeline con pasos N1
3. **Operadores:** al menos 2/3 operadores califican utilidad ≥ 4/5
4. **NOC:** referente confirma que resumen NOC ahorra retrabajo
5. **Estabilidad:** sin deriva crítica (DNI, KB random, pasos repetidos) en ≥ 90% de turnos

**Siguiente paso:** ver [INTEGRACION_PILOTO.md](./INTEGRACION_PILOTO.md) — sandbox JSC + staging.

### No-Go — Iterar MVP

- Pasos N1 no coinciden con operación real y requieren rediseño mayor
- Tickets NOC llegan sin evidencia útil
- Deriva conversacional frecuente sin workaround
- Operadores prefieren proceso manual actual

**Siguiente paso:** ajustar playbooks en `flujos_operativos.py`, repetir piloto 1 semana.

### Condicional — Go con condiciones

- Go si imowi provee acceso JSC sandbox en 2 semanas
- Go limitado a 1 cooperativa hasta integrar contable

---

## Roles en la sesión

| Rol | Responsabilidad |
|-----|-----------------|
| Facilitador Vertia | Guion, reset, captura feedback |
| Operador coop | Ejecuta escenarios como N1 real |
| Referente NOC imowi | Valida ticket, timeline, escalamiento |
| Observador (opcional) | Toma notas checklist |

---

## Entregables post-piloto

1. Tabla checklist completada
2. Export métricas (`GET /api/v1/demo/metricas`)
3. Lista brechas integración ([INTEGRACION_PILOTO.md](./INTEGRACION_PILOTO.md))
4. Decisión Go / No-Go / Condicional firmada por referente imowi

---

## Comandos útiles

```bash
# Backend
./run.sh

# Frontend
cd frontend && npm run dev

# Reset demo
./scripts/reset-demo-validacion.sh coop-batan

# Tests piloto
PYTHONPATH=. .venv/bin/pytest tests/test_piloto_*.py tests/test_blindar_flujos.py -q
```
