"""Observabilidad opcional (Sentry). Activa con SENTRY_DSN."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("operations_hub")


def init_sentry() -> bool:
    """Inicializa Sentry si hay DSN. Retorna True si quedó activo."""
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
    logger.info("Sentry activo (env=%s, traces=%.2f)", env, traces)
    return True
