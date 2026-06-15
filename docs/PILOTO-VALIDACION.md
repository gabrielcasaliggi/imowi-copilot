# Matriz de validación piloto — post-estabilización

Matriz para validar la versión **pilot-ready** con persistencia Postgres, frontend Next.js y flujo v3.

Relacionado: [PILOTO-IMOWI.md](./PILOTO-IMOWI.md) · [PRODUCCION-SUPABASE.md](./PRODUCCION-SUPABASE.md)

---

## Pre-requisitos

- [ ] `/health` → `database: postgresql`, `database_connected: true`
- [ ] Frontend Next.js con `NEXT_PUBLIC_API_URL` apuntando a Render
- [ ] `CORS_ORIGINS` incluye URL del frontend
- [ ] Login operador (`batan`) y admin (`admin`) funcionan

Verificación rápida:

```bash
./scripts/verify-production.sh https://tu-api.onrender.com
VERIFY_USER=batan VERIFY_PASSWORD=batan ./scripts/verify-production.sh https://tu-api.onrender.com
```

---

## Matriz de escenarios (12)

| # | Escenario | Mensaje inicial (ejemplo) | Qué validar | Persistencia |
|---|-----------|---------------------------|-------------|--------------|
| 1 | Roaming exterior | «Cliente sin datos en Brasil, línea 2235551234» | Flujo `roaming`, paso datos/itinerancia | Recargar → caso/ticket sigue |
| 2 | Roaming Uruguay | «Sin datos en Uruguay, línea 2235402690» | Categoría roaming, no repetir paso 1 | Idem |
| 3 | Datos local | «Sin datos móviles en Güemes, línea 2235560001» | Flujo `datos`, APN | Idem |
| 4 | Llamadas OK, datos no | «Puede llamar pero WhatsApp no carga» | `llamadas_ok` sin marcar `datos_ok` | Idem |
| 5 | Señal / red | «No registra en red, línea 2235560002» | Flujo señal, pasos cobertura | Idem |
| 6 | SIM / eSIM | «Cambió el chip y no conecta» | Categoría SIM, no pedir DNI | Idem |
| 7 | Persistencia post-N1 | Tras playbook completo: «sigue igual, no funciona» | Escalado `crear_ticket_n2`, aviso ticket | Ticket en `tickets_estate` |
| 8 | Consulta ticket | «¿creaste el ticket?» / «pasame el número» | Intención `estado_ticket`, ID en respuesta | — |
| 9 | Corrección operador | «No es así, el usuario sigue con problemas» | No cerrar caso, retomar guía | — |
| 10 | Confirmación paso | «verificado» / «APN ok» | Avanza paso operativo | Timeline eventos |
| 11 | Multitenancy | Login `batan` vs `viamonte` | Tickets aislados por org | Solo ve sus tickets |
| 12 | Admin NOC | Login `admin`, cambio de tenant | Vista global, stats, telemetría | Datos por org |

---

## Criterios por escenario

### Durante el chat
- Guía operativa muestra paso correcto
- No pide DNI/portabilidad fuera de contexto
- Ficha JSC aporta contexto (si línea en réplica)
- Variantes informales/técnicas entendidas

### Al escalar
- Aviso explícito: «Registré el ticket JSC-xxxx»
- Nivel N1 o N2 según regla
- Timeline con pasos N1 en historial del ticket

### Post-recarga (persistencia)
- Tickets listados en sidebar
- Caso conversacional retomable
- En Supabase Table Editor: filas en `tickets_estate`, `casos_conversacion`

---

## Métricas a capturar

| Métrica | Fuente | Meta piloto |
|---------|--------|-------------|
| Tickets creados | `/api/v1/analytics/tickets` o Supabase | ≥ 3 en sesión |
| Escalados N2 | tickets con `nivel=N2` | ≥ 1 |
| Resueltos en N1 | sin ticket, flujo completado | registrar manual |
| Consultas estado ticket | chat logs | responde con ID |
| Errores DB | Render logs / `/health` | 0 degradado |

---

## Tests automatizados

```bash
.venv/bin/python -m pytest \
  tests/test_matriz_piloto.py \
  tests/test_piloto_escenarios_e2e.py \
  tests/test_dialogo_variantes.py \
  tests/test_blindar_flujos.py \
  tests/test_health_endpoint.py \
  -q
```

---

## Go / No-Go (resumen)

**Go** si ≥ 10/12 escenarios pasan manualmente y tests en verde.

**No-Go** si persistencia falla tras recarga o tickets duplicados/inválidos.

Ver criterio completo en [PILOTO-IMOWI.md](./PILOTO-IMOWI.md).
