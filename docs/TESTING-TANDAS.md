# Cómo correr la suite de tests (dos tandas)

La suite completa ya no entra en una sola corrida de 5 minutos, así que se corre en **dos tandas**. El marcador
`e2e_conv` (registrado en `pyproject.toml`) se aplica automáticamente a todo lo que está en `tests/e2e_conv/`
(`tests/e2e_conv/conftest.py`).

| Tanda | Qué corre | Comando | Total esperado | Tiempo medido |
|---|---|---|---|---|
| 1 — escenarios | `tests/e2e_conv` (harness, invariantes, escenarios y hallazgos) | `timeout 600 .venv/bin/python -m pytest -m e2e_conv` | **140 passed, 10 xfailed** (2068 deseleccionados) | 62 s |
| 2a — resto, mitad 1 | `tests/test_*.py`, archivos 1–103 en orden alfabético (hasta `test_helpdesk_features.py`) | `timeout 900 .venv/bin/python -m pytest -m "not e2e_conv" $(ls tests/test_*.py \| head -103)` | **1370 passed** | 480 s |
| 2b — resto, mitad 2 | `tests/test_*.py`, del archivo 104 en adelante | `timeout 900 .venv/bin/python -m pytest -m "not e2e_conv" $(ls tests/test_*.py \| tail -n +104)` | **698 passed** | 411 s |

Total del repo: **2208 passed + 10 xfailed** (140 + 1370 + 698 passed).

Notas
- **Tiempos**: la partición se hizo por tiempo medido (`--durations=0`: 853 s de tests en total; `test_helpdesk_features.py` solo es 203 s,
  `test_tickets_intelligence_api` 106 s, `test_kb_contributions` 79 s, `test_rbac` 77 s, `test_analytics_export` 74 s). Con la máquina cargada
  (Cursor/Chrome abiertos) cada mitad tarda 7–8 min; en la tanda 3, sin carga, la tanda 2 entera tardó 345 s (≈3 min por mitad). Si una mitad
  pasa de 6 min de forma sostenida, mover el corte o partir en tres.
- **Rebalancear**: al agregar archivos `test_*.py` el corte `head -103` se corre; los archivos nuevos que quedan antes de `test_helpdesk_features.py`
  desplazan ese archivo a la mitad 2. Volver a medir con `--durations=0` si el desbalance crece.
- Los 10 `xfail` son **estrictos** (`xfail(strict=True)`): cuando un arreglo hace pasar uno, el test falla con XPASS y hay que
  retirar el marcador. Para ver que cada uno reproduce su bug: `pytest -m e2e_conv --runxfail` (deben fallar exactamente esos 10).
- Las tandas usan la misma base SQLite de tests (`data/test_estate.db`): **no correrlas en paralelo**.
- Siempre con `timeout`. Una corrida con `timeout 570` se cortó sin dejar resultado: guardar la salida completa en un archivo, no filtrar con `grep`.
- `ruff`: `.venv/bin/ruff check .`
- CI (`.github/workflows/ci.yml`) todavía corre `python -m pytest` completo; separarlo en tandas queda pendiente de decisión.
