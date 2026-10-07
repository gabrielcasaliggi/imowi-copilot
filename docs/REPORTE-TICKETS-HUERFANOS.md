# Reporte de tickets huérfanos (H26)

`scripts/reporte_tickets_huerfanos.py` lista los tickets **abiertos creados por Eko** (origen `Portal`, `App`, `Canal` o `WhatsApp`) que **ninguna conversación de canal tiene ligados**
(`conversaciones_canal.ticket_id`). Son los casos en que el abonado espera una respuesta que la consola no puede mostrar (solo «Sin conversación de canal»), como los que producía H24.

## Garantías

- **Solo lectura**: únicamente `SELECT`. La sesión se abre en modo de solo lectura (`SET TRANSACTION READ ONLY` en PostgreSQL, `PRAGMA query_only` en SQLite) y termina con `rollback`; el script no tiene escrituras.
- **Con tope de tiempo**: `statement_timeout` en PostgreSQL (`--timeout`, 15 s por defecto).
- **Sin datos personales**: la línea del ticket y el teléfono de la conversación salen enmascarados (`***123`, solo los últimos 3 dígitos). No imprime nombres, DNI ni texto de la falla.

## Cómo correrlo (en el servidor, con el entorno de la API)

```bash
cd /ruta/del/repo
.venv/bin/python scripts/reporte_tickets_huerfanos.py --org coop-batan            # texto
.venv/bin/python scripts/reporte_tickets_huerfanos.py --org coop-batan --json     # JSON
```

Usa el `DATABASE_URL` del entorno (el mismo de la API). Sin `--org` recorre todas las organizaciones.

## Qué muestra

1. **Tickets abiertos de Eko sin conversación ligada**: `id`, fecha de creación, `nivel`, `destino`, `estado`, `origen`, línea enmascarada y antigüedad (más viejo primero).
2. **Informativo**: conversaciones en `espera_agente`/`con_agente` sin `ticket_id` (puede ser la cola legítima de visitantes anónimos o un hilo desligado): `id`, canal, estado, teléfono enmascarado y antigüedad.

Un ticket de la sección 1 no se cierra ni se re-liga desde el script: se revisa a mano en la consola. Test: `tests/test_reporte_tickets_huerfanos.py`.
