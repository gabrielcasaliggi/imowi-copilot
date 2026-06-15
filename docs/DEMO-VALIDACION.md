# Modo demo validación — imowi

Sesión estructurada para que operadores y NOC de imowi evalúen el copilot con **3 escenarios reproducibles**, guion paso a paso y checklist de feedback.

**Piloto operativo:** ver [PILOTO-IMOWI.md](./PILOTO-IMOWI.md) (Go/No-Go, métricas, roles).  
**Integración post-piloto:** ver [INTEGRACION_PILOTO.md](./INTEGRACION_PILOTO.md).

---

## Acceso

| Usuario | Contraseña | Uso |
|---------|------------|-----|
| `batan` | `batan` | Operador Cooperativa Batán (recomendado para validación) |
| `admin` | `admin` | Vista NOC global |

**Arranque local:** `./run.sh` o `uvicorn main:app --reload` → consola en http://localhost:3000 (frontend) o http://localhost:8000

---

## Panel en consola

En el sidebar derecho aparece **Validación imowi** y **Estado del piloto**:

- **Iniciar** — limpia la sesión de chat y envía el mensaje inicial del escenario.
- **Guion** — despliega los turnos que el operador debe escribir y qué esperar.
- **Reset demo** — borra casos conversacionales y tickets de la cooperativa activa (vuelve a empezar limpio).
- **Estado del piloto** — escenario activo, paso actual, pasos confirmados, ticket y métricas acumuladas.

También podés resetear por CLI:

```bash
./scripts/reset-demo-validacion.sh coop-batan
```

---

## Escenario 1 — Roaming Brasil

**Línea JSC demo:** `2235551234` · Samsung A54

| # | Escribir en el chat | Qué mirar |
|---|---------------------|-----------|
| 1 | `Cliente sin datos en Brasil, línea 2235551234, Samsung A54` | Ficha JSC, guía **Roaming internacional**, paso 1 |
| 2 | `verificado` | Paso 2 — APN de roaming |
| 3 | `ok` | Paso 3 — roaming en JSC |
| 4 | `no estaba activado el servicio de roaming` | Paso 4 — activar roaming en JSC |
| 5 | `activado en jsc` | Paso 5 — reinicio / modo avión |
| 6 | `hecho` | Paso 6 — prueba de llamada |
| 7 | Botón **Registrar ticket NOC** | Ticket JSC, timeline con eventos `paso_operativo` |

**Validar:** ¿Los pasos coinciden con el playbook de roaming? ¿El timeline es auditable?

---

## Escenario 2 — Sin datos local

**Línea JSC demo:** `2235560001` · Samsung A22 · Güemes

| # | Escribir en el chat | Qué mirar |
|---|---------------------|-----------|
| 1 | `Cliente sin datos móviles en Güemes, línea 2235560001, Samsung A22` | Categoría **Datos**, no mezcla roaming |
| 2 | `verificado` | Paso APN |
| 3 | `apn correcto` | Reinicio de red |
| 4 | `reiniciado` | Prueba de llamadas |
| 5 | `llamadas ok pero sin datos` | Descarte SIM |
| 6 | **Registrar ticket NOC** | Escalamiento con evidencia |

**Validar:** ¿Se distingue síntoma local vs itinerancia? ¿Hechos en la guía operativa?

---

## Escenario 3 — No registra en red

**Línea JSC demo:** `2235560002` · Samsung A22

| # | Escribir en el chat | Qué mirar |
|---|---------------------|-----------|
| 1 | `Línea 2235560002, síntoma no se registra en la red, Samsung A22` | Categoría **Señal**, pregunta por zona |
| 2 | `en varias zonas` | Prueba de llamadas |
| 3 | `no puede hacer llamadas` | Reinicio / modo avión |
| 4 | `hecho y sigue igual` | Escalar a NOC (sin saltar pasos) |
| 5 | **Registrar ticket NOC** | Ticket con motivo y timeline |

**Validar:** ¿Detecta “no se registra en la red” como señal? ¿Pide zona antes de NOC?

---

## Checklist feedback imowi

Marcar por escenario y al cierre de la sesión:

### Por escenario
- [ ] Utilidad de los pasos vs playbook actual
- [ ] Datos faltantes en ficha JSC o resumen NOC
- [ ] Timeline útil para cooperativa → NOC
- [ ] Sin deriva (KB irrelevante, DNI, pasos repetidos)

### General
- [ ] Claridad del panel **Guía operativa** (sidebar)
- [ ] Tiempo estimado N1 con copilot vs sin copilot
- [ ] ¿Lo integrarían en operación diaria?
- [ ] ¿Qué faltaría para producción? (JSC real, contable, SLA, etc.)

### Espacio para notas

| Escenario | Útil (1-5) | Faltante | Comentario |
|-----------|------------|----------|------------|
| Roaming Brasil | | | |
| Sin datos local | | | |
| No registra en red | | | |

---

## API (opcional)

```http
GET  /api/v1/demo/escenarios
GET  /api/v1/demo/metricas
POST /api/v1/demo/evento   {"tipo":"escenario_iniciado","session_id":"...","escenario_id":"roaming-brasil"}
POST /api/v1/demo/reset    {"incluir_tickets": true}
```

Requiere JWT de cooperativa (header `Authorization`).

---

## Relación con presentación comercial

Para demo de 10 min con stakeholders ver [DEMO-PRESENTACION.md](../DEMO-PRESENTACION.md).  
Este documento es para **validación operativa** con ingenieros y operadores N1.
