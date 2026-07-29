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
    ("database", "url"),
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
            "nota": "Cambiar la URL en producción suele requerir reinicio del servicio (Render env).",
        },
        "knowledge": {
            "min_score": KNOWLEDGE_MIN_SCORE,
            "top_k": KNOWLEDGE_TOP_K,
            "max_fragment_chars": KNOWLEDGE_MAX_FRAGMENT_CHARS,
        },
        "canal": {
            "usar_llama_default": True,
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
    if "database" in out and isinstance(out["database"], dict):
        url = out["database"].get("url") or ""
        if url and not str(url).startswith("***") and ":***@" not in str(url):
            out["database"]["url"] = database_url_enmascarada(str(url))
            out["database"]["url_configured"] = True
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
    for section, key in _SECRET_KEYS:
        sec = incoming.get(section)
        if isinstance(sec, dict) and key in sec and _is_masked(str(sec.get(key) or "")):
            sec[key] = current.get(section, {}).get(key, "")

    merged = _deep_merge(current, incoming)
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
    """Playbooks listos para el motor N1 (PasoPlaybook)."""
    raw = resolve_playbooks(db)
    out: dict[str, list[PasoPlaybook]] = {}
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
            out[nombre] = converted
    for nombre, pasos in PLAYBOOKS.items():
        if nombre not in out:
            out[nombre] = list(pasos)
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
    row = db.get(PlatformConfig, CONFIG_ID) if db else None
    return {
        "ai_configured": bool(ai.get("base_url") and ai.get("model")),
        "whatsapp_configured": bool(wa.get("token") and wa.get("phone_number_id")),
        "database_driver": "postgresql" if "postgresql" in (DATABASE_URL or "") else "sqlite",
        "database_url_masked": database_url_enmascarada(),
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
        "updated_by": row.updated_by if row else "",
        "settings": s,
    }
