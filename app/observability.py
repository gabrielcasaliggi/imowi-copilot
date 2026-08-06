"""Observabilidad opcional (Sentry). Activa con SENTRY_DSN."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("operations_hub")

_SENTRY_INIT = False


def init_sentry() -> bool:
    """Inicializa Sentry si hay DSN. Retorna True si quedó activo."""
    global _SENTRY_INIT
    dsn = (os.getenv("SENTRY_DSN") or "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:
        logger.warning("SENTRY_DSN definido pero falta paquete sentry-sdk")
        return False

    env = (os.getenv("APP_ENV") or "development").strip().lower()
    traces = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1" if env == "production" else "0"))
    sentry_sdk.init(
        dsn=dsn,
        environment=env,
        traces_sample_rate=max(0.0, min(traces, 1.0)),
        send_default_pii=False,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
    )
    _SENTRY_INIT = True
    logger.info("Sentry activo (env=%s, traces=%.2f)", env, traces)
    return True


def sentry_activo() -> bool:
    """True si Sentry quedó inicializado en este proceso."""
    if _SENTRY_INIT:
        return True
    try:
        import sentry_sdk

        get_client = getattr(sentry_sdk, "get_client", None)
        if callable(get_client):
            client = get_client()
            return bool(client) and getattr(client, "dsn", None) is not None
        return False
    except Exception:
        return False
