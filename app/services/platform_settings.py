"""Configuración de plataforma — persistida en DB, con fallback a variables de entorno."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from app.config import (
    AI_API_KEY,
    AI_BASE_URL,
    AI_MODEL,
    BILLTRACK_DATABASE_URL,
    BILLTRACK_DBNAME,
    BILLTRACK_ENABLED,
    BILLTRACK_HOST,
    BILLTRACK_PASSWORD,
    BILLTRACK_PORT,
    BILLTRACK_SSLMODE,
    BILLTRACK_USER,
    DATABASE_SSLMODE,
    DATABASE_URL,
    KNOWLEDGE_MAX_FRAGMENT_CHARS,
    KNOWLEDGE_MIN_SCORE,
    KNOWLEDGE_TOP_K,
    WHATSAPP_APP_SECRET,
    WHATSAPP_DEFAULT_ORG_SLUG,
    WHATSAPP_PHONE_NUMBER_ID,
    WHATSAPP_TOKEN,
    WHATSAPP_VERIFY_TOKEN,
    database_url_enmascarada,
)
from app.domain.flujos_abonado import PLAYBOOKS, PasoPlaybook
from app.estate.models import PlatformConfig

CONFIG_ID = "default"

_SECRET_KEYS = {
    ("ai", "api_key"),
    ("whatsapp", "token"),
    ("whatsapp", "app_secret"),
    ("billtrack", "password"),
}

_URL_SECRET_KEYS = {
    ("database", "url"),
    ("billtrack", "url"),
}


def _default_payload() -> dict[str, Any]:
    return {
        "ai": {
            "base_url": AI_BASE_URL,
            "api_key": AI_API_KEY,
            "model": AI_MODEL,
        },
        "whatsapp": {
            "token": WHATSAPP_TOKEN,
            "phone_number_id": WHATSAPP_PHONE_NUMBER_ID,
            "verify_token": WHATSAPP_VERIFY_TOKEN or "ops-hub-wa-verify",
            "app_secret": WHATSAPP_APP_SECRET,
            "default_org_slug": WHATSAPP_DEFAULT_ORG_SLUG or "coop-batan",
        },
        "database": {
            "url": DATABASE_URL,
            "sslmode": DATABASE_SSLMODE,
            "nota": (
                "Data Estate del sistema (tickets, config, canal). "
                "No confundir con BillTrack. Cambiar en producción suele requerir reinicio."
            ),
        },
        "billtrack": {
            "enabled": BILLTRACK_ENABLED,
            "host": BILLTRACK_HOST,
            "port": BILLTRACK_PORT,
            "user": BILLTRACK_USER,
            "password": BILLTRACK_PASSWORD,
            "dbname": BILLTRACK_DBNAME,
            "url": BILLTRACK_DATABASE_URL,
            "sslmode": BILLTRACK_SSLMODE,
            "nota": (
                "Postgres externo de solo lectura: padrón de clientes para que el bot "
                "valide acciones. Independiente del Data Estate. Este servidor suele "
                "requerir sslmode=disable."
            ),
        },
        "knowledge": {
            "min_score": KNOWLEDGE_MIN_SCORE,
            "top_k": KNOWLEDGE_TOP_K,
            "max_fragment_chars": KNOWLEDGE_MAX_FRAGMENT_CHARS,
        },
        "canal": {
            "usar_llama_default": True,
            "diagnostico_ia": True,
        },
        "playbooks": {
            nombre: [
                {"id": p.id, "pregunta": p.pregunta}
                for p in pasos
            ]
            for nombre, pasos in PLAYBOOKS.items()
        },
    }


def _load_raw(db: Session) -> dict[str, Any]:
    row = db.get(PlatformConfig, CONFIG_ID)
    if not row or not row.payload_json:
        return {}
    try:
        data = json.loads(row.payload_json)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def get_merged_settings(db: Session | None = None) -> dict[str, Any]:
    base = _default_payload()
    if db is None:
        return base
    stored = _load_raw(db)
    return _deep_merge(base, stored)


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = deepcopy(base)
    for k, v in (overlay or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def mask_settings(payload: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(payload)
    for section, key in _SECRET_KEYS:
        if section in out and isinstance(out[section], dict) and key in out[section]:
            val = str(out[section].get(key) or "")
            if not val:
                out[section][key] = ""
                out[section][f"{key}_configured"] = False
            else:
                out[section][key] = _mask(val)
                out[section][f"{key}_configured"] = True
    for section, key in _URL_SECRET_KEYS:
        if section in out and isinstance(out[section], dict) and key in out[section]:
            url = str(out[section].get(key) or "")
            if not url:
                out[section][key] = ""
                out[section][f"{key}_configured"] = False
            else:
                out[section][key] = database_url_enmascarada(url)
                out[section][f"{key}_configured"] = True
    return out


def _mask(val: str) -> str:
    if len(val) <= 8:
        return "***"
    return val[:3] + "***" + val[-3:]


def _is_masked(val: str) -> bool:
    return "***" in (val or "")


def save_settings(
    db: Session,
    patch: dict[str, Any],
    *,
    actor: str = "",
) -> dict[str, Any]:
    current = get_merged_settings(db)
    incoming = deepcopy(patch or {})

    # No pisar secretos si el cliente reenvía valor enmascarado
    for section, key in (*_SECRET_KEYS, *_URL_SECRET_KEYS):
        sec = incoming.get(section)
        if isinstance(sec, dict) and key in sec and _is_masked(str(sec.get(key) or "")):
            sec[key] = current.get(section, {}).get(key, "")

    merged = _deep_merge(current, incoming)

    # BillTrack: reconstruir URL con password escapado (evita timeout por ':' en la pass)
    bt = merged.get("billtrack")
    if isinstance(bt, dict):
        from app.services.billtrack import connection_params

        built = connection_params(bt)
        if built.get("url"):
            bt["url"] = built["url"]
        if built.get("sslmode"):
            bt["sslmode"] = built["sslmode"]

    row = db.get(PlatformConfig, CONFIG_ID)
    if not row:
        row = PlatformConfig(id=CONFIG_ID, payload_json="{}")
        db.add(row)
    row.payload_json = json.dumps(merged, ensure_ascii=False)
    row.updated_by = actor or ""
    db.commit()
    db.refresh(row)
    return merged


def resolve_ai(db: Session | None = None) -> dict[str, str]:
    s = get_merged_settings(db)["ai"]
    return {
        "base_url": str(s.get("base_url") or AI_BASE_URL),
        "api_key": str(s.get("api_key") or AI_API_KEY),
        "model": str(s.get("model") or AI_MODEL),
    }


def resolve_whatsapp(db: Session | None = None) -> dict[str, str]:
    s = get_merged_settings(db)["whatsapp"]
    return {
        "token": str(s.get("token") or WHATSAPP_TOKEN),
        "phone_number_id": str(s.get("phone_number_id") or WHATSAPP_PHONE_NUMBER_ID),
        "verify_token": str(s.get("verify_token") or WHATSAPP_VERIFY_TOKEN or "ops-hub-wa-verify"),
        "app_secret": str(s.get("app_secret") or WHATSAPP_APP_SECRET),
        "default_org_slug": str(s.get("default_org_slug") or WHATSAPP_DEFAULT_ORG_SLUG or "coop-batan"),
    }


def resolve_billtrack(db: Session | None = None) -> dict[str, Any]:
    """Credenciales del Postgres externo BillTrack (consulta de clientes)."""
    from app.services.billtrack import connection_params, parse_postgres_url

    s = get_merged_settings(db).get("billtrack") or {}
    if not isinstance(s, dict):
        s = {}
    enabled_raw = s.get("enabled")
    if isinstance(enabled_raw, str):
        enabled = enabled_raw.strip().lower() in ("1", "true", "yes", "on")
    else:
        enabled = bool(enabled_raw) if enabled_raw is not None else BILLTRACK_ENABLED

    host = str(s.get("host") or BILLTRACK_HOST or "").strip()
    user = str(s.get("user") or BILLTRACK_USER or "").strip()
    password = str(s.get("password") if s.get("password") is not None else BILLTRACK_PASSWORD)
    dbname = str(s.get("dbname") or BILLTRACK_DBNAME or "postgres").strip() or "postgres"
    port = str(s.get("port") or BILLTRACK_PORT or "5432").strip() or "5432"
    url = str(s.get("url") or BILLTRACK_DATABASE_URL or "").strip()
    sslmode = str(s.get("sslmode") or BILLTRACK_SSLMODE or "disable").strip() or "disable"

    # Si solo hay URL (legacy/env), completar campos visibles
    if url and not host:
        parsed = parse_postgres_url(url)
        host = parsed.get("host") or host
        user = parsed.get("user") or user
        dbname = parsed.get("dbname") or dbname
        port = parsed.get("port") or port

    cfg = {
        "enabled": enabled,
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "dbname": dbname,
        "url": url,
        "sslmode": sslmode,
        "nota": str(s.get("nota") or ""),
    }
    built = connection_params(cfg)
    cfg["url"] = built["url"] or url
    return cfg


def resolve_knowledge(db: Session | None = None) -> dict[str, float | int]:
    s = get_merged_settings(db)["knowledge"]
    return {
        "min_score": float(s.get("min_score") if s.get("min_score") is not None else KNOWLEDGE_MIN_SCORE),
        "top_k": int(s.get("top_k") if s.get("top_k") is not None else KNOWLEDGE_TOP_K),
        "max_fragment_chars": int(
            s.get("max_fragment_chars")
            if s.get("max_fragment_chars") is not None
            else KNOWLEDGE_MAX_FRAGMENT_CHARS
        ),
    }


def resolve_canal_usar_llama(db: Session | None = None) -> bool:
    """Si el canal abonado (portal/WA) debe redactar con la IA configurada en admin."""
    s = get_merged_settings(db).get("canal") or {}
    raw = s.get("usar_llama_default", True)
    if isinstance(raw, str):
        return raw.strip().lower() in ("1", "true", "yes", "on", "si", "sí")
    return bool(raw) if raw is not None else True


def resolve_canal_diagnostico_ia(db: Session | None = None) -> bool:
    """Si N1 técnico usa IA para diagnosticar (playbook = checklist)."""
    s = get_merged_settings(db).get("canal") or {}
    raw = s.get("diagnostico_ia", True)
    if isinstance(raw, str):
        return raw.strip().lower() in ("1", "true", "yes", "on", "si", "sí")
    return bool(raw) if raw is not None else True


def resolve_playbooks(db: Session | None = None) -> dict[str, list[dict[str, str]]]:
    s = get_merged_settings(db)
    pb = s.get("playbooks") or {}
    if not isinstance(pb, dict) or not pb:
        return {
            nombre: [{"id": p.id, "pregunta": p.pregunta} for p in pasos]
            for nombre, pasos in PLAYBOOKS.items()
        }
    return pb


def playbooks_as_pasos(db: Session | None = None) -> dict[str, list[PasoPlaybook]]:
    """Playbooks listos para el motor N1 (PasoPlaybook).

    Defaults de código como base. Si el admin guardó pasos para una clave,
    esa lista reemplaza por completo al default (override total).
    Claves solo en código (sin override) siguen saliendo del default.
    """
    raw = resolve_playbooks(db)
    stored: dict[str, list[PasoPlaybook]] = {}
    for nombre, pasos in raw.items():
        converted: list[PasoPlaybook] = []
        for p in pasos or []:
            if isinstance(p, dict):
                pid = str(p.get("id") or "").strip() or "paso"
                pregunta = str(p.get("pregunta") or "").strip()
                if pregunta:
                    converted.append(PasoPlaybook(id=pid, pregunta=pregunta))
            elif isinstance(p, PasoPlaybook):
                converted.append(p)
        if converted:
            stored[nombre] = converted

    out: dict[str, list[PasoPlaybook]] = {n: list(ps) for n, ps in PLAYBOOKS.items()}
    for nombre, pasos in stored.items():
        out[nombre] = pasos
    return out


def with_db_session(fn):
    """Ejecuta fn(db) con sesión corta; si falla, fn(None)."""

    def _wrap(*args, **kwargs):
        try:
            from app.estate.database import get_session_factory

            db = get_session_factory()()
            try:
                return fn(db, *args, **kwargs)
            finally:
                db.close()
        except Exception:
            return fn(None, *args, **kwargs)

    return _wrap


def public_status(db: Session | None = None) -> dict[str, Any]:
    """Estado no sensible para el panel (sin secretos)."""
    s = mask_settings(get_merged_settings(db))
    wa = resolve_whatsapp(db)
    ai = resolve_ai(db)
    bt = resolve_billtrack(db)
    row = db.get(PlatformConfig, CONFIG_ID) if db else None
    bt_url = str(bt.get("url") or "")
    return {
        "ai_configured": bool(ai.get("base_url") and ai.get("model")),
        "whatsapp_configured": bool(wa.get("token") and wa.get("phone_number_id")),
        "database_driver": "postgresql" if "postgresql" in (DATABASE_URL or "") else "sqlite",
        "database_url_masked": database_url_enmascarada(),
        "billtrack_configured": bool(bt_url or (bt.get("host") and bt.get("user"))),
        "billtrack_enabled": bool(bt.get("enabled") and (bt_url or bt.get("host"))),
        "billtrack_url_masked": database_url_enmascarada(bt_url) if bt_url else "",
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
        "updated_by": row.updated_by if row else "",
        "settings": s,
    }
