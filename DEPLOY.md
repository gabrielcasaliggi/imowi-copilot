# Despliegue — imowi NOC Copilot

## Qué persiste hoy

| Dato | Ubicación | Notas |
|------|-----------|--------|
| Tickets | `data/tickets.json` | Cooperativa, línea, falla, estado, etc. |
| Sesiones login | `data/sessions.json` | Tokens (demo) |
| Base conocimiento | `Base_de_Conocimiento_Tickets.md` | Solo lectura en el image |

**Importante:** en PaaS sin volumen (Render free, Railway sin disk), los JSON se **borran** en cada redeploy. Usá **volumen** o **VPS**.

El historial del chat **no** se guarda aún; solo los campos del ticket.

---

## Opción recomendada: Docker (VPS o local)

```bash
# 1. Variables (copiá .env.example → .env y completá AI_API_KEY)
cp .env.example .env

# 2. Levantar
docker compose up -d --build

# 3. Abrir
# http://TU_IP:8000
```

Los datos quedan en el volumen Docker `copilot-data`. Para backup:

```bash
docker compose exec copilot cat /app/data/tickets.json
```

---

## VPS (sin Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# editar .env

mkdir -p data
uvicorn main:app --host 0.0.0.0 --port 8000
```

Usá **systemd** o **nginx** como reverse proxy con HTTPS (Let's Encrypt).

Variables útiles:

```env
DATA_DIR=/var/lib/imowi-copilot/data
AI_BASE_URL=https://api.groq.com/openai/v1
AI_API_KEY=tu-clave
AI_MODEL=llama-3.3-70b-versatile
```

---

## PaaS (Railway, Render, Fly.io)

1. Conectá el repo.
2. **Build:** `pip install -r requirements.txt`
3. **Start:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Variables de entorno: `AI_*`, `DATA_DIR=/data` (si ofrecen disco persistente).
5. En Render: activá **Persistent Disk** y montá en `/data`.
6. Subí también `Base_de_Conocimiento_Tickets.md` (incluido en el repo).

Sin disco persistente: sirve para **demo temporal**, no para producción con tickets reales.

---

## Checklist antes de publicar

- [ ] Cambiar contraseñas demo en `app/config.py` (o mover a env).
- [ ] No commitear `.env` (ya está en `.gitignore`).
- [ ] `AI_API_KEY` solo en variables del servidor.
- [ ] HTTPS delante de la app (nginx / Caddy / proxy del PaaS).
- [ ] Probar login coop + crear ticket + recargar página + retomar caso.

---

## Próximo paso (producción)

Para más usuarios y concurrencia:

1. **SQLite** o **PostgreSQL** en lugar de JSON.
2. Auth real (LDAP / OAuth), no tokens en archivo.
3. Opcional: guardar historial de chat por ticket.

Para una **demo interna** con Docker + volumen, lo actual alcanza.
