"""Importación CSV de usuarios y líneas para cooperativas piloto."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.estate.models import LineaJSC, Organization, User
from app.estate.security import hash_password, valid_email, valid_password

_ROLES_VALIDOS = {"cliente", "ingeniero_noc", "admin_sistema", "admin_org"}
_ALIASES = {
    "nombre": ("nombre", "name", "operador"),
    "email": ("email", "correo", "mail"),
    "telefono": ("telefono", "tel", "phone", "celular"),
    "rol": ("rol", "role"),
    "password": ("password", "clave", "pass"),
    "linea_principal": ("linea_principal", "linea", "msisdn", "numero"),
    "abonado": ("abonado", "titular"),
    "plan": ("plan",),
}


@dataclass
class ImportResult:
    creados: int = 0
    actualizados: int = 0
    lineas_creadas: int = 0
    omitidos: int = 0
    errores: list[str] = field(default_factory=list)
    filas: list[dict] = field(default_factory=list)


def _normalize_header(name: str) -> str:
    key = (name or "").strip().lower().replace(" ", "_")
    for canonical, aliases in _ALIASES.items():
        if key in aliases:
            return canonical
    return key


def _normalize_msisdn(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    return digits[-10:] if len(digits) > 10 else digits


def _parse_rows(text: str) -> list[dict[str, str]]:
    sample = text.strip()
    if not sample:
        return []
    reader = csv.DictReader(io.StringIO(text), skipinitialspace=True)
    if not reader.fieldnames:
        return []
    rows: list[dict[str, str]] = []
    for raw in reader:
        row: dict[str, str] = {}
        for k, v in raw.items():
            if k is None:
                continue
            norm = _normalize_header(k)
            row[norm] = (v or "").strip()
        if any(row.values()):
            rows.append(row)
    return rows


def import_usuarios_csv(
    db: Session,
    org: Organization,
    csv_text: str,
    *,
    default_password: str = "cliente",
    default_rol: str = "cliente",
) -> ImportResult:
    result = ImportResult()
    rows = _parse_rows(csv_text)
    if not rows:
        result.errores.append("El archivo CSV está vacío o no tiene encabezados válidos.")
        return result

    for idx, row in enumerate(rows, start=2):
        nombre = row.get("nombre", "")
        email = row.get("email", "").lower()
        if not nombre or not email:
            result.omitidos += 1
            result.errores.append(f"Fila {idx}: nombre y email son obligatorios.")
            continue
        if not valid_email(email):
            result.omitidos += 1
            result.errores.append(f"Fila {idx}: email '{email}' inválido.")
            continue

        rol = (row.get("rol") or default_rol).lower()
        if rol in ("operador", "cooperativa"):
            rol = "cliente"
        if rol not in _ROLES_VALIDOS:
            result.omitidos += 1
            result.errores.append(f"Fila {idx}: rol '{rol}' no válido.")
            continue

        password = row.get("password") or default_password
        if not valid_password(password):
            result.omitidos += 1
            result.errores.append(f"Fila {idx}: clave demasiado corta (mínimo 6 caracteres).")
            continue
        telefono = row.get("telefono", "")
        linea = _normalize_msisdn(row.get("linea_principal", ""))

        existing = db.scalar(select(User).where(User.email == email))
        if existing:
            if existing.organizacion_id != org.id:
                result.omitidos += 1
                result.errores.append(f"Fila {idx}: email {email} ya existe en otra cooperativa.")
                continue
            existing.nombre = nombre
            existing.rol = rol
            existing.telefono = telefono
            existing.linea_principal = linea
            if row.get("password"):
                existing.password = hash_password(password)
                existing.must_change_password = "No"
            result.actualizados += 1
        else:
            db.add(
                User(
                    organizacion_id=org.id,
                    email=email,
                    nombre=nombre,
                    password=hash_password(password),
                    rol=rol,
                    telefono=telefono,
                    linea_principal=linea,
                    must_change_password="Sí" if password == default_password else "No",
                )
            )
            result.creados += 1

        if linea:
            abonado = row.get("abonado") or nombre
            plan = row.get("plan") or "Móvil"
            linea_row = db.scalar(
                select(LineaJSC).where(
                    LineaJSC.organizacion_id == org.id,
                    LineaJSC.msisdn == linea,
                )
            )
            if not linea_row:
                db.add(
                    LineaJSC(
                        organizacion_id=org.id,
                        msisdn=linea,
                        abonado=abonado,
                        plan=plan,
                        apn=f"internet.{org.slug.replace('coop-', '')}.ar",
                    )
                )
                result.lineas_creadas += 1

        result.filas.append(
            {
                "email": email,
                "nombre": nombre,
                "rol": rol,
                "linea_principal": linea,
            }
        )

    db.commit()
    return result
