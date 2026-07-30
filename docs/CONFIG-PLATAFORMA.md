# Configuración de plataforma (admin)

Panel en **Admin Hub → Configuración plataforma** para operar sin editar solo `.env` en cada deploy.

## Secciones

1. **API IA** — endpoint compatible OpenAI (Ollama/Llama local o cloud), modelo y API key. Botón “Probar conexión”.
2. **WhatsApp** — Cloud API Meta (token, phone number id, verify token, app secret, org slug del webhook).
3. **Clientes (BillTrack)** — Postgres **externo de solo lectura** para que el bot consulte el padrón de clientes. Campos: host, puerto, usuario, contraseña, dbname, sslmode (`disable` en servidores on-prem sin TLS). La URL se arma escapando caracteres especiales de la password. Botón “Probar conexión BillTrack”.
4. **Data Estate** — base del **sistema** (tickets, usuarios, config, canal, KB). Muestra URL activa; “Probar Data Estate activo” hace `SELECT 1` sobre `DATABASE_URL` del proceso. No confundir con BillTrack.
5. **Conocimiento** — umbrales del RAG (`min_score`, `top_k`, `max_fragment_chars`). Artículos KB: pantalla Conocimiento.
6. **Playbooks** — JSON editable de flujos N1 (`internet`, `movil`, `corte_deuda`, `general`).

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
- `POST /api/v1/admin/settings/test-database` — solo Data Estate activo

Solo rol **admin**. Persistencia: tabla `platform_config`. Valores no definidos caen a variables de entorno.
