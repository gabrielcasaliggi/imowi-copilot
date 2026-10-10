"""Higiene del entorno de tests: nada del .env real entra al proceso de pytest.

app/config.py llama a load_dotenv() al importarse. En tests eso cargaría las claves del
.env de la máquina (p. ej. AI_API_KEY) y los tests podrían hablar con sistemas reales.

Los mensajes de error nombran variables, nunca valores.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

REPO = Path(__file__).resolve().parent.parent
ENV_REAL = REPO / ".env"

# Credenciales y endpoints de sistemas reales que lee la app (app/config.py y servicios).
SENSIBLES = (
    "AI_API_KEY",
    "AI_BASE_URL",
    "AUTH_SECRET",
    "PORTAL_AUTH_SECRET",
    "ADMIN_PASSWORD",
    "COOP_PASSWORD",
    "MOCK_USERS_JSON",
    "BILLTRACK_DATABASE_URL",
    "BILLTRACK_HOST",
    "BILLTRACK_USER",
    "BILLTRACK_PASSWORD",
    "BCM_API_URL",
    "BCM_USER",
    "BCM_APP_PASS",
    "UISP_BASE_URL",
    "UISP_API_TOKEN",
    "RADIUS_API_KEY",
    "RADIUS_API_TOKEN",
    "SOPNET_API_URL",
    "SOPNET_USER",
    "SOPNET_APP_PASS",
    "OV_BATAN_API_URL",
    "OV_BATAN_API_USER",
    "OV_BATAN_API_PASSWORD",
    "SENTRY_DSN",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "SMTP_HOST",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "WHATSAPP_TOKEN",
    "WHATSAPP_APP_SECRET",
    "WHATSAPP_VERIFY_TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_WEBHOOK_SECRET",
)

FUGA = pytest.mark.xfail(
    strict=True,
    reason="app/config.py ejecuta load_dotenv() también en el proceso de tests",
)


def _cargadas_desde(env_file: Path, nombres: tuple[str, ...] | None = None) -> list[str]:
    """Nombres cuyo valor en os.environ es idéntico al del archivo (sin exponer valores)."""
    if not env_file.is_file():
        return []
    valores = dotenv_values(env_file)
    return sorted(
        k
        for k, v in valores.items()
        if v and (nombres is None or k in nombres) and os.environ.get(k) == v
    )


@FUGA
def test_load_dotenv_de_la_app_no_carga_nada_en_tests(tmp_path):
    """Mecanismo, también en CI (sin .env): la función que usa app.config no toca el entorno."""
    import app.config as config

    nombre = "HIGIENE_ENTORNO_CLAVE_FALSA"
    falso = tmp_path / ".env"
    falso.write_text(f"{nombre}=valor-falso\n", encoding="utf-8")
    # Nunca comparar contra os.environ entero: pytest imprimiría todo el entorno.
    assert os.environ.get(nombre) is None
    try:
        config.load_dotenv(falso)
        cargada = os.environ.get(nombre) is not None
        assert not cargada, f"{nombre} quedó cargada en el entorno"
    finally:
        os.environ.pop(nombre, None)


@FUGA
def test_sensibles_no_vienen_del_env_real():
    if not ENV_REAL.is_file():
        pytest.skip("sin .env en esta máquina: lo cubre el test del mecanismo")
    fugadas = _cargadas_desde(ENV_REAL, SENSIBLES)
    assert not fugadas, f"variables sensibles cargadas desde .env: {fugadas}"


@FUGA
def test_ninguna_clave_del_env_real_en_el_entorno():
    if not ENV_REAL.is_file():
        pytest.skip("sin .env en esta máquina: lo cubre el test del mecanismo")
    fugadas = _cargadas_desde(ENV_REAL)
    assert not fugadas, f"claves cargadas desde .env: {fugadas}"


def test_database_url_es_la_sqlite_de_tests():
    url = os.environ.get("DATABASE_URL", "")
    # Booleanos antes del assert: si falla, pytest no muestra la URL.
    es_sqlite = url.startswith("sqlite:///")
    es_base_de_tests = url.endswith("test_estate.db")
    assert es_sqlite, "DATABASE_URL no es SQLite"
    assert es_base_de_tests, "DATABASE_URL no es la base de tests"
    assert os.environ.get("BILLTRACK_DATABASE_URL") is None, "BILLTRACK_DATABASE_URL definida"
