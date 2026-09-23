# EKO 2.6N-C — Test Harness Runtime Isolation

**Estado:** PASS  
**Fecha:** 2026-09-23  
**Alcance:** pytest / harness local únicamente  
**Precedente:** 2.6N-B → PATH C (`TEST_HARNESS_AVAILABLE`)

## Objetivo

Demostrar, sin tocar producción ni staging remoto, que la configuración de rollout:

```
ACTION_RUNTIME_ENABLED=true
ACTION_RUNTIME_ACTIONS=create_ticket
```

aísla Runtime a `create_ticket`, ejecuta el flujo CASI una sola vez y respeta XOR Runtime/Legacy.

## Configuration

Validada **solo en monkeypatch de tests** (no aplicada a `.env` ni deploy):

```
ENABLED=true
ACTIONS=create_ticket
```

Equivalente en harness:

```python
monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
monkeypatch.setattr(bridge, "ACTION_RUNTIME_ACTIONS", frozenset({"create_ticket"}))
```

## Runtime ON

Escenario: confirmation pending + texto «sí» vía `_ticket_via_runtime_o_legacy`, writer mockeado.

```
runtime calls:   1
legacy calls:    0   (rama Legacy del helper no entra)
executor calls:  1   (_crear_ticket_n2 vía Runtime)
harness tickets: 1   (sintético SQLite o mock TK-*)
harness events:  1   (tipo=creacion, visible_cliente=Sí)
```

Sensor: `tests/test_eko_runtime_isolation_2_6nc.py`

## Runtime OFF

```
ENABLED=false
ACTIONS=create_ticket   # irrelevante si master off
```

```
runtime calls:  0
legacy calls:   1
```

Sin doble ejecución.

## Isolation

Con `ACTIONS={create_ticket}`:

```
create_ticket:           COVERED
other default actions:   NOT COVERED
```

Otras del default set (no cubiertas bajo aislamiento):

- `installation_status`
- `open_OV`
- `request_account_selection`
- `run_diagnostic_bcm`
- `run_diagnostic_pppoe`
- `run_diagnostic_uisp`
- `send_message`
- `service_list`
- `show_balance`
- `show_invoice`
- `show_ticket`
- `ticket_customer_note`

Assertion explícita: `ACTION_RUNTIME_ACTIONS !=` default frozenset completo.

## CASI

Flujo validado (no `create_ticket()` directo como única prueba):

```
Proposal:  parse_llm_action_proposal → source=llm_proposal; params hostiles sanitizados
Policy:    sin confirmation_received → needs_confirmation / NEEDS_CONFIRMATION
Motor:     _ticket_via_runtime_o_legacy (N1) con confirmation_pending + «sí»
Runtime:   dispatch_runtime / execute_action → execution_path=runtime, status=success
```

`LLM content != authority`: parámetros inventados por el LLM (`client_number`, `visible_cliente`, `confirmation`) no autorizan el write.

## Regression

| Suite | Resultado |
|---|---|
| `tests/test_eko_runtime_isolation_2_6nc.py` | PASS (7) |
| `tests/test_eko_create_ticket_runtime_2_6k.py` | PASS |
| `tests/test_eko_n1_ticket_customer_note_2_6i.py` | PASS |
| XOR / create_ticket en `test_eko_action_runtime_4d.py` (filtro) | PASS |
| `test_4d_explicit_pppoe_one_reader` | FAIL preexistente — **PRE-EXISTING / OUT OF SCOPE** (PPPoE `needs_input` / `service_selection_required`; no corregido) |

Comando de cierre principal:

```bash
.venv/bin/python -m pytest \
  tests/test_eko_runtime_isolation_2_6nc.py \
  tests/test_eko_create_ticket_runtime_2_6k.py \
  tests/test_eko_n1_ticket_customer_note_2_6i.py -q
```

```bash
.venv/bin/ruff check tests/test_eko_runtime_isolation_2_6nc.py
```

## Safety

```
production touched        = NO
production config modified = NO
remote ticket created      = NO
remote event created       = NO
```

Sin SSH a `ibot`/`soporte`, sin cambios en `app/config.py` defaults operativos, sin `.env`, sin deploy/systemd/Docker/CI.

## Criterio de PASS (checklist)

- [x] `create_ticket` aislado por `ACTION_RUNTIME_ACTIONS`
- [x] Runtime ON utiliza Runtime
- [x] Runtime ON no utiliza Legacy
- [x] Runtime ON ejecuta exactamente una vez
- [x] Runtime OFF no utiliza Runtime
- [x] Runtime OFF puede utilizar Legacy
- [x] Nunca Runtime + Legacy simultáneos
- [x] Flujo Proposal / Policy / Motor
- [x] Executor protegido por harness (mock / SQLite)
- [x] Exactamente un Ticket sintético
- [x] Exactamente un Event sintético `creacion`
- [x] Sin side effect remoto
- [x] Producción no tocada
- [x] Regresiones relevantes OK (PPPoE documentado como preexistente)

## Final status

```
PASS
```

```
create_ticket Runtime isolation = PROVEN
```

Listo para una fase posterior de activación operativa **fuera** de este brief (no es parte de 2.6N-C).
