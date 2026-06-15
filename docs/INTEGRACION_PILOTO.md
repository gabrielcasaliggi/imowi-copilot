# Integración post-piloto — Contratos mínimos

Documento de referencia para la conversación con imowi **después** del piloto operativo controlado. Define qué datos reales se necesitan para pasar de demo a integración.

---

## Principio

JSC y el sistema contable siguen siendo **sistemas maestro**. imowi Operations Hub consume datos, guía N1 y escala al NOC con trazabilidad. No reemplaza billing ni provisión.

---

## 1. JSC — Línea y abonado

**Contrato actual (demo):** [`app/jsc/contract.py`](../app/jsc/contract.py) → `FichaLineaJSC`

| Campo demo | Campo real esperado | Uso en copilot |
|------------|---------------------|----------------|
| `msisdn` | MSISDN / línea | Triaje, ticket, memoria por línea |
| `abonado` | Nombre titular | Contexto ticket NOC |
| `plan` | Plan comercial | Diagnóstico y categoría |
| `estado_linea` | Activa / Suspendida / Baja | Bloqueo escalamiento si suspendida |
| `iccid` | ICCID / eSIM | Derivación SIM |
| `apn` | APN configurado | Troubleshooting datos |
| `roaming_habilitado` | Sí / No | Flujo roaming internacional |
| `estado_cuenta` | Al día / Deuda / Revisar | Resolver N1 antes de red |
| `saldo_resumen` | Saldo o deuda | Alerta operador |

**Endpoints sugeridos (fase live):**

```
GET  /lineas/{msisdn}
GET  /lineas?org={org_id}&limit={limit}
GET  /lineas/search?q={query}
POST /sync/lineas          # batch nocturno opcional
```

**Gap demo → real:**

| Demo hoy | Producción |
|----------|------------|
| SQLite `lineas_jsc` seed | API JSC o sync periódico |
| 8 líneas Batán/Viamonte | Catálogo completo por cooperativa |
| `estado_cuenta` estático | Consulta contable en tiempo real o cache |

---

## 2. Sistema contable

**No integrado en demo.** Solo reflejado en `estado_cuenta` y `saldo_resumen` de la ficha JSC.

| Dato mínimo | Uso |
|-------------|-----|
| Estado administrativo (al día / deuda / mora) | Decisión N1: cobranza vs red |
| Saldo / monto adeudado | Mensaje al operador antes de escalar |
| Fecha último pago (opcional) | Contexto en ticket |

**Contrato sugerido:**

```
GET /cuentas/{msisdn}/estado
→ { estado: "Deuda", saldo: -2800, moneda: "ARS", ultimo_pago: "2026-01-15" }
```

**Regla operativa acordada en piloto:** si `estado_cuenta != Al día`, el copilot debe advertir antes de escalar a red/NOC.

---

## 3. NOC / Tickets

**Demo hoy:** tickets en SQLite (`tickets_estate`) + timeline (`ticket_events`) + notificaciones locales.

| Operación demo | Operación real esperada |
|----------------|-------------------------|
| Crear ticket JSC-xxxx local | POST ticket en sistema NOC imowi |
| Timeline `paso_operativo` | Comentarios / audit log en ticket externo |
| Notificación consola | Email / webhook / cola NOC |
| Update estado N1/N2 | PATCH estado + proveedor + SLA |

**Contrato mínimo ticket saliente:**

```json
{
  "linea": "2235551234",
  "categoria": "Roaming",
  "nivel": "N2",
  "destino": "imowi_noc",
  "descripcion_falla": "...",
  "evidencia": "pasos N1 confirmados",
  "acciones_n1_realizadas": "...",
  "origen": "Copilot Operador"
}
```

**Campos que el piloto ya genera y deben mapearse:**

- `acciones_n1_realizadas` — hechos del flujo operativo
- `motivo_escalamiento` — paso `*_cerrar_seguimiento` o forzar NOC
- `evidencia` — resumen construido en `seguimiento_ticket.py`
- Eventos timeline — uno por paso confirmado (`paso_operativo`)

---

## 4. Base de conocimiento

| Demo | Producción |
|------|------------|
| KB tenant en SQLite + RAG Markdown global | KB curada por cooperativa + artículos imowi |
| `Base_de_Conocimiento_Tickets.md` (51k líneas) | Subset indexado por categoría/ticket type |

**Recomendación post-piloto:** indexar solo artículos validados por NOC; desactivar RAG global durante flujo operativo activo (ya implementado parcialmente).

---

## 5. Telemetría / Red

| Demo | Producción |
|------|------------|
| `network_elements` seed + simulación | SNMP / OSS / alarmas Movistar |
| Ticket autónomo predictivo | Integración con monitor real |

---

## 6. Checklist de readiness integración

Antes de piloto extendido (30–45 días), imowi debe confirmar:

- [ ] Acceso API JSC (sandbox o export)
- [ ] Campo `estado_cuenta` confiable o API contable
- [ ] Formato ticket NOC destino (JSC nativo vs sistema propio)
- [ ] Playbooks N1 validados (roaming, datos, señal)
- [ ] Usuarios LDAP / SSO cooperativas (opcional fase 2)
- [ ] Entorno staging dedicado (no SQLite demo)

---

## Referencias en código

| Área | Archivo |
|------|---------|
| Contrato JSC | `app/jsc/contract.py` |
| Conector demo | `app/jsc/connector.py` |
| Bridge tickets | `app/services/ticket_bridge.py` |
| Timeline pasos | `app/services/seguimiento_ticket.py` |
| Flujos N1 | `app/domain/flujos_operativos.py` |
| Métricas piloto | `app/services/piloto_metricas.py` |
