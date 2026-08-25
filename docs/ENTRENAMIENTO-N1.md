# Entrenamiento N1 — mesa de ayuda (hogareño + corporativo)

Proceso para bajar **tickets N2 evitables** sin tapar visitas ópticas ni handoffs B2B legítimos (SLA / sede caída).

## Ciclo semanal

1. Correr el entrenamiento automatizado (`python -m qa_bot.entrenamiento_exhaustivo`).
2. Revisar 3–5 tickets N2 reales de bandeja (`canal_abonado_n2`) — ahí aparece el ruido del cliente.
3. Si N1 podía resolver → artículo KB corto **o** paso de playbook (nunca el transcript crudo).
4. Agregar o ajustar una **persona** QA con hechos ocultos y sumarla al lote.
5. Re-correr el harness del lote afectado.
6. Métrica de corte: **0 N2 evitables**. N2 ópticos / radio agotado / provisión móvil / B2B productivo = OK.

```bash
.venv/bin/python -m qa_bot.entrenamiento_exhaustivo          # P01–P28 + C01–C04
.venv/bin/python -m qa_bot.entrenamiento_exhaustivo --lote movil
.venv/bin/python -m qa_bot.cliente_hogareno --lote exhaustivo
.venv/bin/python -m qa_bot.cliente_hogareno --personas P13,P16,P17,P18
.venv/bin/python -m qa_bot.cliente_corporativo               # C01–C04
```

Lotes hogareños (`--lote`): `base` (P01–P18), `guion`/`exhaustivo` (P01–P28), `internet`, `factura`, `movil`, `agente`, `sensa`.

Métrica de corte del automatizado: **0 N2 evitables**. Artefacto: `qa_bot/artifacts/entrenamiento_exhaustivo.json`.

Esto reemplaza el barrido manual de ~2 semanas sobre el catálogo curado. **No** reemplaza la prueba con cliente real (escribe mal, no sabe qué le pasa, mezcla temas).

Reglas:

- No mezclar harness hogareño y B2B (tono y umbral de escalado distintos).
- En tests, forzar playbooks de código (override admin puede pisar el catálogo).
- El canal N1 usa KB **tenant** (`incluir_rag_global=False`); no indexar dumps de tickets ni embeddings Botmaker crudos.
- Fuente Botmaker (`docs/rag-botmaker-2026-08-14/`): solo **procedimientos curados** → seed/playbook/persona. Todo `rag_ready=false` hasta aprobación.

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
| Pagar factura | `facturacion_pago` | Facturación — medios de pago; N1 cuándo cerrar/derivar | P13 | nunca |
| Avisar pago | `facturacion_informar_pago` | Facturación — informar un pago | P14 | nunca |
| Reactivación reciente | `reactivacion_pago` | Corte por deuda — rehabilitación automática | P15 | nunca (espera plazo) |
| Reclamo de monto | `facturacion_reclamo` | Facturación — reclamo de monto | P16 | legítimo facturación |
| Sensa app (N1 alcanza) | `tv_sensa` | TV OTT Sensa; Sensa N1 cuándo cerrar/derivar | P17 | nunca |
| Sensa error de cuenta | `tv_sensa` | TV OTT Sensa — requisitos y escalamiento | P18 | legítimo |
| Móvil sin datos, APN Android OK, pack acreditado | `movil_datos` | IMOWI — sin datos móviles | P19 | N2 provisión (no 3G/iPhone) |
| 2ª insistencia mismo «quiero agente» | menú / handoff | — | P20 | 2ª = ticket; 1ª no |
| Saldo / cuánto debo | facturación | — | P21 | nunca |
| Factura más cara / aumento | facturación | — | P22 | nunca (indaga, no QR solo) |
| Se acabaron datos del abono | `movil_datos` | bono ov.batan | P23 | nunca |
| SMS banco no llega (A2P) | `movil_llamadas` / FAQ | — | P24 | nunca (otro medio) |
| Fijo sin tono | `telefono_fija` | — | P25 | post_n1_fija (legítimo tras playbook) |
| Typo menú `,ovil` | menú servicio | — | P26 | nunca |
| Corte por falta de pago / cómo pago | `facturacion_pago` | medios OV/QR | P27 | nunca |
| Quiere contratar fibra | `alta_plan` | — | P28 | nunca (comercial, no N2 técnico) |

## Matriz corporativa (Ecolan B2B)

| Síntoma | Playbook | KB seed | Persona | N2 esperado |
|---------|----------|---------|---------|-------------|
| Cotización enlace | `ecolan_b2b` | B2B — triaje alcance; enlace dedicado | C01 | nunca (no N2 técnico) |
| VPN un usuario (hotspot OK) | `ecolan_b2b` | B2B — VPN sucursal | C02 | nunca |
| Enlace dedicado sede caída | `ecolan_b2b` | B2B — enlace dedicado / IP fija | C03 | legítimo Ecolan |
| VM/DC impacto productivo | `ecolan_b2b` | B2B — VM/DC caída con impacto | C04 | legítimo |

## Cómo curar desde un chat bueno o blueprint Botmaker

1. Extraer el **procedimiento** (pasos + cuándo no escalar).
2. Quitar PII (DNI, nombre, IP, montos reales de clientes).
3. Seed en [`app/estate/seed.py`](../app/estate/seed.py) o propuesta KB al cerrar ticket.
4. Persona QA que valide el artículo / playbook.

## Fuera de alcance (siguiente)

Telefonía fija/móvil fina, embeddings Botmaker en prod, consola operador IMOWI.
