# Cómo correr la suite de tests (dos tandas)

La suite completa ya no entra en una sola corrida de 5 minutos, así que se corre en **dos tandas**. El marcador
`e2e_conv` (registrado en `pyproject.toml`) se aplica automáticamente a todo lo que está en `tests/e2e_conv/`
(`tests/e2e_conv/conftest.py`).

| Tanda | Qué corre | Comando | Total esperado | Tiempo aprox. |
|---|---|---|---|---|
| 1 — escenarios | `tests/e2e_conv` (harness, invariantes, 14+ escenarios y hallazgos) | `.venv/bin/python -m pytest -m e2e_conv` | **136 passed, 10 xfailed** (2026 deseleccionados) | ~35 s (34 s medidos) |
| 2 — resto | todo lo demás | `.venv/bin/python -m pytest -m "not e2e_conv"` | **2026 passed** | ~6 min (345 s medidos; una corrida dio 405 s) |

Total del repo: **2162 passed + 10 xfailed** (suma de ambas tandas, tras la tanda 3 del contrato de turno).

Notas
- Los 10 `xfail` son **estrictos** (`xfail(strict=True)`): cuando un arreglo hace pasar uno, el test falla con XPASS y hay que
  retirar el marcador. Para ver que cada uno reproduce su bug: `pytest -m e2e_conv --runxfail` (deben fallar exactamente esos 10).
- La tanda 2 **ya supera** los 5 minutos: usar `timeout 570` (o partirla). Para dividirla por archivos:
  `ls tests/test_*.py | head -78` y `ls tests/test_*.py | tail -n +79`, pasados a `pytest -m "not e2e_conv" <archivos>`.
- Las dos tandas usan la misma base SQLite de tests (`data/test_estate.db`): **no correrlas en paralelo**.
- Siempre con `timeout`, por ejemplo `timeout 300 .venv/bin/python -m pytest -m e2e_conv`.
- `ruff`: `.venv/bin/ruff check .`
- CI (`.github/workflows/ci.yml`) todavía corre `python -m pytest` completo; separarlo en dos pasos queda pendiente de decisión.
