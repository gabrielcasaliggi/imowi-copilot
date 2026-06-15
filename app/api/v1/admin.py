"""Administración de cooperativas, usuarios e importación CSV — solo admin imowi."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.v1.schemas import OrganizationCreate, OrganizationUpdate, UserCreate
from app.auth import UsuarioSesion, requiere_admin
from app.estate import repository as repo
from app.estate.database import get_db
from app.estate.import_csv import import_usuarios_csv

router = APIRouter(tags=["Admin"])


def _org_or_404(db: Session, slug: str):
    org = repo.get_org_by_slug(db, slug)
    if not org:
        raise HTTPException(404, f"Cooperativa '{slug}' no encontrada")
    return org


@router.get("/admin/organizations")
def list_organizations_admin(
    _: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    return {"organizaciones": repo.list_organizations_admin(db)}


@router.post("/admin/organizations")
def create_organization(
    body: OrganizationCreate,
    _: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    if not body.nombre.strip():
        raise HTTPException(400, "El nombre es obligatorio")
    org = repo.create_organization(
        db,
        nombre=body.nombre.strip(),
        slug=body.slug.strip() if body.slug else None,
        logo_label=body.logo_label,
        brand_color=body.brand_color,
    )
    return {
        "status": "ok",
        "organizacion": {
            "slug": org.slug,
            "nombre": org.nombre,
            "brand_color": org.brand_color,
            "logo_label": org.logo_label,
            **repo.organization_stats(db, org.id),
        },
    }


@router.put("/admin/organizations/{slug}")
def update_organization(
    slug: str,
    body: OrganizationUpdate,
    _: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    if slug == "imowi" and body.nombre and body.nombre.strip().lower() != "imowi noc":
        pass  # permitir renombrar display pero no bloquear
    org = repo.update_organization(
        db,
        slug,
        nombre=body.nombre.strip() if body.nombre else None,
        logo_label=body.logo_label,
        brand_color=body.brand_color,
    )
    if not org:
        raise HTTPException(404, f"Cooperativa '{slug}' no encontrada")
    return {
        "status": "ok",
        "organizacion": {
            "slug": org.slug,
            "nombre": org.nombre,
            "brand_color": org.brand_color,
            "logo_label": org.logo_label,
            **repo.organization_stats(db, org.id),
        },
    }


@router.get("/admin/organizations/{slug}/users")
def list_organization_users(
    slug: str,
    _: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    org = _org_or_404(db, slug)
    users = repo.list_users_for_org(db, org.id)
    return {
        "slug": slug,
        "usuarios": [repo.user_to_dict(u) for u in users],
    }


@router.post("/admin/organizations/{slug}/users")
def create_organization_user(
    slug: str,
    body: UserCreate,
    _: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    org = _org_or_404(db, slug)
    if not body.email.strip() or not body.nombre.strip():
        raise HTTPException(400, "Email y nombre son obligatorios")
    try:
        user = repo.create_user_for_org(
            db,
            org.id,
            email=body.email.strip(),
            nombre=body.nombre.strip(),
            password=body.password or "cliente",
            rol=body.rol or "cliente",
            telefono=body.telefono,
            linea_principal=body.linea_principal,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"status": "ok", "usuario": repo.user_to_dict(user)}


@router.post("/admin/organizations/{slug}/import-csv")
async def import_organization_csv(
    slug: str,
    file: UploadFile = File(...),
    _: UsuarioSesion = Depends(requiere_admin),
    db: Session = Depends(get_db),
):
    org = _org_or_404(db, slug)
    if org.slug == "imowi":
        raise HTTPException(400, "Importá usuarios en una cooperativa operativa, no en imowi NOC")
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "El CSV debe estar en UTF-8") from exc

    result = import_usuarios_csv(db, org, text)
    return {
        "status": "ok",
        "slug": slug,
        "creados": result.creados,
        "actualizados": result.actualizados,
        "lineas_creadas": result.lineas_creadas,
        "omitidos": result.omitidos,
        "errores": result.errores,
        "filas": result.filas,
    }
