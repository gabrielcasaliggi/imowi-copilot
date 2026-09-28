# EKO 2.8 — Invoice Headers Home

## Objetivo

El Home de la app muestra las cabeceras FC que el chat ya lee con `show_invoice` / `read_invoices_fc`. El saldo sigue saliendo de `GET /portal/customer-summary`.

## Endpoint

`GET /api/v1/portal/invoices`

Autenticación: la misma del portal (`_portal_auth`). Sin sesión, 401. Sesión no identificada, 403.

## Identidad

El `client_number` es el del abonado que resuelve el JWT (`_abonado_portal_identificado`). El endpoint no acepta cuenta, DNI ni id en el query.

Si ese `client_number` está vacío, responde HTTP 200:

```json
{
  "status": "unavailable",
  "reason_code": "missing_client_number",
  "invoices": []
}
```

En ese caso no llama a `read_invoices_fc`.

## Query contract

El único parámetro permitido es `limit`.

Cualquier otra clave (`client_number`, `dni`, `account_number`, `abonado_id`, `foo`, …) responde HTTP 400 y no lee BillTrack.

`limit` usa la pinza de `read_invoices_fc`: default 5, mínimo 1, máximo 20. Un valor que no es entero cae en 5. `0` y los negativos quedan en 1.

## Response contract

HTTP 200 en los casos de negocio. Cuerpo:

```json
{
  "status": "ok | empty | unavailable | error",
  "reason_code": null,
  "invoices": []
}
```

Cada ítem, y nada más:

* `invoice_number`
* `full_type`
* `amount`
* `issued_at` (ISO-8601 del reader, o `null`)
* `status`

No se envían `due_date`, `period`, `currency`, PDF, líneas, `client_number`, `account_number` ni id interno. La proyección no usa `InvoiceHeader.to_dict()`.

## BillTrack

`evaluar_facturas_portal` llama a `read_invoices_fc` con el `client_number` del abonado y el `limit` ya pinzado. No hay otro SQL ni otra conexión.

## Error handling

| Reader | Respuesta |
|---|---|
| `ok` | `status: ok` y la lista proyectada |
| `empty` | `status: empty`, `reason_code: no_fc_invoices`, `invoices: []` |
| `unavailable` | `status: unavailable`, `invoices: []` |
| `error` | `status: error`, `invoices: []` |

Un fallo de BillTrack no se devuelve como `ok` ni como lista inventada.

## Home

`useInvoices` llama a `getInvoices` sin query de identidad. `InvoiceHeadersSection` es independiente de `BalanceCard`.

Estados:

* **loading:** «Cargando facturas…»
* **success:** número, tipo (`full_type`), importe (`formatMontoDisplay`) y estado tal cual
* **empty:** «No encontramos facturas recientes en tu cuenta.»
* **unavailable/error:** «No pudimos consultar tus facturas ahora.» y Reintentar

Si las facturas fallan, el saldo no se oculta. Los links de Oficina Virtual siguen en `BalanceCard`.

## Fecha de emisión

`issued_at` se muestra con `formatInvoiceIssuedAt`.

Esa función toma el día calendario `AAAA-MM-DD` del string que llegó del backend y lo escribe `dd/mm/aaaa`. No usa `formatTicketWhen` ni la zona horaria del dispositivo.

`2026-09-01T00:00:00+00:00` se ve `01/09/2026`, el mismo día que el chat arma con `strftime("%d/%m/%Y")` sobre ese valor. Lo mismo para `2026-09-15` y `2026-12-31`. Un offset distinto no mueve el día escrito en el string: `2026-09-01T00:00:00-03:00` también es `01/09/2026`.

Si no hay fecha, o no es un día calendario, la fila no muestra «Emitida».

## Seguridad

Un query con identidad ajena es HTTP 400 antes de `read_invoices_fc`. El reader, cuando corre, filtra por el `client_number` del abonado autenticado.

## Tests

* `tests/test_portal_invoices_2_8.py`: JWT, límites, rechazo de identidad, ownership, vacío, error de BillTrack y allowlist de campos.
* `mobile/scripts/verify-invoices.mjs` (`npm run test:invoices`): fases de UI, campos, ausencia de pago/PDF/vencimiento, y la fecha calendario en `UTC`, `America/Buenos_Aires` y `Pacific/Kiritimati`.

No hay renderer de Home en el repo. Esos scripts no sustituyen una prueba en dispositivo.

## Out of scope

* `due_date`
* payment
* PDF
* payment history
* Runtime
* Journeys
* `ticket_customer_note`
* production
