"""Rate-limit / lockout / auditoría de login (consola y portal)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import (
    AUTH_LOCKOUT_MINUTES,
    AUTH_LOGIN_MAX_FAILURES,
    AUTH_LOGIN_WINDOW_MINUTES,
)
from app.estate.models import AuthLockout, AuthLoginEvent, AuthTokenDenylist


def _now() -> datetime:
    return datetime.now(UTC)


def actor_key(superficie: str, actor: str, ip: str) -> str:
    return f"{superficie}|{(actor or '').strip().lower()}|{(ip or '').strip()}"


def is_locked(db: Session, *, superficie: str, actor: str, ip: str) -> bool:
    key = actor_key(superficie, actor, ip)
    row = db.scalar(select(AuthLockout).where(AuthLockout.actor_key == key))
    if not row or not row.locked_until:
        return False
    until = row.locked_until
    if until.tzinfo is None:
        until = until.replace(tzinfo=UTC)
    if until > _now():
        return True
    # expiró
    row.locked_until = None
    row.failures = 0
    db.commit()
    return False


def record_login_event(
    db: Session,
    *,
    superficie: str,
    actor: str,
    ip: str,
    ok: bool,
    reason: str = "",
    org_slug: str = "",
) -> None:
    db.add(
        AuthLoginEvent(
            superficie=superficie,
            actor=(actor or "")[:160],
            ip=(ip or "")[:64],
            ok="Sí" if ok else "No",
            reason=(reason or "")[:80],
            org_slug=(org_slug or "")[:80],
        )
    )
    db.commit()


def register_failure(db: Session, *, superficie: str, actor: str, ip: str) -> bool:
    """Registra fallo. Retorna True si quedó bloqueado."""
    key = actor_key(superficie, actor, ip)
    row = db.scalar(select(AuthLockout).where(AuthLockout.actor_key == key))
    if not row:
        row = AuthLockout(superficie=superficie, actor_key=key, failures=0)
        db.add(row)
        db.flush()

    # Contar fallos recientes en ventana
    since = _now() - timedelta(minutes=AUTH_LOGIN_WINDOW_MINUTES)
    recent = list(
        db.scalars(
            select(AuthLoginEvent)
            .where(
                AuthLoginEvent.superficie == superficie,
                AuthLoginEvent.actor == (actor or "").strip().lower()[:160],
                AuthLoginEvent.ok == "No",
                AuthLoginEvent.created_at >= since,
            )
            .order_by(AuthLoginEvent.created_at.desc())
        ).all()
    )
    # También contar por IP si actor vacío
    if not actor:
        recent = list(
            db.scalars(
                select(AuthLoginEvent)
                .where(
                    AuthLoginEvent.superficie == superficie,
                    AuthLoginEvent.ip == (ip or "")[:64],
                    AuthLoginEvent.ok == "No",
                    AuthLoginEvent.created_at >= since,
                )
            ).all()
        )

    row.failures = len(recent) + 1
    locked = False
    if row.failures >= AUTH_LOGIN_MAX_FAILURES:
        row.locked_until = _now() + timedelta(minutes=AUTH_LOCKOUT_MINUTES)
        locked = True
    db.commit()
    return locked


def clear_failures(db: Session, *, superficie: str, actor: str, ip: str) -> None:
    key = actor_key(superficie, actor, ip)
    row = db.scalar(select(AuthLockout).where(AuthLockout.actor_key == key))
    if row:
        row.failures = 0
        row.locked_until = None
        db.commit()


def denylist_add(db: Session, jti: str, exp_at: datetime) -> None:
    if not jti:
        return
    existing = db.get(AuthTokenDenylist, jti)
    if existing:
        return
    db.add(AuthTokenDenylist(jti=jti, exp_at=exp_at))
    db.commit()


def denylist_contains(db: Session, jti: str) -> bool:
    if not jti:
        return False
    row = db.get(AuthTokenDenylist, jti)
    if not row:
        return False
    exp = row.exp_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    if exp < _now():
        db.delete(row)
        db.commit()
        return False
    return True


def list_login_events(
    db: Session,
    *,
    superficie: str | None = None,
    limit: int = 100,
) -> list[AuthLoginEvent]:
    q = select(AuthLoginEvent).order_by(AuthLoginEvent.created_at.desc()).limit(min(limit, 500))
    if superficie:
        q = q.where(AuthLoginEvent.superficie == superficie)
    return list(db.scalars(q).all())
