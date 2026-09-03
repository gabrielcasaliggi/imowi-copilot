# Checklist QA piloto — Operations Hub

Ejecutar **al menos 1 vez por semana** (o antes de cada deploy a `ibot.ecolan.com`).
Marcar OK / FAIL. Si falla un ítem crítico, no desplegar.

Ambiente: _____________  Fecha: _____________  Quién: _____________

## 0. Preflight

- [ ] `git log -1 --oneline` es el commit esperado en el server
- [ ] `sudo systemctl status operations-hub-api` y `operations-hub-frontend` active
- [ ] `curl -sS https://ibot.ecolan.com/health` → `status` ok/degraded esperado
- [ ] Frontend rebuild hecho tras el pull (`npm ci && npm run build` + restart)

## 1. Auth consola

- [ ] Login agente demo/prod funciona
- [ ] Login admin funciona
- [ ] Logout limpia sesión
- [ ] Usuario sin permiso no entra a Admin

## 2. Portal abonado (`/portal`)

- [ ] DNI inválido / inexistente: error genérico (anti-enum)
- [ ] DNI válido: OTP / PIN según modo
- [ ] Reenviar código OTP
- [ ] Invitado puede chatear
- [ ] Mensaje técnico (internet lento) responde bot sin ticket inmediato
- [ ] `*agente*` (o flujo de derivación) crea ticket y estado espera agente
- [ ] Banner “espera agente” / “con agente” visible cuando aplica

## 3. Bandeja → Consola (agente)

- [ ] Conversación aparece en Bandeja
- [ ] **Tomar y abrir Consola** asigna ticket y navega a `/soporte`
- [ ] Chat del canal sincroniza mensajes del abonado
- [ ] Enviar respuesta del agente llega al portal
- [ ] Mobile: Volver en Bandeja; tabs Chat/Contexto en Consola

## 4. Tickets / cola

- [ ] Ticket visible en Cola
- [ ] Claim / reassign supervisor (si aplica)
- [ ] Cerrar/resolver pide confirmación y cierra ticket
- [ ] Tras cerrar, reingreso portal abre conversación nueva

## 5. KB / admin

- [ ] Agente propone mejora a KB desde contexto
- [ ] Admin ve pendiente (badge nav o campana)
- [ ] Aprobar/rechazar contribución

## 6. BillTrack (si habilitado)

- [ ] Portal con DNI real/mock resuelve padrón
- [ ] Consulta de saldo no inventa CBU/QR
- [ ] Fallo BillTrack no tira 500 en login-pin

## 7. Observabilidad / seguridad rápida

- [ ] Si hay `SENTRY_DSN`, un error de prueba aparece en Sentry (opcional)
- [ ] No hay secretos en logs del restart
- [ ] Backup estate reciente (< 24h) si es prod

## Resultado

| Severidad | Cantidad |
|-----------|----------|
| Críticos FAIL | |
| Menores FAIL | |

**Go / No-go deploy:** _____________

Notas:
-
-
