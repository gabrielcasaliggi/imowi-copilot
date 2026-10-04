# Cómo correr la suite de tests (dos tandas)

La suite completa ya no entra en una sola corrida de 5 minutos, así que se corre en **dos tandas**. El marcador
`e2e_conv` (registrado en `pyproject.toml`) se aplica automáticamente a todo lo que está en `tests/e2e_conv/`
(`tests/e2e_conv/conftest.py`).

| Tanda | Qué corre | Comando | Total esperado | Tiempo aprox. |
|---|---|---|---|---|
| 1 — escenarios | `tests/e2e_conv` (harness, invariantes, 14+ escenarios y hallazgos) | `.venv/bin/python -m pytest -m e2e_conv` | **32 passed, 48 xfailed** (1930 deseleccionados) | ~30 s (28 s medidos) |
| 2 — resto | todo lo demás | `.venv/bin/python -m pytest -m "not e2e_conv"` | **1930 passed** (pytest informó 81 deseleccionados: 80 son de `e2e_conv`; el otro no lo identifiqué) | ~4,5 min (272 s medidos) |

Total del repo: **1962 passed + 48 xfailed** (suma de ambas tandas).

Notas
- Los 48 `xfail` son **estrictos** (`xfail(strict=True)`): cuando un arreglo hace pasar uno, el test falla con XPASS y hay que
  retirar el marcador. Para ver que cada uno reproduce su bug: `pytest -m e2e_conv --runxfail` (deben fallar exactamente esos 48).
- La tanda 2 está cerca del tope de 5 minutos. Si hace falta partirla, se puede dividir por archivos:
  `ls tests/test_*.py | head -78` y `ls tests/test_*.py | tail -n +79`, pasados a `pytest -m "not e2e_conv" <archivos>`.
- Las dos tandas usan la misma base SQLite de tests (`data/test_estate.db`): **no correrlas en paralelo**.
- Siempre con `timeout`, por ejemplo `timeout 300 .venv/bin/python -m pytest -m e2e_conv`.
- `ruff`: `.venv/bin/ruff check .`
- CI (`.github/workflows/ci.yml`) todavía corre `python -m pytest` completo; separarlo en dos pasos queda pendiente de decisión.
