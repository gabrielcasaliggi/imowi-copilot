# Integración JSC — Contrato y plan de migración

## Cuándo integrar

**Después** de validar el piloto con matriz [PILOTO-VALIDACION.md](./PILOTO-VALIDACION.md). No bloquear el piloto por JSC real: la réplica demo (`lineas_jsc`) y tickets en `tickets_estate` alcanzan para validar flujo N1/N2.

---

## Objetivo

Reemplazar la réplica demo por datos reales del sistema JSC (altas, bajas, modificaciones, consumos) y, en fase 2, sincronizar tickets N1/N2 con ticketeras externas.

---

## Contrato de línea

Definido en `app/jsc/contract.py` → `FichaLineaJSC`.

| Campo | Uso en plataforma |
|-------|-------------------|
| `msisdn` | Identificación en triaje y tickets |
| `abonado` | Contexto en descripción |
| `plan` | Diagnóstico y categorización |
| `estado_linea` | Bloquear escalamiento si suspendida |
| `iccid` | Derivación SIM/eSIM |
| `apn` | Troubleshooting datos |
| `estado_cuenta` | Resolver en N1 antes de escalar |
| `roaming_habilitado` | Validar casos roaming |

## Interfaz `JSCProvider`

```python
class JSCProvider(Protocol):
    def buscar_linea(org_id, msisdn) -> FichaLineaJSC | None
    def listar_lineas(org_id, limit) -> list[FichaLineaJSC]
    def buscar(org_id, query) -> list[FichaLineaJSC]
```

Implementación actual: `app/jsc/connector.py` (SQLite/Postgres seed).

---

## Contrato de ticket (fase 2)

`TicketJSCPayload` en `app/jsc/contract.py` — mapeo desde `tickets_estate`:

| Campo interno | Campo JSC sugerido | Notas |
|---------------|-------------------|-------|
| `id` | `ticket_externo_id` / referencia | JSC-1001 local → ID remoto |
| `linea` | `msisdn` | Obligatorio |
| `descripcion_falla` | `descripcion` | Texto operador |
| `nivel` | `nivel` (N1/N2) | Ticketera destino |
| `destino` | `area` | cooperativa / imowi_noc |
| `proveedor` | `proveedor` | Carrier, SIM, etc. |
| `acciones_n1_realizadas` | `evidencia_n1` | Timeline resumido |
| `motivo_escalamiento` | `motivo` | Por qué escaló |
| `categoria` | `tipo_incidencia` | Roaming, Datos, Señal… |
| `creado_por` | `operador` | Usuario cooperativa |
| `organizacion_id` | `cooperativa_id` | Mapear slug → ID JSC |

Función: `mapear_ticket_a_jsc(ticket, org_nombre) -> TicketJSCPayload`.

---

## Información a solicitar a imowi

Checklist para reunión de integración:

- [ ] URL base API JSC (sandbox y producción)
- [ ] Método de autenticación (API key, OAuth, mTLS)
- [ ] Endpoint consulta línea por MSISDN
- [ ] Endpoint alta ticket N1 cooperativa
- [ ] Endpoint escalamiento a N2 / NOC
- [ ] Formato de ID de ticket y estados válidos
- [ ] Webhooks o polling para actualizaciones de estado
- [ ] Límites de rate y horarios de mantenimiento
- [ ] Ejemplos JSON reales (request/response) anonimizados
- [ ] Mapeo cooperativa slug → ID en JSC

---

## Fases de implementación

### Fase 0 — Actual (piloto)
- `JSC_PROVIDER=demo`
- Seed en `app/estate/seed.py`
- Tickets solo en `tickets_estate`

### Fase 1 — Lectura live
- `JSCProviderHTTP` consulta línea en tiempo real
- Validación suave: si no está en JSC, seguir flujo (ya implementado)
- Caché opcional en `lineas_jsc`

### Fase 2 — Escritura sandbox
- Crear ticket N1 en JSC sandbox al escalar desde cooperativa
- Guardar `ticket_externo_id` en `tickets_estate`
- Modo `JSC_WRITE_MODE=sandbox`

### Fase 3 — Producción
- Escritura N2 hacia NOC / proveedor según reglas del clasificador
- Reconciliación de estados (cerrado, en revisión)
- Alertas si sync falla

---

## Configuración prevista

```env
JSC_PROVIDER=demo|http|sync
JSC_API_URL=
JSC_API_KEY=
JSC_WRITE_MODE=off|sandbox|production
JSC_SYNC_INTERVAL_MINUTES=60
```

Variables documentadas; implementación HTTP pendiente de contrato real de imowi.

---

## Endpoints API sugeridos (JSC externo)

- `GET /lineas/{msisdn}` — ficha de línea
- `GET /lineas?org={org_id}` — catálogo por organización
- `GET /lineas/search?q={query}` — búsqueda
- `POST /tickets` — alta ticket N1
- `POST /tickets/{id}/escalar` — paso a N2
- `GET /tickets/{id}` — consulta estado
- `POST /sync/lineas` — sincronización batch

---

## Criterio de listo para Fase 1

1. Piloto Go según [PILOTO-IMOWI.md](./PILOTO-IMOWI.md)
2. Acceso sandbox JSC con MSISDN de prueba
3. Documentación API de imowi con ejemplos
4. Acuerdo de campos obligatorios para ticket N1
