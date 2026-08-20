# Entrenamiento N1 — mesa de ayuda (hogareño + corporativo)

Proceso para bajar **tickets N2 evitables** sin tapar visitas ópticas ni handoffs B2B legítimos (SLA / sede caída).

## Ciclo semanal

1. Revisar 3–5 tickets N2 de bandeja (`canal_abonado_n2`).
2. Si N1 podía resolver → artículo KB corto **o** paso de playbook (nunca el transcript crudo).
3. Agregar o ajustar una **persona** QA con hechos ocultos.
4. Correr el harness del lote afectado.
5. Métrica de corte: **0 N2 evitables**. N2 ópticos / radio agotado / B2B productivo = OK.

```bash
.venv/bin/python -m qa_bot.cliente_hogareno              # P01–P12
.venv/bin/python -m qa_bot.cliente_hogareno --personas P09,P12
.venv/bin/python -m qa_bot.cliente_corporativo           # C01–C04
```

Reglas:

- No mezclar harness hogareño y B2B (tono y umbral de escalado distintos).
- En tests, forzar playbooks de código (override admin puede pisar el catálogo).
- El canal N1 usa KB **tenant** (`incluir_rag_global=False`); no indexar dumps de tickets.

## Matriz hogareña

| Síntoma | Playbook | KB seed (título) | Persona | N2 esperado |
|---------|----------|------------------|---------|-------------|
| Fibra sin servicio, PON OK | `internet_ftth` | Internet FTTH — sin servicio; N1 luces PON/LOS | P01 | nunca |
| LOS roja | `internet_ftth` | N1 hogareño — luces PON y LOS | P02 | óptico legítimo |
| Solo WiFi / cobertura | `wifi` | N1 hogareño — cable vs WiFi | P03 | nunca |
| Lento en pico | `internet_lento` | N1 hogareño — lentitud en horario pico | P04 | nunca |
| Radio techo agotado | `internet_radio` | N1 hogareño — PoE y antena | P05 | post_n1_radio |
| Typo / NLP | `internet` → FTTH | — | P06 | nunca |
| Pide humano de entrada | menú + N1 | — | P07 | nunca |
| Reiteración temprana | `internet` | — | P08 | nunca |
| Intermitencia | `internet_intermitente` | Internet — cortes o intermitencia | P09 | nunca (si reinicio estabiliza) |
| ADSL sin sync | `internet_adsl` | Internet ADSL — sin servicio | P10 | nunca si sync vuelve; else legítimo |
| Cambio clave WiFi | `cambio_clave_wifi` | WiFi — cambiar clave o nombre | P11 | nunca |
| Adulto mayor / WhatsApp | `wifi` / internet | N1 hogareño — adulto mayor y WhatsApp | P12 | nunca |

## Matriz corporativa (Ecolan B2B)

| Síntoma | Playbook | KB seed | Persona | N2 esperado |
|---------|----------|---------|---------|-------------|
| Cotización enlace | `ecolan_b2b` | B2B — triaje alcance; enlace dedicado | C01 | nunca (no N2 técnico) |
| VPN un usuario (hotspot OK) | `ecolan_b2b` | B2B — VPN sucursal | C02 | nunca |
| Enlace dedicado sede caída | `ecolan_b2b` | B2B — enlace dedicado / IP fija | C03 | legítimo Ecolan |
| VM/DC impacto productivo | `ecolan_b2b` | B2B — VM/DC caída con impacto | C04 | legítimo |

## Cómo curar desde un chat bueno

1. Extraer el **procedimiento** (pasos + cuándo no escalar).
2. Quitar PII (DNI, nombre, IP, montos).
3. Seed en [`app/estate/seed.py`](../app/estate/seed.py) o propuesta KB al cerrar ticket.
4. Opcional: persona QA que valide el artículo.

## Fuera de alcance (Fase 2)

TV Sensa, factura fina, consola operador IMOWI, embeddings Botmaker.
