# Configuración de plataforma (admin)

Panel en **Admin Hub → Configuración plataforma** para operar sin editar solo `.env` en cada deploy.

## Secciones

1. **API IA** — endpoint compatible OpenAI (Ollama/Llama local o cloud), modelo y API key. Botón “Probar conexión”.
2. **WhatsApp** — Cloud API Meta (token, phone number id, verify token, app secret, org slug del webhook).
3. **Base de datos** — muestra URL activa enmascarada; guardar un valor nuevo sirve para documentar migración on-prem. El proceso en Render sigue usando `DATABASE_URL` del entorno hasta reinicio.
4. **Conocimiento** — umbrales del RAG (`min_score`, `top_k`, `max_fragment_chars`). Artículos KB: pantalla Conocimiento.
5. **Playbooks** — JSON editable de flujos N1 (`internet`, `movil`, `corte_deuda`, `general`).

## API

- `GET /api/v1/admin/settings`
- `PUT /api/v1/admin/settings` body `{ "settings": { "ai": {...}, ... } }`
- `POST /api/v1/admin/settings/test-ai`
- `POST /api/v1/admin/settings/test-whatsapp`

Solo rol **admin**. Persistencia: tabla `platform_config`. Valores no definidos caen a variables de entorno.
