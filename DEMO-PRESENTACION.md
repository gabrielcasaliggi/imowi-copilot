# imowi Operations Hub — Guía de presentación (10 min)

## Mensaje central

> **No reemplazamos JSC ni el sistema contable.** Unificamos la operación: el operador habla en lenguaje natural, el sistema consulta JSC, valida cuenta, aplica manuales y genera tickets NOC con trazabilidad agentic.

---

## Acceso demo

| Usuario | Contraseña | Perfil |
|---------|------------|--------|
| `admin` | `admin` | NOC imowi — ve todas las cooperativas |
| `batan` | `batan` | Operador Cooperativa Batán |
| `viamonte` | `viamonte` | Operador Cooperativa Viamonte |

**Local:** `uvicorn main:app --reload --host 127.0.0.1 --port 8000` → http://127.0.0.1:8000

---

## Guión sugerido

### 1. Cooperativa atiende un reclamo (3 min)

1. Login: **batan / batan**
2. En el chat:
   ```
   Cliente sin datos en Brasil, línea 2235551234, Samsung A54
   ```
3. Mostrar:
   - **Ficha JSC** (abonado, plan, APN, roaming)
   - **Trazas agentes** (Pre-LLM → JSC → Diagnóstico → Intent roaming)
4. Clic en **Registrar ticket NOC** → ticket `JSC-xxxx` en panel

### 2. Caso con deuda — sistema contable (1 min)

1. Chat:
   ```
   Línea 2235559012 sin servicio
   ```
2. El agente marca **estado cuenta: Deuda** y sugiere verificar contable antes de red.

### 3. NOC imowi — vista global (2 min)

1. Salir → Login **admin / admin**
2. Selector **Vista cooperativa** → cambiar entre Batán y Viamonte
3. Mostrar tickets de cada revendedor

### 4. Proactividad — monitor de red (2 min)

1. Pestaña **Monitor de Red**
2. **Simular falla** en `Celda-Movistar-Güemes`
3. Volver a Consola: ticket **Autónomo Predictivo** sin que el cliente haya llamado

### 5. Cierre comercial (1 min)

- Hoy: réplica JSC + stub contable (demo)
- Mañana: adaptador API/export JSC real
- Escala: mismo modelo para 50.000+ líneas y N cooperativas revendedoras

---

## Líneas de prueba (catálogo JSC demo)

| Línea | Cooperativa | Nota |
|-------|-------------|------|
| 2235551234 | Batán | Roaming Brasil — caso estrella |
| 2235559012 | Batán | Línea suspendida + deuda |
| 2235571001 | Viamonte | Fibra FTTH |

---

## Frases para stakeholders

- *"JSC sigue siendo el sistema maestro; nosotros aceleramos la operación."*
- *"Las cooperativas revenden con su marca; imowi conserva el control del NOC."*
- *"Los agentes no reemplazan al operador: ejecutan playbooks auditados."*
