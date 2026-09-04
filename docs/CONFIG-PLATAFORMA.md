# Configuración de plataforma (admin)

Panel en **Admin Hub → Configuración plataforma** para operar sin editar solo `.env` en cada deploy.

## Secciones

1. **API IA** — endpoint compatible OpenAI (Ollama/Llama local o cloud), modelo y API key. Botón “Probar conexión”.
2. **WhatsApp** — Cloud API Meta (token, phone number id, verify token, app secret, org slug del webhook).
3. **Clientes (BillTrack)** — Postgres **externo de solo lectura**. Campos de conexión + test TCP.
   Lookup portal/bot por defecto sobre `api_person` + `api_person_email` + `api_person_phone`
   (DNI vs `doc_cuit`: exacto o CUIT argentino). Con *habilitado* + URL, el portal verifica DNI real.
   `BILLTRACK_LOOKUP_SQL` opcional para override; `BILLTRACK_LOOKUP_READY=false` apaga el lookup.
4. **Radio (UISP)** — NMS de solo lectura. CPE por username Radius.
5. **Fibra (BCM)** — Sopnet BCM de solo lectura (OLT/ONU). Cliente por número ERP (`client_number` BillTrack). JWT usuario + password de aplicación. N1 no edita clientes.
6. **Data Estate** — base del **sistema** (tickets, usuarios, config, canal, KB). Muestra URL activa; “Probar Data Estate activo” hace `SELECT 1` sobre `DATABASE_URL` del proceso. No confundir con BillTrack.
7. **Conocimiento** — umbrales del RAG (`min_score`, `top_k`, `max_fragment_chars`). Artículos KB: pantalla Conocimiento.
8. **Playbooks** — JSON editable de flujos N1 (`internet`, `movil`, `corte_deuda`, `general`).

## Dos bases, dos roles

| | Data Estate | BillTrack |
|---|---|---|
| Rol | Persistencia de la plataforma | Consulta de clientes para el bot |
| Escritura | Sí (tickets, config, …) | Solo lectura (`billtrack_reader`) |
| Settings | `database` / `DATABASE_URL` | `billtrack` / `BILLTRACK_DATABASE_URL` |

## API

- `GET /api/v1/admin/settings`
- `PUT /api/v1/admin/settings` body `{ "settings": { "ai": {...}, "billtrack": {...}, ... } }`
- `POST /api/v1/admin/settings/test-ai`
- `POST /api/v1/admin/settings/test-whatsapp`
- `POST /api/v1/admin/settings/test-billtrack` body opcional `{ "url", "sslmode" }`
- `POST /api/v1/admin/settings/test-uisp` body opcional `{ "base_url", "token", "login" }`
- `POST /api/v1/admin/settings/test-bcm` body opcional `{ "base_url", "user", "app_pass", "numero_cliente" }`
- `POST /api/v1/admin/settings/test-database` — solo Data Estate activo

Solo rol **admin**. Persistencia: tabla `platform_config`. Valores no definidos caen a variables de entorno.
