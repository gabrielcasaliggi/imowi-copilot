# Comprensión contextual — datos Botmaker

Pipeline para mejorar `comprension_abonado` con evidencia de **76k sesiones reales** (ene 2025 – jun 2026), sin indexar transcripts en producción.

## Principios

1. **Agregar, no reemplazar** — la capa de comprensión enriquece el turno; playbooks y guardrails siguen mandando.
2. **Sin PII en git** — exports crudos quedan fuera del repo (`data/` está en `.gitignore`).
3. **Solo patrones agregados versionables** — `app/data/comprension_lexico_curado.json`.
4. **Menús numéricos Botmaker ≠ EKO** — los dígitos (`7`, `2`, …) se minan como estadística; no se mapean ciegamente a EKO.

## Flujo

```bash
# 1. Export local (fuera del repo)
#    ~/Descargas/sesiones-historicas-2025_2026-06/

# 2. Minado + anonimización
.venv/bin/python scripts/minar_comprension_botmaker.py \
  --input-dir ~/Descargas/sesiones-historicas-2025_2026-06

# 3. Salidas
#    data/comprension-botmaker/report.json      → métricas (gitignored)
#    app/data/comprension_lexico_curado.json    → léxico versionable

# 4. Verificar
.venv/bin/python -m pytest tests/test_comprension_abonado.py -q
```

## Qué mina el script

| Artefacto | Contenido |
|-----------|-----------|
| Pares bot→usuario cortos | Respuestas ≤40 chars tras clasificar pregunta del bot |
| Buckets | `aviso_deuda`, `menu_servicio`, `menu_tipo_acceso`, `wifi_interferencias`, `confirmar_paso`, `csat`, `identificacion`, `confirmar_si_no`, `otro` |
| Léxico candidato | Tokens frecuentes cerca de keywords ISP (revisión humana antes de activar) |
| `frases_tecnico_en_aviso_deuda` | Frases que en Botmaker siguieron diagnóstico tras aviso de mora |

## Cifras del último barrido (76.096 sesiones)

| Métrica | Valor |
|---------|-------|
| Mensajes usuario | 393.166 |
| Pares cortos bot→usuario | 319.655 |
| Usuario ≤8 caracteres | ~52% |
| Pares en `aviso_deuda` | 71.757 |

## Integración en runtime

```
mensaje → comprension_abonado.preparar_turno_comprension()
        → comprension_lexico (JSON curado + reglas base)
        → ctx["hechos"] + texto_para_reglas
        → canal_abonado / playbooks (sin cambio de política)
```

## Ciclo de mejora continua

1. Nuevo export Botmaker (trimestral).
2. Re-correr minado.
3. Diff de `comprension_lexico_curado.json`.
4. Agregar tests en `tests/test_comprension_abonado.py` para frases nuevas relevantes.
5. Deploy API (el JSON viaja con el código).

## Privacidad

El minado aplica en memoria:

- Teléfonos → `[telefono]`
- DNI 7–8 dígitos → `[dni]`
- Emails → `[email]`
- Coordenadas → `[ubicacion]`

No commitear `data/comprension-botmaker/` ni exports crudos.
