# Cómo correr la suite de tests (dos tandas)

La suite completa ya no entra en una sola corrida de 5 minutos, así que se corre en **dos tandas**. El marcador
`e2e_conv` (registrado en `pyproject.toml`) se aplica automáticamente a todo lo que está en `tests/e2e_conv/`
(`tests/e2e_conv/conftest.py`).

| Tanda | Qué corre | Comando | Total esperado | Tiempo medido |
|---|---|---|---|---|
| 1 — escenarios | `tests/e2e_conv` (harness, invariantes, escenarios y hallazgos) | `timeout 900 .venv/bin/python -m pytest -m e2e_conv` | **757 passed, 10 xfailed** | 73–657 s según carga |
| 2a — resto, mitad 1 | `tests/test_*.py`, archivos 1–115 en orden alfabético (hasta `test_h27g_confirmaciones.py`) | `timeout 900 .venv/bin/python -m pytest -m "not e2e_conv" $(ls tests/test_*.py \| head -115)` | **1736 passed** | 78–81 s |
| 2b — resto, mitad 2 | `tests/test_*.py`, del archivo 116 en adelante | `timeout 900 .venv/bin/python -m pytest -m "not e2e_conv" $(ls tests/test_*.py \| tail -n +116)` | **861 passed, 0 xfailed** | 71–96 s |

Total del repo: **3354 passed, 10 xfailed** (757 + 1736 + 861). Suite completa en un proceso con base limpia: 3354 passed, 10 xfailed, 860 s (H-APP-2: +18 de `tests/test_portal_ticket_view.py`; higiene de tests: +8 de `tests/test_higiene_entorno.py` y `tests/test_platform_settings.py`; todos caen en la mitad 2; H31: +18 de `tests/test_h31_clave_wifi_enmascarada.py`; H32b: +10 de `tests/test_h32b_ssid_wifi_literal.py`; los dos caen en la mitad 2; H32: +12 de `tests/test_h32_clave_wifi_literal.py`, que cae primero en la mitad 2; H27g: +90 de `tests/test_h27g_confirmaciones.py` y `tests/e2e_conv/test_h27g_copy.py`; H27k retiró 8 xfails y sumó 6 tests; los 10 xfails estrictos que quedan son de H27-L2/L3/L4, limitaciones conocidas del legacy, ver la auditoría). H17 A, B y C cerrados; H22 (Fix 4) cerrado; H21 Fix 1, Fix 2 y Fix 3 cerrados; H24, H25, H27a, H27k, H27g, H28, H31, H32 y H32b cerrados. Abiertos: H17-B2 y H17-D (afirmación suelta), H20, H23, H26; H27-L1..L4 quedan como limitaciones conocidas del legacy.

Notas
- **Tiempos**: la partición se hizo por tiempo medido (`--durations=0`: 853 s de tests en total; `test_helpdesk_features.py` solo es 203 s,
  `test_tickets_intelligence_api` 106 s, `test_kb_contributions` 79 s, `test_rbac` 77 s, `test_analytics_export` 74 s). Con la máquina cargada
  (Cursor/Chrome abiertos) cada mitad llegó a tardar 7–8 min (330 s y 226 s en la última corrida sin carga); en la tanda 3, sin carga, la tanda 2 entera tardó 345 s (≈3 min por mitad). Si una mitad
  pasa de 6 min de forma sostenida, mover el corte o partir en tres.
- **Rebalancear**: al agregar archivos `test_*.py` el corte `head -115` se corre; los archivos nuevos que quedan antes de `test_helpdesk_features.py`
  desplazan ese archivo a la mitad 2. Volver a medir con `--durations=0` si el desbalance crece. **Ya pasó** con `test_falla_optica_afirmacion.py` (Paso 4):
  `test_helpdesk_features.py` (el más lento) corre hoy en la mitad 2; con H27g (`test_h27g_confirmaciones.py`) el corte cae en ese archivo y `test_handoff_notify.py` pasa a la mitad 2; si la mitad 2 pasa de 6 min, correr el corte hasta incluir `test_helpdesk_features.py` (hoy `head -117` / `tail -n +118`).
- Los invariantes I1–I12 corren en todos los escenarios (`inv.violaciones`); I11/I12 son los de ticket ligado (H24). Hoy hay 10 `xfail` estrictos en `tests/e2e_conv/test_h27a_planta.py`, todos con el hallazgo en el motivo: H27-L2/L3/L4 (legacy, fuera de H27a/H27k). Si se agrega uno, es **estricto** (`xfail(strict=True)`): cuando un arreglo lo hace pasar, el test falla con XPASS y hay que
  retirar el marcador. Para ver que cada uno reproduce su bug: `pytest -m e2e_conv --runxfail` (deben fallar exactamente los marcados).
- Las tandas usan la misma base SQLite de tests (`data/test_estate.db`): **no correrlas en paralelo**.
- **Antes de subir**, correr la suite completa como el CI: un solo proceso, con la base de tests **limpia** (mover `data/test_estate.db`) y `ruff check .`. Una base local vieja puede esconder fallos que el CI sí ve (pasó con los tests de RC-4: el playbook de la base tenía otros pasos).
- **Tanda 1 y su timeout**: con H31 midió 580 s contra el viejo `timeout 600`; en la higiene de tests (2026-10) midió 657 s, que con 600 se habría cortado. Desde entonces el comando usa `timeout 900`. Si se corta, no concluir nada: subir el timeout y volver a correr; si el margen baja de ~60 s de forma sostenida, subirlo en la tabla.
- Siempre con `timeout`. Una corrida con `timeout 570` se cortó sin dejar resultado: guardar la salida completa en un archivo, no filtrar con `grep`.
- **Entorno aislado**: los tests **no cargan el `.env` real**. `tests/conftest.py` reemplaza `dotenv.load_dotenv` por un no-op antes de importar `app.*` (producción no cambia), fuerza la SQLite de tests y `tests/test_higiene_entorno.py` falla si alguna clave del `.env` aparece en el entorno. Un test que necesite una variable la define él mismo (`monkeypatch.setenv`).
- **Guardia de red**: `tests/guardia_red.py` (instalada desde `conftest.py`) bloquea toda conexión a hosts no locales, por socket de Python y por psycopg. Permitidos: loopback, `localhost`, `testserver` y sockets unix. Lo bloqueado levanta `ConexionBloqueadaEnTests` y aparece al final de la corrida en la sección **«guardia de red: conexiones no locales bloqueadas»**, con el test y la cantidad (nunca el host); si la sección no aparece, no hubo intentos. Para buscarla en un log guardado: `grep -A20 "guardia de red" <log>`.
- `ruff`: `.venv/bin/ruff check .`
- CI (`.github/workflows/ci.yml`) todavía corre `python -m pytest` completo; separarlo en tandas queda pendiente de decisión.
- **Base de tests sucia**: hasta 2026-10 `tests/test_platform_settings.py` dejaba en `platform_config` un playbook «módem custom» y BillTrack habilitado (los logins abrían conexiones a un Postgres local); hoy un fixture restaura la configuración después de cada test. Igual, siempre base limpia: una base vieja puede arrastrar ese estado de corridas anteriores.
