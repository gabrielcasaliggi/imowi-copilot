# Uso local — Modo producto operativo

Consola **imowi Operations Hub** en entorno local con réplica JSC (SQLite). Se comporta como producción: el operador atiende reclamos reales por chat, sin escenarios ni botones de demo.

---

## Arranque

```bash
# Terminal 1 — API
./run.sh

# Terminal 2 — Frontend
cd frontend && npm run dev
```

- Frontend: http://localhost:3000  
- API: http://localhost:8000  

Login operador: **`batan` / `batan`**

---

## Atender un reclamo

1. Entrá a **Consola de Soporte**
2. Escribí el caso en lenguaje natural, por ejemplo:

   ```
   Cliente sin datos en Brasil, línea 2235551234, Samsung A54
   ```

3. Seguí la **Guía operativa** del sidebar (pasos N1 por categoría)
4. Confirmá cada paso con respuestas cortas: `verificado`, `ok`, `revisado`, `no navega`, etc.
5. Cuando corresponda, **Registrar ticket NOC**

### Líneas disponibles en réplica local (Coop Batán)

| Línea | Uso típico |
|-------|------------|
| 2235551234 | Roaming, línea activa |
| 2235560001 | Datos móviles local |
| 2235560002 | Señal / registro en red |
| 2235559012 | Línea suspendida + deuda |

---

## Paneles del sidebar

| Panel | Función |
|-------|---------|
| Caso activo | Línea, estado, ticket vinculado |
| Estado operativo | Paso N1 actual y pasos confirmados |
| Guía operativa | Playbook determinístico (sin IA) |
| Ficha JSC | Abonado, plan, APN, roaming, cuenta |
| Ticket en formación | Detalle y timeline |
| Notificaciones | Novedades del NOC |

---

## Reglas operativas

- **Un caso por línea móvil** — si cambiás de línea, usá **Nuevo reclamo**
- El motor prioriza **flujo operativo** sobre KB/IA mientras hay pasos pendientes
- Los tickets quedan con **timeline auditable** (eventos `paso_operativo`)

---

## NOC (admin)

Login: **`admin` / `admin`**

- Vista global por cooperativa
- Actualización de tickets escalados
- Monitor de red y estadísticas

---

## Limpieza de datos (solo desarrollo)

Para vaciar casos y tickets entre pruebas locales (no es operación productiva):

```bash
./scripts/reset-demo-validacion.sh coop-batan
```

O borrá la base SQLite y reiniciá:

```bash
rm -f data/estate.db
./run.sh
```

El seed vuelve a cargar organizaciones, KB, telemetría y catálogo JSC local.

---

## Réplica JSC vs producción

| Local hoy | Producción |
|-----------|------------|
| SQLite `lineas_jsc` (seed) | API JSC o sync periódico |
| Tickets en SQLite | Supabase / NOC externo |
| LLM local (Ollama) o Groq | Groq / proveedor acordado |

Ver [INTEGRACION_PILOTO.md](./INTEGRACION_PILOTO.md) para contratos de integración.

---

## Herramientas internas (no visibles en UI)

Endpoints `/api/v1/demo/*` y scripts de reset se mantienen para tests y desarrollo. No forman parte de la experiencia del operador.
