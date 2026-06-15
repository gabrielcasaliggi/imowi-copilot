"""Utilidades de seguridad — hashing de contraseñas y validación."""

from __future__ import annotations

import re

import bcrypt

_MIN_PASSWORD_LEN = 6
_BCRYPT_PREFIX = "$2"


def hash_password(plain: str) -> str:
    if not valid_password(plain):
        raise ValueError(f"La clave debe tener al menos {_MIN_PASSWORD_LEN} caracteres")
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
    return plain == stored


def valid_password(plain: str) -> bool:
    return len((plain or "").strip()) >= _MIN_PASSWORD_LEN


def valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", (email or "").strip()))
