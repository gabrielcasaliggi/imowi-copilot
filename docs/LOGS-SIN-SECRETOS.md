# Logs sin secretos (H28)

## Incidente

`httpx` logueaba en `INFO` la URL completa de cada request. Las llamadas a BCM llevan las credenciales en la
query string (`/auth/obtenerToken?usuario=…&contrasenaapp=…` y `…?usuario=…&token=…`), así que la contraseña de
aplicación de BCM y el token de sesión quedaron escritos en el journal del server. Además,
`redactar_params_sensibles` de BCM no tapaba `token` ni `contrasenaapp` en los logs de error de los cambios de Wi‑Fi.

**Acción de ops (obligatoria): rotar la contraseña de aplicación de BCM** (y con ella se invalidan los tokens que
hayan quedado en el journal). Después de rotarla, revisar quién tiene acceso al journal y a los backups de logs del
período expuesto. Mismo criterio para el token del bot de Telegram si estuvo configurado (va en el path de la URL).

## Política

1. **Nunca** se loguea un secreto: contraseñas, tokens, API keys, headers `Authorization`, la contraseña de una
   URL (`scheme://user:pass@host`), ni el token del bot de Telegram.
2. Las URLs, params, headers y payloads de integraciones (BCM, UISP, Radius, BillTrack, OV, WhatsApp, Telegram,
   email) se loguean solo si hacen falta, y nunca con credenciales. Preferir status y nombres de clave antes que
   cuerpos completos.
3. Red de seguridad global (`app/log_redaction.py`, instalada en `main.py`):
   - `httpx` y `httpcore` en `WARNING` (no logean cada request);
   - toda línea de log pasa por `redactar` antes de llegar a cualquier handler (journal, uvicorn, Sentry, caplog):
     enmascara con `***` el valor de `contrasena*`/`password`/`passwd`/`pwd`/`pass`, `*token*`, `*secret*`,
     `api_key`, `key`, `clave`, `authorization`/`x-auth-token`, `celular`/`telefono`/`msisdn`, en query string,
     JSON/dict y headers, sin distinguir mayúsculas; también trazas de excepción y `stack_info`;
   - Sentry: `before_send` y `before_breadcrumb` aplican lo mismo (los breadcrumbs de httpx guardan URL y query).
4. La red no reemplaza el cuidado en el código: para dicts de params usar `redactar_params_sensibles` /
   `es_clave_sensible`; para texto libre de un tercero (cuerpos de error), `redactar(...)`.
5. Tests: `tests/test_log_redaction.py` (BCM con credenciales ficticias, formatos del filtro, access log de uvicorn,
   logs de journey). Nunca usar valores reales en tests, fixtures, commits ni tickets.

## Pendiente (propuesta, sin cambiar el contrato)

El cliente BCM (`app/bcm/client.py`) ya prueba la autenticación por cuerpo (`post_form`, `post_json`), pero el
primer intento (`post_query_form`) manda las credenciales en query **y** body, y el último (`get_query`) solo en
query. Las consultas (`obtenerPorNumeroCliente`, `/tr/modificarWifi*`) mandan `usuario`/`token` (y la clave Wi‑Fi
del abonado) en la query. Propuesta: confirmar con Sopnet qué variante de auth acepta prod, dejar solo la de cuerpo,
y ver si la API acepta el token por header (`Authorization: Bearer`) y los params de `/tr/*` en el body.
