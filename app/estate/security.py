"""Utilidades de seguridad — hashing de contraseñas y validación."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

import bcrypt

from app.config import DNI_PEPPER, es_produccion

_MIN_PASSWORD_LEN = 10
_BCRYPT_PREFIX = "$2"
_COMMON_PASSWORDS = frozenset(
    {
        "password",
        "password1",
        "password12",
        "password123",
        "admin",
        "admin123",
        "admin12",
        "123456",
        "12345678",
        "1234567890",
        "qwerty",
        "qwerty123",
        "cliente",
        "demo",
        "changeme",
        "batan1",
        "supervisor",
        "ejecutivo",
        "viamonte",
        "noc123",
        "prueba",
        "coop123",
    }
)


def password_policy_errors(plain: str) -> list[str]:
    """Devuelve lista de incumplimientos de política (vacía = OK)."""
    errors: list[str] = []
    p = plain or ""
    if len(p.strip()) < _MIN_PASSWORD_LEN:
        errors.append(f"mínimo {_MIN_PASSWORD_LEN} caracteres")
    if not re.search(r"[A-ZÁÉÍÓÚÑ]", p):
        errors.append("al menos una mayúscula")
    if not re.search(r"[a-záéíóúñ]", p):
        errors.append("al menos una minúscula")
    if not re.search(r"\d", p):
        errors.append("al menos un dígito")
    if p.strip().lower() in _COMMON_PASSWORDS:
        errors.append("contraseña demasiado común")
    return errors


def hash_password(plain: str, *, enforce_policy: bool = True) -> str:
    if enforce_policy and not valid_password(plain):
        errs = password_policy_errors(plain)
        raise ValueError(
            "La clave no cumple la política: " + (", ".join(errs) if errs else "inválida")
        )
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def is_hashed(stored: str) -> bool:
    return (stored or "").startswith(_BCRYPT_PREFIX)


def verify_password(plain: str, stored: str) -> bool:
    if not plain or not stored:
        return False
    if is_hashed(stored):
        try:
            return bcrypt.checkpw(plain.encode("utf-8"), stored.encode("utf-8"))
        except ValueError:
            return False
    # Legacy plaintext: solo fuera de production
    if es_produccion():
        return False
    return plain == stored


def valid_password(plain: str) -> bool:
    return not password_policy_errors(plain or "")


def valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", (email or "").strip()))


def valid_pin(pin: str) -> bool:
    """PIN portal: 6–8 dígitos."""
    return bool(re.fullmatch(r"\d{6,8}", (pin or "").strip()))


def hash_pin(pin: str) -> str:
    if not valid_pin(pin):
        raise ValueError("El PIN debe tener entre 6 y 8 dígitos")
    return hash_password(pin.strip(), enforce_policy=False)


def verify_pin(plain: str, stored: str) -> bool:
    return verify_password((plain or "").strip(), stored or "")


def normalizar_dni(raw: str) -> str:
    """Quita puntos/espacios; deja solo dígitos."""
    return re.sub(r"\D+", "", (raw or "").strip())


def valid_dni_ar(dni: str) -> bool:
    d = normalizar_dni(dni)
    return len(d) in (7, 8)


def hash_dni(dni_normalized: str) -> str:
    """HMAC-SHA256 del DNI (pepper) — no reversible sin pepper."""
    key = (DNI_PEPPER or "dev-dni-pepper").encode("utf-8")
    return hmac.new(key, normalizar_dni(dni_normalized).encode("utf-8"), hashlib.sha256).hexdigest()


def hash_token(raw: str) -> str:
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


def generate_invite_token() -> str:
    return secrets.token_urlsafe(32)


def generate_otp(length: int = 6) -> str:
    n = max(4, min(8, int(length or 6)))
    upper = 10**n
    return f"{secrets.randbelow(upper):0{n}d}"


def mask_email(email: str) -> str:
    e = (email or "").strip()
    if "@" not in e:
        return "***"
    local, _, domain = e.partition("@")
    if len(local) <= 1:
        masked_local = "*"
    else:
        masked_local = local[0] + "***"
    return f"{masked_local}@{domain}"


def mask_phone(phone: str) -> str:
    digits = re.sub(r"\D+", "", phone or "")
    if len(digits) < 4:
        return "***"
    return f"***{digits[-4:]}"
