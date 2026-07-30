# RBAC: roles, permisos y tenants

Documento de diseño acordado para el modelo de acceso de la consola Operations Hub.

**Estado:** implementación en curso (catálogo, JWT, guards, Admin Hub roles/permisos).  
**Fecha:** 2026-07-30  
**Alcance:** consola de agentes/admin (no portal abonado).

---

## Contexto actual

Hoy la consola es efectivamente **binaria**:

| JWT efectivo | Quién |
|--------------|--------|
| `admin` | Plataforma / NOC Imowi |
| `agente` | Operador de cooperativa |

Roles más ricos viven en DB (`admin_sistema`, `ingeniero_noc`, `admin_org`, …) pero se **colapsan** a `admin`/`agente` al emitir el token (`app/auth.py`). El Admin Hub permite orgs, alta de usuarios y settings, pero **no** hay matriz de permisos ni edición de roles.

Este documento define el modelo objetivo.

---

## Principio de tenant

- Cada cooperativa/empresa es una `Organization` (`organizations`).
- Cada usuario pertenece a **una** organización (`users.organizacion_id`).
- **Solo el Administrador** puede cruzar tenants (crear orgs, `X-Tenant-Slug`, vista global).
- Supervisor, Ejecutivo y Agente operan **únicamente dentro de su cooperativa**.

El aislamiento por org ya existe en `get_tenant_context` (`app/api/v1/deps.py`); el cambio es dejar de aplastar roles y aplicar permisos dentro de ese scope.

---

## Roles

### 1. Administrador

- Alcance: **plataforma** (todas las cooperativas).
- Puede modificar todo y **configurar el bot**.
- Crea cooperativas/empresas.
- Gestiona roles, permisos y usuarios.
- Ve estadísticas completas, tickets abiertos/cerrados, mediciones e interacción/actividad de usuarios.
- Puede filtrar por cooperativa o ver agregados globales.

### 2. Supervisor de área

- Alcance: **solo su cooperativa**.
- Ve la cola de tickets y cómo la atienden los agentes.
- Puede **derivar / reasignar** tickets entre agentes.
- Ve el **performance de los agentes** de su coop.
- Puede **crear y desactivar agentes** de su cooperativa (no roles de plataforma ni otros supervisores/ejecutivos, salvo que el Admin lo permita después).
- No configura el bot ni gestiona la matriz global de roles/permisos.
- No cambia de tenant.

### 3. Ejecutivo

- Alcance: **solo su cooperativa**.
- Ve performance del bot y estadísticas agregadas de su org.
- Puede **exportar y generar reportes**.
- No opera la cola, no deriva tickets, no configura el bot, no gestiona usuarios.
- No cambia de tenant.

### 4. Agente

- Alcance: **solo su cooperativa**.
- Puede cambiar su **estado de disponibilidad** (disponible / ocupado / ausente, etc.).
- Ve la **cola completa** de tickets de su cooperativa (incluidos los mensajes/casos que el bot deriva a humanos).
- Ve **su propio** performance / actividad.
- No ve stats de otros agentes, no deriva tickets, no configura bot, no gestiona usuarios.

---

## Matriz de permisos

Leyenda: **Sí** · **No** · **Su org** · **Propio**

### Plataforma y configuración

| Permiso | Código sugerido | Admin | Supervisor | Ejecutivo | Agente |
|---------|-----------------|:-----:|:----------:|:---------:|:------:|
| Crear/editar cooperativas | `orgs.manage` | Sí | No | No | No |
| Configurar bot / settings plataforma | `bot.configure` | Sí | No | No | No |
| Gestionar roles y permisos | `roles.manage` | Sí | No | No | No |
| Gestionar usuarios (CRUD global) | `users.manage` | Sí | No | No | No |
| Crear/desactivar agentes de su coop | `users.manage_agents` | Sí | Su org | No | No |
| Cambiar de tenant | `tenant.switch` | Sí | No | No | No |

### Tickets y cola

| Permiso | Código sugerido | Admin | Supervisor | Ejecutivo | Agente |
|---------|-----------------|:-----:|:----------:|:---------:|:------:|
| Ver cola de tickets | `tickets.queue.view` | Sí (global/org) | Su org | No | Su org (completa) |
| Ver tickets abiertos/cerrados | `tickets.view` | Sí | Su org | No* | Su org (cola) |
| Derivar / reasignar tickets | `tickets.reassign` | Sí | Su org | No | No |
| Actualizar seguimiento / estado | `tickets.update` | Sí | Su org | No | Solo asignados (si se habilita) |
| Cambiar disponibilidad | `agent.availability` | — | — | — | Sí |

\*El ejecutivo consume métricas agregadas, no la bandeja operativa.

### Estadísticas y reportes

| Permiso | Código sugerido | Admin | Supervisor | Ejecutivo | Agente |
|---------|-----------------|:-----:|:----------:|:---------:|:------:|
| Stats globales / multi-coop | `stats.global` | Sí | No | No | No |
| Performance del bot (su org) | `stats.bot` | Sí | No | Su org | No |
| Performance de agentes (su org) | `stats.agents` | Sí | Su org | No | No |
| Actividad propia | `stats.self` | Sí | Sí | Sí | Propio |
| Exportar / reportes | `reports.export` | Sí | Su org (equipo) | Su org (bot/stats) | No |

### Knowledge base (mínimo acordado)

| Permiso | Código sugerido | Admin | Supervisor | Ejecutivo | Agente |
|---------|-----------------|:-----:|:----------:|:---------:|:------:|
| Proponer a KB | `kb.propose` | Sí | Sí | No | Sí |
| Publicar / revisar KB | `kb.publish` | Sí | No | No | No |

---

## Sector Admin (UI)

Ampliar el Admin Hub (`/admin`) con:

1. **Roles** — catálogo de los 4 roles base (clonables/ajustables a futuro).
2. **Permisos** — matriz rol × capability (checkboxes).
3. **Usuarios** — alta/edición, organización, rol, activo/inactivo; filtro por cooperativa.

Flujo típico:

1. Admin crea cooperativa.
2. Admin (o supervisor, solo agentes) da de alta usuarios en esa coop.
3. Asigna rol: `supervisor` | `ejecutivo` | `agente` (o `admin` solo en org plataforma).

Tabs existentes (Cooperativas, Configuración plataforma) se mantienen; Roles / Permisos / Usuarios se integran o se añaden como secciones.

---

## Modelo de datos (objetivo)

Sin imponer schema final; guía de implementación:

| Entidad | Responsabilidad |
|---------|-----------------|
| `roles` | id, código (`admin`, `supervisor`, `ejecutivo`, `agente`), nombre, descripción, system (no borrable) |
| `permissions` | id, código (`tickets.reassign`, …), dominio, descripción |
| `role_permissions` | rol ↔ permiso |
| `users.rol` o `users.role_id` | asignación; migrar strings legacy |
| `users.activo` / `disabled_at` | alta lógica para que el supervisor desactive agentes |

Valores JWT / sesión deben preservar el **rol real** (no colapsar supervisor/ejecutivo a `agente`).

Flags derivados útiles en `TenantContext`:

- `es_admin_plataforma` (ex `es_admin_imowi`)
- `permisos: set[str]` o helper `puede(codigo)`
- `organizacion_slug` inmutable salvo `tenant.switch`

---

## Mapeo desde roles legacy

| Legacy / DB actual | Rol objetivo |
|--------------------|--------------|
| `admin`, `admin_sistema` (Imowi) | `admin` |
| `ingeniero_noc` (Imowi) | `admin` o `supervisor` plataforma (decidir en migración; default propuesto: `admin` si hoy tiene privilegios NOC) |
| `admin_org`, `ingeniero_noc` (coop) | `supervisor` |
| `operador`, `cooperativa`, `cliente`, `agente` | `agente` |
| _(nuevo)_ | `ejecutivo` |

La migración debe ser explícita y reversible (seed + script), no solo rename silencioso.

---

## Reglas de autorización (resumen)

1. Si no hay permiso → 403.
2. Si el recurso es de otra org y el usuario no tiene `tenant.switch` → 404 o 403 (preferir no filtrar datos ajenos).
3. Supervisor solo puede crear/desactivar usuarios con rol `agente` en **su** `organizacion_id`.
4. Ejecutivo: endpoints de analytics/export de su org; sin mutaciones de tickets/cola.
5. Agente: cola completa de su org; stats solo `stats.self`; disponibilidad propia.

---

## Fuera de alcance (esta fase)

- Portal abonado (`typ=portal`) — sin cambios de RBAC de consola.
- Roles custom ilimitados por cooperativa (solo los 4 + matriz editable por Admin).
- Facturación / billing por rol.
- SSO / IdP externo.

---

## Plan de implementación (orden sugerido)

1. Catálogo de roles y permisos en backend (constantes + tablas o seed).
2. Dejar de colapsar roles en JWT; ampliar `TenantContext` + `puede()`.
3. Guards en APIs de tickets, stats, admin, users.
4. Campo activo/desactivado en usuarios; API supervisor `users.manage_agents`.
5. UI Admin: Roles · Permisos · Usuarios.
6. UI por rol: nav, cola, stats, disponibilidad, export.
7. Tests de autorización por rol + tenant.
8. Migración de usuarios/seed demo (`admin`, supervisor Batán, ejecutivo Batán, agentes).

---

## Decisiones cerradas

| # | Pregunta | Respuesta |
|---|----------|-----------|
| 1 | Alcance del supervisor | Solo su cooperativa |
| 2 | Ejecutivo: ¿exportar? | Sí, reportes/export |
| 3 | Ejecutivo: ¿tenant? | Solo su cooperativa |
| 4 | Agente: ¿cola? | Cola **completa** de su coop |
| 5 | Supervisor: ¿usuarios? | Puede **crear y desactivar agentes** de su coop |
| 6 | Admin | Todo + config bot + crear coops + RBAC |

---

## Referencias de código actual

| Área | Ubicación |
|------|-----------|
| Normalización JWT | `app/auth.py` (`_normalizar_rol_consola`, `_rol_token_desde_estate`) |
| Tenant context | `app/api/v1/deps.py` |
| Modelos User/Org | `app/estate/models.py` |
| Admin API | `app/api/v1/admin.py` |
| Admin UI | `frontend/src/components/admin/AdminPanel.tsx` |
| Gate frontend | `user?.rol === "admin"` en `AppContext` / páginas |

Ver también: [ARQUITECTURA_PLATAFORMA.md](./ARQUITECTURA_PLATAFORMA.md), [OPERATIONS-HUB-RESUMEN.md](./OPERATIONS-HUB-RESUMEN.md).
