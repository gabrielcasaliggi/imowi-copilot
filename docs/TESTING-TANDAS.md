# Cómo correr la suite de tests (dos tandas)

La suite completa ya no entra en una sola corrida de 5 minutos, así que se corre en **dos tandas**. El marcador
`e2e_conv` (registrado en `pyproject.toml`) se aplica automáticamente a todo lo que está en `tests/e2e_conv/`
(`tests/e2e_conv/conftest.py`).

| Tanda | Qué corre | Comando | Total esperado | Tiempo medido |
|---|---|---|---|---|
| 1 — escenarios | `tests/e2e_conv` (harness, invariantes, escenarios y hallazgos) | `timeout 600 .venv/bin/python -m pytest -m e2e_conv` | **602 passed, 16 xfailed** (2429 deseleccionados) | 73–430 s según carga |
| 2a — resto, mitad 1 | `tests/test_*.py`, archivos 1–103 en orden alfabético (hasta `test_helpdesk_features.py`) | `timeout 900 .venv/bin/python -m pytest -m "not e2e_conv" $(ls tests/test_*.py \| head -103)` | **1389 passed** | 89 s |
| 2b — resto, mitad 2 | `tests/test_*.py`, del archivo 104 en adelante | `timeout 900 .venv/bin/python -m pytest -m "not e2e_conv" $(ls tests/test_*.py \| tail -n +104)` | **1040 passed, 0 xfailed** | 70 s |

Total del repo: **3031 passed, 16 xfailed** (602 + 1389 + 1040). Suite completa en un proceso con base limpia: 3031 passed, 16 xfailed, 556 s. H17 A, B y C cerrados; H22 (Fix 4) cerrado; H21 Fix 1 cerrado; Fix 2 abierto: quedan sus xfails estrictos.

Notas
- **Tiempos**: la partición se hizo por tiempo medido (`--durations=0`: 853 s de tests en total; `test_helpdesk_features.py` solo es 203 s,
  `test_tickets_intelligence_api` 106 s, `test_kb_contributions` 79 s, `test_rbac` 77 s, `test_analytics_export` 74 s). Con la máquina cargada
  (Cursor/Chrome abiertos) cada mitad llegó a tardar 7–8 min (330 s y 226 s en la última corrida sin carga); en la tanda 3, sin carga, la tanda 2 entera tardó 345 s (≈3 min por mitad). Si una mitad
  pasa de 6 min de forma sostenida, mover el corte o partir en tres.
- **Rebalancear**: al agregar archivos `test_*.py` el corte `head -103` se corre; los archivos nuevos que quedan antes de `test_helpdesk_features.py`
  desplazan ese archivo a la mitad 2. Volver a medir con `--durations=0` si el desbalance crece.
- Hoy hay 16 `xfail` estrictos, todos de H21 Fix 2 (`tests/e2e_conv/test_escenarios.py`). Si se agrega uno, es **estricto** (`xfail(strict=True)`): cuando un arreglo lo hace pasar, el test falla con XPASS y hay que
  retirar el marcador. Para ver que cada uno reproduce su bug: `pytest -m e2e_conv --runxfail` (deben fallar exactamente los marcados).
- Las tandas usan la misma base SQLite de tests (`data/test_estate.db`): **no correrlas en paralelo**.
- **Antes de subir**, correr la suite completa como el CI: un solo proceso, con la base de tests **limpia** (mover `data/test_estate.db`) y `ruff check .`. Una base local vieja puede esconder fallos que el CI sí ve (pasó con los tests de RC-4: el playbook de la base tenía otros pasos).
- Siempre con `timeout`. Una corrida con `timeout 570` se cortó sin dejar resultado: guardar la salida completa en un archivo, no filtrar con `grep`.
- `ruff`: `.venv/bin/ruff check .`
- CI (`.github/workflows/ci.yml`) todavía corre `python -m pytest` completo; separarlo en tandas queda pendiente de decisión.
- **Base de tests sucia**: `tests/test_platform_settings.py` guarda un playbook «módem custom» en `platform_config` que no se restaura; en una base vieja los e2e H21 muestran «¿Probaste reiniciar el módem custom?». Siempre base limpia.
