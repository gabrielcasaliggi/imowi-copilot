"""Acceso a datos multitenant con aislamiento por organizacion_id."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import ANOMALY_TTL_MINUTES, TICKET_ID_PREFIX
from app.estate.models import (
    CasoConversacion,
    ConversacionCanal,
    KnowledgeArticle,
    KnowledgeContribution,
    LineaJSC,
    NetworkElement,
    NetworkOutage,
    Organization,
    PilotEvent,
    Ticket,
    TicketEvent,
    TicketNotification,
    User,
)
from app.estate.security import hash_password, valid_email, valid_password
from app.estate.sla_engine import apply_sla_to_ticket, compute_sla


def get_org_by_slug(db: Session, slug: str) -> Organization | None:
    return db.scalar(select(Organization).where(Organization.slug == slug))


def get_org_by_id(db: Session, org_id: str) -> Organization | None:
    return db.scalar(select(Organization).where(Organization.id == org_id))


def list_organizations(db: Session) -> list[Organization]:
    return list(db.scalars(select(Organization).order_by(Organization.nombre)).all())


def list_users_for_org(db: Session, org_id: str) -> list[User]:
    return list(db.scalars(select(User).where(User.organizacion_id == org_id)).all())


def slugify_org_name(nombre: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (nombre or "").lower()).strip("-")
    if not base:
        base = "nueva"
    slug = base if base.startswith("coop-") else f"coop-{base}"
    return slug[:80]


def _slug_disponible(db: Session, slug: str, *, excluir_id: str | None = None) -> str:
    candidato = slug
    n = 2
    while True:
        q = select(Organization).where(Organization.slug == candidato)
        if excluir_id:
            q = q.where(Organization.id != excluir_id)
        if not db.scalar(q.limit(1)):
            return candidato
        candidato = f"{slug}-{n}"[:80]
        n += 1


def organization_stats(db: Session, org_id: str) -> dict:
    usuarios = db.scalar(select(func.count()).select_from(User).where(User.organizacion_id == org_id)) or 0
    tickets = db.scalar(select(func.count()).select_from(Ticket).where(Ticket.organizacion_id == org_id)) or 0
    lineas = db.scalar(select(func.count()).select_from(LineaJSC).where(LineaJSC.organizacion_id == org_id)) or 0
    abiertos = (
        db.scalar(
            select(func.count()).select_from(Ticket).where(
                Ticket.organizacion_id == org_id,
                Ticket.estado != "Cerrado",
            )
        )
        or 0
    )
    return {
        "usuarios": usuarios,
        "tickets": tickets,
        "lineas": lineas,
        "tickets_abiertos": abiertos,
    }


def list_organizations_admin(db: Session) -> list[dict]:
    orgs = list_organizations(db)
    return [
        {
            "slug": o.slug,
            "nombre": o.nombre,
            "brand_color": o.brand_color,
            "logo_label": o.logo_label,
            "es_plataforma": o.slug == "imowi",
            **organization_stats(db, o.id),
        }
        for o in orgs
    ]


def create_organization(
    db: Session,
    *,
    nombre: str,
    slug: str | None = None,
    logo_label: str = "C",
    brand_color: str = "#2298A6",
) -> Organization:
    base_slug = slug or slugify_org_name(nombre)
    final_slug = _slug_disponible(db, base_slug)
    org = Organization(
        nombre=nombre,
        slug=final_slug,
        logo_label=(logo_label or "C")[:8],
        brand_color=brand_color or "#2298A6",
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def update_organization(
    db: Session,
    slug: str,
    *,
    nombre: str | None = None,
    logo_label: str | None = None,
    brand_color: str | None = None,
) -> Organization | None:
    org = get_org_by_slug(db, slug)
    if not org:
        return None
    if nombre is not None:
        org.nombre = nombre
    if logo_label is not None:
        org.logo_label = logo_label[:8]
    if brand_color is not None:
        org.brand_color = brand_color
    db.commit()
    db.refresh(org)
    return org


def delete_organization(db: Session, slug: str, *, actor: str = "admin") -> dict:
    """Elimina cooperativa y todos sus datos (cascada). No permite borrar imowi."""
    from app.estate.models import (
        Abonado,
        AuditEvent,
        CasoConversacion,
        ConversacionCanal,
        KnowledgeArticle,
        KnowledgeContribution,
        LineaJSC,
        MensajeCanal,
        NetworkElement,
        PilotEvent,
        PortalAbonadoLink,
        PortalOtpChallenge,
        Ticket,
        TicketEvent,
        TicketNotification,
        User,
        UserInvite,
    )

    org = get_org_by_slug(db, slug)
    if not org:
        raise ValueError("not_found")
    if org.slug == "imowi":
        raise ValueError("protected")

    oid = org.id
    org_nombre = org.nombre
    org_slug = org.slug
    counts = {
        "usuarios": db.scalar(select(func.count()).select_from(User).where(User.organizacion_id == oid)) or 0,
        "tickets": db.scalar(select(func.count()).select_from(Ticket).where(Ticket.organizacion_id == oid)) or 0,
        "abonados": db.scalar(select(func.count()).select_from(Abonado).where(Abonado.organizacion_id == oid)) or 0,
    }

    imowi = get_org_by_slug(db, "imowi")
    if imowi:
        from app.estate.audit import log_audit

        log_audit(
            db,
            org_id=imowi.id,
            actor=actor or "admin",
            accion="cooperativa_baja",
            recurso=org_slug,
            detalle=(
                f"Eliminada {org_nombre}: usuarios={counts['usuarios']} "
                f"tickets={counts['tickets']} abonados={counts['abonados']}"
            ),
        )

    # Hijos primero (orden por FKs)
    db.execute(delete(MensajeCanal).where(MensajeCanal.organizacion_id == oid))
    db.execute(delete(ConversacionCanal).where(ConversacionCanal.organizacion_id == oid))
    db.execute(delete(TicketNotification).where(TicketNotification.organizacion_id == oid))
    db.execute(delete(TicketEvent).where(TicketEvent.organizacion_id == oid))
    db.execute(delete(Ticket).where(Ticket.organizacion_id == oid))
    db.execute(delete(CasoConversacion).where(CasoConversacion.organizacion_id == oid))
    db.execute(delete(KnowledgeContribution).where(KnowledgeContribution.organizacion_id == oid))
    db.execute(delete(KnowledgeArticle).where(KnowledgeArticle.organizacion_id == oid))
    db.execute(delete(NetworkElement).where(NetworkElement.organizacion_id == oid))
    db.execute(delete(LineaJSC).where(LineaJSC.organizacion_id == oid))
    db.execute(delete(PortalOtpChallenge).where(PortalOtpChallenge.organizacion_id == oid))
    db.execute(delete(PortalAbonadoLink).where(PortalAbonadoLink.organizacion_id == oid))
    db.execute(delete(Abonado).where(Abonado.organizacion_id == oid))
    db.execute(delete(UserInvite).where(UserInvite.organizacion_id == oid))
    db.execute(delete(User).where(User.organizacion_id == oid))
    db.execute(delete(PilotEvent).where(PilotEvent.organizacion_id == oid))
    db.execute(delete(AuditEvent).where(AuditEvent.organizacion_id == oid))
    db.delete(org)
    db.commit()

    return {"slug": org_slug, "nombre": org_nombre, **counts}


_ROLES_VALIDOS = {
    "admin",
    "supervisor",
    "ejecutivo",
    "agente",
    "cliente",
    "ingeniero_noc",
    "admin_sistema",
    "admin_org",
    "operador",
    "cooperativa",
}


def user_is_active(user: User) -> bool:
    return (getattr(user, "activo", None) or "Sí").strip().lower() in ("sí", "si", "yes", "true", "1")


def create_user_for_org(
    db: Session,
    org_id: str,
    *,
    email: str,
    nombre: str,
    password: str = "",
    rol: str = "agente",
    telefono: str = "",
    linea_principal: str = "",
    must_change_password: bool | None = None,
) -> User:
    import secrets
    import string

    from app.rbac import normalizar_rol_consola

    email_norm = email.strip().lower()
    if not valid_email(email_norm):
        raise ValueError("Email inválido")
    plain = (password or "").strip()
    if not plain:
        alphabet = string.ascii_letters + string.digits
        plain = "Tmp" + "".join(secrets.choice(alphabet) for _ in range(10)) + "1a"
        if must_change_password is None:
            must_change_password = True
    if not valid_password(plain):
        from app.estate.security import password_policy_errors

        raise ValueError(
            "La clave no cumple la política: " + ", ".join(password_policy_errors(plain))
        )
    rol_raw = (rol or "agente").lower()
    if rol_raw not in _ROLES_VALIDOS:
        raise ValueError(f"Rol '{rol}' no permitido")
    org = db.get(Organization, org_id)
    rol_norm = normalizar_rol_consola(rol_raw, org.slug if org else None)
    if db.scalar(select(User).where(User.email == email_norm)):
        raise ValueError(f"El email {email} ya está registrado")
    force_change = must_change_password
    if force_change is None:
        force_change = True
    user = User(
        organizacion_id=org_id,
        email=email_norm,
        nombre=nombre.strip(),
        password=hash_password(plain),
        rol=rol_norm,
        telefono=telefono,
        linea_principal=linea_principal,
        must_change_password="Sí" if force_change else "No",
        activo="Sí",
        disponibilidad="disponible",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user_for_org(
    db: Session,
    org_id: str,
    user_id: str,
    *,
    nombre: str | None = None,
    rol: str | None = None,
    telefono: str | None = None,
    linea_principal: str | None = None,
    activo: bool | None = None,
    password: str | None = None,
    disponibilidad: str | None = None,
    allowed_roles: set[str] | frozenset[str] | None = None,
) -> User | None:
    from app.rbac import normalizar_rol_consola

    user = db.scalar(select(User).where(User.id == user_id, User.organizacion_id == org_id))
    if not user:
        return None
    if nombre is not None:
        user.nombre = nombre.strip()
    if telefono is not None:
        user.telefono = telefono
    if linea_principal is not None:
        user.linea_principal = linea_principal
    if password is not None:
        if not valid_password(password):
            from app.estate.security import password_policy_errors

            raise ValueError(
                "La clave no cumple la política: " + ", ".join(password_policy_errors(password))
            )
        user.password = hash_password(password)
        user.must_change_password = "No"
        user.token_version = int(getattr(user, "token_version", 0) or 0) + 1
    if activo is not None:
        user.activo = "Sí" if activo else "No"
        if not activo:
            user.token_version = int(getattr(user, "token_version", 0) or 0) + 1
    if disponibilidad is not None:
        user.disponibilidad = disponibilidad.strip().lower() or "disponible"
    if rol is not None:
        org = db.get(Organization, org_id)
        rol_norm = normalizar_rol_consola(rol, org.slug if org else None)
        if allowed_roles is not None and rol_norm not in allowed_roles:
            raise ValueError(f"No podés asignar el rol '{rol_norm}'")
        user.rol = rol_norm
    db.commit()
    db.refresh(user)
    return user


def get_user_by_id(db: Session, org_id: str, user_id: str) -> User | None:
    return db.scalar(select(User).where(User.id == user_id, User.organizacion_id == org_id))


def set_user_availability(db: Session, org_id: str, email: str, disponibilidad: str) -> User | None:
    user = get_user_by_email(db, org_id, email)
    if not user:
        # Alias sin dominio completo
        rows = db.scalars(select(User).where(User.organizacion_id == org_id)).all()
        value = email.strip().lower()
        user = next(
            (u for u in rows if u.email.lower() == value or u.email.lower().split("@", 1)[0] == value),
            None,
        )
    if not user:
        return None
    user.disponibilidad = (disponibilidad or "disponible").strip().lower()
    db.commit()
    db.refresh(user)
    return user


def user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "nombre": user.nombre,
        "rol": user.rol,
        "telefono": user.telefono or "",
        "linea_principal": user.linea_principal or "",
        "must_change_password": (user.must_change_password or "No") == "Sí",
        "activo": user_is_active(user),
        "disponibilidad": getattr(user, "disponibilidad", None) or "disponible",
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def get_user_by_email(db: Session, org_id: str, email: str) -> User | None:
    return db.scalar(
        select(User).where(User.organizacion_id == org_id, User.email == email)
    )


def get_user_by_login(db: Session, login: str) -> tuple[User, Organization] | None:
    """Busca usuario por email completo o alias local antes de @."""
    value = (login or "").strip().lower()
    if not value:
        return None
    rows = db.execute(
        select(User, Organization)
        .join(Organization, Organization.id == User.organizacion_id)
    ).all()
    for user, org in rows:
        email = (user.email or "").lower()
        alias = email.split("@", 1)[0]
        if value in (email, alias):
            return user, org
    return None


def list_kb(db: Session, org_id: str) -> list[KnowledgeArticle]:
    return list(
        db.scalars(
            select(KnowledgeArticle)
            .where(KnowledgeArticle.organizacion_id == org_id)
            .order_by(KnowledgeArticle.created_at.desc())
        ).all()
    )


def add_kb(db: Session, org_id: str, titulo: str, categoria: str, contenido: str) -> KnowledgeArticle:
    art = KnowledgeArticle(
        organizacion_id=org_id,
        titulo=titulo,
        categoria=categoria,
        contenido=contenido,
    )
    db.add(art)
    db.commit()
    db.refresh(art)
    return art


def get_kb(db: Session, org_id: str, articulo_id: str) -> KnowledgeArticle | None:
    return db.scalar(
        select(KnowledgeArticle).where(
            KnowledgeArticle.id == articulo_id,
            KnowledgeArticle.organizacion_id == org_id,
        )
    )


def delete_kb(db: Session, org_id: str, articulo_id: str) -> bool:
    art = get_kb(db, org_id, articulo_id)
    if not art:
        return False
    db.delete(art)
    db.commit()
    return True


def add_kb_contribution(
    db: Session,
    org_id: str,
    *,
    titulo: str,
    categoria: str,
    contenido: str,
    ticket_id: str = "",
    origen: str = "cierre",
    nivel_ticket: str = "",
    propuesto_por: str = "",
) -> KnowledgeContribution:
    contrib = KnowledgeContribution(
        organizacion_id=org_id,
        ticket_id=ticket_id or "",
        titulo=titulo.strip()[:200],
        categoria=(categoria or "General").strip()[:80],
        contenido=contenido.strip(),
        estado="pendiente",
        origen=origen or "cierre",
        nivel_ticket=nivel_ticket or "",
        propuesto_por=propuesto_por or "",
    )
    db.add(contrib)
    db.commit()
    db.refresh(contrib)
    return contrib


def get_kb_contribution(
    db: Session,
    org_id: str,
    contrib_id: str,
    *,
    admin_global: bool = False,
) -> KnowledgeContribution | None:
    q = select(KnowledgeContribution).where(KnowledgeContribution.id == contrib_id)
    if not admin_global:
        q = q.where(KnowledgeContribution.organizacion_id == org_id)
    return db.scalar(q)


def list_kb_contributions(
    db: Session,
    org_id: str,
    *,
    estado: str = "",
    ticket_id: str = "",
    admin_global: bool = False,
    limit: int = 100,
) -> list[KnowledgeContribution]:
    q = select(KnowledgeContribution).order_by(KnowledgeContribution.created_at.desc()).limit(limit)
    if not admin_global:
        q = q.where(KnowledgeContribution.organizacion_id == org_id)
    if estado:
        q = q.where(KnowledgeContribution.estado == estado)
    if ticket_id:
        q = q.where(KnowledgeContribution.ticket_id == ticket_id)
    return list(db.scalars(q).all())


def find_pending_kb_contribution_for_ticket(
    db: Session,
    org_id: str,
    ticket_id: str,
) -> KnowledgeContribution | None:
    if not ticket_id:
        return None
    return db.scalar(
        select(KnowledgeContribution)
        .where(
            KnowledgeContribution.organizacion_id == org_id,
            KnowledgeContribution.ticket_id == ticket_id,
            KnowledgeContribution.estado == "pendiente",
        )
        .order_by(KnowledgeContribution.created_at.desc())
        .limit(1)
    )


def approve_kb_contribution(
    db: Session,
    contrib: KnowledgeContribution,
    *,
    revisado_por: str,
    titulo: str | None = None,
    categoria: str | None = None,
    contenido: str | None = None,
    motivo_revision: str = "",
) -> tuple[KnowledgeContribution, KnowledgeArticle]:
    if titulo is not None and titulo.strip():
        contrib.titulo = titulo.strip()[:200]
    if categoria is not None and categoria.strip():
        contrib.categoria = categoria.strip()[:80]
    if contenido is not None and contenido.strip():
        contrib.contenido = contenido.strip()
    art = KnowledgeArticle(
        organizacion_id=contrib.organizacion_id,
        titulo=contrib.titulo,
        categoria=contrib.categoria or "General",
        contenido=contrib.contenido,
    )
    db.add(art)
    db.flush()
    contrib.estado = "aprobada"
    contrib.revisado_por = revisado_por or ""
    contrib.motivo_revision = (motivo_revision or "").strip()[:2000]
    contrib.articulo_id = art.id
    contrib.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(contrib)
    db.refresh(art)
    return contrib, art


def reject_kb_contribution(
    db: Session,
    contrib: KnowledgeContribution,
    *,
    revisado_por: str,
    motivo_revision: str = "",
) -> KnowledgeContribution:
    contrib.estado = "rechazada"
    contrib.revisado_por = revisado_por or ""
    contrib.motivo_revision = (motivo_revision or "").strip()[:2000]
    contrib.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(contrib)
    return contrib


def list_telemetry(db: Session, org_id: str) -> list[NetworkElement]:
    expire_stale_anomalies(db, org_id)
    return list(
        db.scalars(
            select(NetworkElement)
            .where(NetworkElement.organizacion_id == org_id)
            .order_by(NetworkElement.elemento_red)
        ).all()
    )


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def expire_stale_anomalies(db: Session, org_id: str) -> int:
    """La base operativa de anomalías es temporal, no parte de la KB documental."""
    if ANOMALY_TTL_MINUTES <= 0:
        return 0
    cutoff = datetime.now(UTC) - timedelta(minutes=ANOMALY_TTL_MINUTES)
    rows = list(
        db.scalars(
            select(NetworkElement).where(
                NetworkElement.organizacion_id == org_id,
                NetworkElement.estado_actual != "Normal",
            )
        ).all()
    )
    expired = 0
    for el in rows:
        ts = _as_utc(el.ultima_actualizacion)
        if ts and ts < cutoff:
            el.estado_actual = "Normal"
            el.valor_actual = "OK"
            el.ultima_actualizacion = datetime.now(UTC)
            expired += 1
    if expired:
        db.commit()
    return expired


def simulate_failure(db: Session, org_id: str, elemento_red: str) -> NetworkElement | None:
    el = db.scalar(
        select(NetworkElement).where(
            NetworkElement.organizacion_id == org_id,
            NetworkElement.elemento_red == elemento_red,
        )
    )
    if not el:
        return None
    el.estado_actual = "Anomalía Predictiva"
    el.valor_actual = "ALERTA"
    el.ultima_actualizacion = datetime.now(UTC)
    db.commit()
    db.refresh(el)
    return el


def _ticket_seq_num(tid: str) -> int | None:
    """Número secuencial de IDs tipo PREFIJO-NNNN (IBOT / legacy JSC)."""
    if not tid or "-" not in tid:
        return None
    prefix, _, rest = tid.partition("-")
    # Contar prefijo actual + legacy JSC para no reiniciar la secuencia.
    known = {TICKET_ID_PREFIX.upper(), "JSC", "IBOT"}
    if prefix.upper() not in known:
        return None
    try:
        return int(rest)
    except ValueError:
        return None


def _next_ticket_id(db: Session, org_id: str) -> str:
    # Ticket.id es primary key global: la numeración no puede ser por organización.
    rows = db.scalars(select(Ticket.id)).all()
    nums = [n for tid in rows if (n := _ticket_seq_num(tid)) is not None]
    n = max(nums) + 1 if nums else 1001
    return f"{TICKET_ID_PREFIX}-{n}"


def create_ticket(
    db: Session,
    org_id: str,
    *,
    linea: str,
    dispositivo: str,
    descripcion_falla: str,
    origen: str,
    categoria: str = "General",
    intent_ejecutado: str = "",
    creado_por: str = "",
    nivel: str = "N1",
    destino: str = "cooperativa",
    proveedor: str = "",
    motivo_escalamiento: str = "",
    evidencia: str = "",
    acciones_n1_realizadas: str = "",
    estado_sla: str = "Pendiente",
    ticket_externo_id: str = "",
    regla_clasificacion: str = "",
) -> Ticket:
    t = Ticket(
        id=_next_ticket_id(db, org_id),
        organizacion_id=org_id,
        linea=linea,
        dispositivo=dispositivo,
        descripcion_falla=descripcion_falla,
        origen=origen,
        categoria=categoria,
        intent_ejecutado=intent_ejecutado,
        creado_por=creado_por,
        nivel=nivel,
        destino=destino,
        proveedor=proveedor,
        motivo_escalamiento=motivo_escalamiento,
        evidencia=evidencia,
        acciones_n1_realizadas=acciones_n1_realizadas,
        estado_sla=estado_sla,
        ticket_externo_id=ticket_externo_id,
        regla_clasificacion=regla_clasificacion,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    apply_sla_to_ticket(t)
    db.commit()
    db.refresh(t)
    add_ticket_event(
        db,
        org_id,
        t.id,
        tipo="creacion",
        titulo=f"Ticket {t.nivel} creado",
        detalle=_evento_creacion_detalle(t),
        nivel=t.nivel,
        estado=t.estado,
        actor=creado_por or "sistema",
    )
    add_ticket_notification(
        db,
        org_id,
        t.id,
        destinatario=creado_por,
        titulo=f"Ticket {t.id} registrado",
        mensaje=(
            f"El reclamo quedó registrado como ticket {t.nivel}. "
            f"Estado actual: {t.estado}. Destino: {t.destino}."
        ),
    )
    return t


def list_tickets(db: Session, org_id: str) -> list[Ticket]:
    items = list(
        db.scalars(
            select(Ticket)
            .where(Ticket.organizacion_id == org_id)
            .order_by(Ticket.created_at.desc())
        ).all()
    )
    refresh_tickets_sla(db, items)
    return items


def list_tickets_all(db: Session) -> list[Ticket]:
    items = list(
        db.scalars(select(Ticket).order_by(Ticket.created_at.desc())).all()
    )
    refresh_tickets_sla(db, items)
    return items


def refresh_tickets_sla(db: Session, tickets: list[Ticket], *, persist: bool = True) -> None:
    dirty = False
    newly_breached: list[Ticket] = []
    for t in tickets:
        if t.estado == "Cerrado":
            continue
        was_breached = bool(t.sla_breached_at)
        prev = (t.sla_due_at, t.sla_breached_at, t.estado_sla, t.sla_policy)
        apply_sla_to_ticket(t)
        if prev != (t.sla_due_at, t.sla_breached_at, t.estado_sla, t.sla_policy):
            dirty = True
        if not was_breached and t.sla_breached_at:
            newly_breached.append(t)
    if dirty and persist:
        db.commit()
    for t in newly_breached:
        try:
            from app.services.sla_notify import notify_sla_breach

            notify_sla_breach(db, t, was_breached=False)
        except Exception:
            logger = __import__("logging").getLogger("operations_hub")
            logger.warning("Fallo notify SLA breach %s", t.id, exc_info=True)


def ensure_ticket_sla(db: Session, t: Ticket) -> dict:
    if t.estado != "Cerrado":
        was_breached = bool(t.sla_breached_at)
        prev = (t.sla_due_at, t.sla_breached_at, t.estado_sla, t.sla_policy)
        apply_sla_to_ticket(t)
        if prev != (t.sla_due_at, t.sla_breached_at, t.estado_sla, t.sla_policy):
            db.commit()
            db.refresh(t)
        if not was_breached and t.sla_breached_at:
            try:
                from app.services.sla_notify import notify_sla_breach

                notify_sla_breach(db, t, was_breached=False)
            except Exception:
                pass
    return compute_sla(t)


def get_ticket(
    db: Session,
    org_id: str,
    ticket_id: str,
    *,
    admin_global: bool = False,
) -> Ticket | None:
    stmt = select(Ticket).where(Ticket.id == ticket_id)
    if not admin_global:
        stmt = stmt.where(Ticket.organizacion_id == org_id)
    return db.scalar(stmt)


def update_ticket(
    db: Session,
    org_id: str,
    ticket_id: str,
    *,
    estado: str | None = None,
    resolucion_tecnica: str | None = None,
    descripcion_falla: str | None = None,
    nivel: str | None = None,
    destino: str | None = None,
    proveedor: str | None = None,
    motivo_escalamiento: str | None = None,
    estado_sla: str | None = None,
    ticket_externo_id: str | None = None,
    asignado_a: str | None = None,
    actor: str = "operador",
    admin_global: bool = False,
) -> Ticket | None:
    t = get_ticket(db, org_id, ticket_id, admin_global=admin_global)
    if not t:
        return None
    event_org_id = t.organizacion_id
    era_abierto = t.estado != "Cerrado"
    cambios = []
    if estado:
        t.estado = estado
        cambios.append(f"estado={estado}")
    if resolucion_tecnica is not None:
        t.resolucion_tecnica = resolucion_tecnica
        if resolucion_tecnica:
            cambios.append("resolución técnica actualizada")
    if descripcion_falla:
        t.descripcion_falla = descripcion_falla
        cambios.append("descripción actualizada")
    if nivel:
        t.nivel = nivel
        cambios.append(f"nivel={nivel}")
    if destino:
        t.destino = destino
        cambios.append(f"destino={destino}")
    if proveedor is not None:
        t.proveedor = proveedor
        if proveedor:
            cambios.append(f"proveedor={proveedor}")
    if motivo_escalamiento is not None:
        t.motivo_escalamiento = motivo_escalamiento
        if motivo_escalamiento:
            cambios.append("motivo de escalamiento actualizado")
    if estado_sla:
        t.estado_sla = estado_sla
        cambios.append(f"SLA={estado_sla}")
    if ticket_externo_id is not None:
        t.ticket_externo_id = ticket_externo_id
        if ticket_externo_id:
            cambios.append(f"referencia externa={ticket_externo_id}")
    if asignado_a is not None:
        prev = getattr(t, "asignado_a", "") or ""
        t.asignado_a = asignado_a.strip()
        if t.asignado_a != prev:
            cambios.append(f"asignado_a={t.asignado_a or '(sin asignar)'}")
    t.updated_at = datetime.now(UTC)
    if t.estado != "Cerrado":
        apply_sla_to_ticket(t)
    db.commit()
    db.refresh(t)
    if era_abierto and t.estado == "Cerrado":
        from app.estate.learning_loop import procesar_cierre_ticket

        org = get_org_by_id(db, event_org_id)
        procesar_cierre_ticket(
            db,
            event_org_id,
            t,
            org_name=org.nombre if org else "",
        )
        mark_ticket_notifications_read(db, event_org_id, ticket_id)
    if cambios:
        detalle = "; ".join(cambios)
        add_ticket_event(
            db,
            event_org_id,
            ticket_id,
            tipo="actualizacion" if asignado_a is None else "reasignacion",
            titulo="Ticket reasignado" if asignado_a is not None else "Ticket actualizado",
            detalle=detalle,
            nivel=t.nivel,
            estado=t.estado,
            actor=actor,
        )
        if asignado_a:
            add_ticket_notification(
                db,
                event_org_id,
                ticket_id,
                destinatario=asignado_a,
                titulo="Ticket asignado",
                mensaje=f"Se te asignó el ticket {ticket_id}",
            )
        elif t.creado_por:
            add_ticket_notification(
                db,
                event_org_id,
                ticket_id,
                destinatario=t.creado_por,
                titulo=f"Novedad en ticket {t.id}",
                mensaje=f"El ticket {t.id} fue actualizado: {detalle}. Nivel actual: {t.nivel}.",
            )
    return t


def _evento_creacion_detalle(t: Ticket) -> str:
    partes = [
        f"Origen: {t.origen}",
        f"Destino: {t.destino}",
        f"Categoría: {t.categoria}",
    ]
    if t.proveedor:
        partes.append(f"Proveedor sugerido: {t.proveedor}")
    if t.regla_clasificacion:
        partes.append(f"Regla: {t.regla_clasificacion}")
    return " | ".join(partes)


def add_ticket_event(
    db: Session,
    org_id: str,
    ticket_id: str,
    *,
    tipo: str,
    titulo: str,
    detalle: str = "",
    nivel: str = "",
    estado: str = "",
    actor: str = "sistema",
    visible_cliente: str = "Sí",
) -> TicketEvent:
    ev = TicketEvent(
        organizacion_id=org_id,
        ticket_id=ticket_id,
        tipo=tipo,
        titulo=titulo,
        detalle=detalle,
        nivel=nivel,
        estado=estado,
        actor=actor,
        visible_cliente=visible_cliente,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def list_ticket_events(
    db: Session,
    org_id: str,
    ticket_id: str,
    *,
    solo_visibles: bool = False,
    admin_global: bool = False,
) -> list[TicketEvent]:
    stmt = (
        select(TicketEvent)
        .where(TicketEvent.ticket_id == ticket_id)
        .order_by(TicketEvent.created_at.asc())
    )
    if not admin_global:
        stmt = stmt.where(TicketEvent.organizacion_id == org_id)
    if solo_visibles:
        stmt = stmt.where(TicketEvent.visible_cliente == "Sí")
    return list(db.scalars(stmt).all())


def add_ticket_notification(
    db: Session,
    org_id: str,
    ticket_id: str | None,
    *,
    destinatario: str,
    titulo: str,
    mensaje: str,
    canal: str = "consola",
) -> TicketNotification:
    tid = (ticket_id or "").strip() or None
    n = TicketNotification(
        organizacion_id=org_id,
        ticket_id=tid,
        destinatario=destinatario,
        canal=canal,
        titulo=titulo,
        mensaje=mensaje,
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def list_supervisores_org(db: Session, org_id: str) -> list[User]:
    """Usuarios activos con rol supervisor (o admin) en la org."""
    from app.rbac import normalizar_rol_consola

    users = list_users_for_org(db, org_id)
    out: list[User] = []
    for u in users:
        if (u.activo or "Sí") == "No":
            continue
        rol = normalizar_rol_consola(u.rol or "")
        if rol in ("supervisor", "admin") and (u.email or "").strip():
            out.append(u)
    return out


def list_admins_plataforma(db: Session) -> list[User]:
    """Admins de la org plataforma (imowi) — ven alertas de todas las cooperativas."""
    from app.rbac import normalizar_rol_consola

    org = get_org_by_slug(db, "imowi")
    if not org:
        return []
    out: list[User] = []
    for u in list_users_for_org(db, org.id):
        if (u.activo or "Sí") == "No":
            continue
        if normalizar_rol_consola(u.rol or "") == "admin" and (u.email or "").strip():
            out.append(u)
    return out


def destinatarios_alerta_csat(db: Session, org_id: str) -> list[str]:
    """Emails a notificar por CSAT bajo: supervisores/admins de la org + admins plataforma."""
    emails: set[str] = set()
    for u in list_supervisores_org(db, org_id):
        emails.add((u.email or "").strip().lower())
    for u in list_admins_plataforma(db):
        emails.add((u.email or "").strip().lower())
    return sorted(e for e in emails if e and "@" in e)


def list_ticket_notifications(
    db: Session,
    org_id: str,
    *,
    destinatario: str = "",
    solo_no_leidas: bool = False,
    admin_global: bool = False,
    incluir_csat_org: bool = False,
) -> list[TicketNotification]:
    """Lista notificaciones.

    Si incluir_csat_org=True y hay destinatario, también incluye alertas de equipo
    (csat_bajo, inbox_handoff, sla_breach) de la org aunque el destinatario sea otro.
    """
    from sqlalchemy import or_

    stmt = select(TicketNotification).order_by(TicketNotification.created_at.desc())
    if not admin_global:
        stmt = stmt.where(TicketNotification.organizacion_id == org_id)
    if destinatario:
        dest = destinatario.strip()
        if incluir_csat_org:
            stmt = stmt.where(
                or_(
                    TicketNotification.destinatario == dest,
                    TicketNotification.canal.in_(
                        ("csat_bajo", "inbox_handoff", "sla_breach")
                    ),
                )
            )
        else:
            stmt = stmt.where(TicketNotification.destinatario == dest)
    if solo_no_leidas:
        stmt = stmt.where(TicketNotification.leida == "No")
    return list(db.scalars(stmt).all())


def mark_notification_read(
    db: Session,
    org_id: str,
    notification_id: str,
    *,
    admin_global: bool = False,
) -> TicketNotification | None:
    stmt = select(TicketNotification).where(TicketNotification.id == notification_id)
    if not admin_global:
        stmt = stmt.where(TicketNotification.organizacion_id == org_id)
    n = db.scalar(stmt)
    if not n:
        return None
    n.leida = "Sí"
    db.commit()
    db.refresh(n)
    return n


def mark_ticket_notifications_read(
    db: Session,
    org_id: str,
    ticket_id: str,
) -> int:
    """Marca como leídas todas las notificaciones abiertas de un ticket."""
    items = list(
        db.scalars(
            select(TicketNotification).where(
                TicketNotification.organizacion_id == org_id,
                TicketNotification.ticket_id == ticket_id,
                TicketNotification.leida == "No",
            )
        ).all()
    )
    if not items:
        return 0
    for n in items:
        n.leida = "Sí"
    db.commit()
    return len(items)


def dismiss_notifications_for_closed_tickets(
    db: Session,
    org_id: str,
    *,
    destinatario: str = "",
    admin_global: bool = False,
) -> int:
    """Limpia pendientes huérfanos: ticket ya cerrado pero notificación no leída."""
    stmt = select(TicketNotification).where(TicketNotification.leida == "No")
    if not admin_global:
        stmt = stmt.where(TicketNotification.organizacion_id == org_id)
    if destinatario:
        stmt = stmt.where(TicketNotification.destinatario == destinatario)
    unread = list(db.scalars(stmt).all())
    if not unread:
        return 0

    ticket_ids = {n.ticket_id for n in unread if n.ticket_id}
    if not ticket_ids:
        return 0

    closed_q = select(Ticket.id).where(
        Ticket.id.in_(ticket_ids),
        Ticket.estado == "Cerrado",
    )
    if not admin_global:
        closed_q = closed_q.where(Ticket.organizacion_id == org_id)
    closed_ids = set(db.scalars(closed_q).all())
    if not closed_ids:
        return 0

    n_done = 0
    for n in unread:
        # CSAT bajo se revisa después del cierre: no auto-descartar
        if (n.canal or "").strip().lower() == "csat_bajo":
            continue
        if n.ticket_id in closed_ids:
            n.leida = "Sí"
            n_done += 1
    if n_done:
        db.commit()
    return n_done


def agent_performance(db: Session, org_id: str, *, admin_global: bool = False) -> dict:
    """Performance operativa de agentes. Con admin_global agrega todas las orgs (imowi)."""
    from app.rbac import normalizar_rol_consola

    if admin_global:
        users = [
            u
            for u in db.scalars(select(User)).all()
            if normalizar_rol_consola(u.rol) == "agente" and (u.activo or "Sí") != "No"
        ]
        tickets = list_tickets_all(db)
        org_map = {o.id: o.nombre for o in list_organizations(db)}
    else:
        users = [
            u
            for u in list_users_for_org(db, org_id)
            if normalizar_rol_consola(u.rol) == "agente"
        ]
        tickets = list_tickets(db, org_id)
        org_map = {}

    abiertos = [t for t in tickets if t.estado != "Cerrado"]

    agentes = []
    for u in users:
        email = (u.email or "").lower()
        alias = email.split("@", 1)[0]
        keys = {email, alias}
        if u.nombre:
            keys.add(u.nombre.lower())
        asignados = [
            t
            for t in abiertos
            if (getattr(t, "asignado_a", "") or "").lower() in keys
        ]
        creados_abiertos = [
            t
            for t in abiertos
            if (t.creado_por or "").lower() in keys and not (getattr(t, "asignado_a", "") or "")
        ]
        cerrados = [
            t
            for t in tickets
            if t.estado == "Cerrado"
            and (
                (getattr(t, "asignado_a", "") or "").lower() in keys
                or (t.creado_por or "").lower() in keys
            )
        ]
        carga = len(asignados) + len(creados_abiertos)
        row = {
            **user_to_dict(u),
            "tickets_abiertos": carga,
            "tickets_asignados": len(asignados),
            "tickets_cerrados": len(cerrados),
        }
        if admin_global:
            row["organizacion"] = org_map.get(u.organizacion_id, "")
        agentes.append(row)
    agentes.sort(key=lambda a: (-a["tickets_abiertos"], a["nombre"]))
    return {
        "agentes": agentes,
        "total_agentes": len(agentes),
        "tickets_abiertos": len(abiertos),
        "alcance": "global" if admin_global else "organizacion",
    }

def ticket_stats(
    db: Session,
    org_id: str,
    *,
    admin_global: bool = False,
    desde: datetime | None = None,
    hasta: datetime | None = None,
) -> dict:
    all_tickets = list_tickets_all(db) if admin_global else list_tickets(db, org_id)
    # Series/distribuciones: tickets creados en el rango (actividad del período)
    tickets = [t for t in all_tickets if _ticket_en_rango(t, desde, hasta)]
    now = datetime.now(UTC)
    # Backlog / top riesgo: snapshot de abiertos actuales (alineado con ops), no solo creados en rango
    open_now = [t for t in all_tickets if t.estado != "Cerrado"]

    total = len(tickets)
    abiertos = sum(1 for t in tickets if t.estado != "Cerrado")
    cerrados = sum(1 for t in tickets if t.estado == "Cerrado")
    n2 = sum(1 for t in tickets if t.nivel == "N2")
    n1 = sum(1 for t in tickets if t.nivel == "N1")

    antiguedades_horas = [
        _horas_entre(_as_aware(t.created_at), _as_aware(t.updated_at) if t.estado == "Cerrado" else now)
        for t in tickets
        if t.created_at
    ]
    promedio_horas = round(sum(antiguedades_horas) / len(antiguedades_horas), 1) if antiguedades_horas else 0

    daily = _serie_diaria(tickets, desde, hasta)
    monthly = _serie_mensual(tickets)

    por_categoria = _conteo(tickets, lambda t: t.categoria or "General")
    por_estado = _conteo(tickets, lambda t: t.estado or "Sin estado")
    por_nivel = _conteo(tickets, lambda t: t.nivel or "N1")
    por_origen = _conteo(tickets, lambda t: t.origen or "Reporte Cliente")
    por_destino = _conteo(tickets, lambda t: t.destino or "cooperativa")
    por_proveedor = _conteo([t for t in tickets if t.proveedor], lambda t: t.proveedor)

    promedio_por_categoria = []
    for categoria, grupo in _agrupar(tickets, lambda t: t.categoria or "General").items():
        horas = [
            _horas_entre(_as_aware(t.created_at), _as_aware(t.updated_at) if t.estado == "Cerrado" else now)
            for t in grupo
            if t.created_at
        ]
        promedio_por_categoria.append({
            "label": categoria,
            "count": len(grupo),
            "avg_hours": round(sum(horas) / len(horas), 1) if horas else 0,
        })
    promedio_por_categoria.sort(key=lambda x: (-x["count"], x["label"]))

    por_cooperativa: list[dict] = []
    if admin_global:
        org_map = {o.id: o.nombre for o in list_organizations(db)}
        por_cooperativa = _conteo(tickets, lambda t: org_map.get(t.organizacion_id, "Sin org"))
        coop_stats = []
        for coop_label, grupo in _agrupar(tickets, lambda t: org_map.get(t.organizacion_id, "Sin org")).items():
            cerrados_coop = sum(1 for t in grupo if t.estado == "Cerrado")
            n2_coop = sum(1 for t in grupo if t.nivel == "N2")
            horas = [
                _horas_entre(_as_aware(t.created_at), _as_aware(t.updated_at) if t.estado == "Cerrado" else now)
                for t in grupo
                if t.created_at
            ]
            coop_stats.append({
                "label": coop_label,
                "count": len(grupo),
                "abiertos": sum(1 for t in grupo if t.estado != "Cerrado"),
                "n2": n2_coop,
                "tasa_cierre": round((cerrados_coop / len(grupo)) * 100, 1) if grupo else 0,
                "promedio_horas": round(sum(horas) / len(horas), 1) if horas else 0,
            })
        coop_stats.sort(key=lambda x: (-x["count"], x["label"]))
    else:
        coop_stats = []

    top_lineas = _conteo([t for t in tickets if t.linea], lambda t: t.linea)[:8]
    from app.estate.ticket_intelligence import calcular_prioridad

    backlog_items = []
    for t in open_now:
        intel = calcular_prioridad(t, pool=open_now)
        sla = intel.get("sla") or {}
        backlog_items.append({
            "id": t.id,
            "linea": t.linea,
            "nivel": t.nivel,
            "estado": t.estado,
            "categoria": t.categoria,
            "estado_sla": sla.get("estado_sla") or getattr(t, "estado_sla", "Pendiente"),
            "horas_abierto": intel["horas_abierto"],
            "priority_score": intel["priority_score"],
            "risk_level": intel["risk_level"],
            "next_best_action": intel["next_best_action"],
        })
    backlog = sorted(backlog_items, key=lambda x: (-x["priority_score"], -x["horas_abierto"]))[:8]

    return {
        "resumen": {
            "total": total,
            "abiertos": abiertos,
            "cerrados": cerrados,
            "n1": n1,
            "n2": n2,
            "promedio_horas": promedio_horas,
            "tasa_cierre": round((cerrados / total) * 100, 1) if total else 0,
            "porcentaje_n2": round((n2 / total) * 100, 1) if total else 0,
            "abiertos_ahora": len(open_now),
        },
        "series": {
            "diaria": daily,
            "mensual": monthly,
        },
        "distribuciones": {
            "categoria": por_categoria,
            "estado": por_estado,
            "nivel": por_nivel,
            "origen": por_origen,
            "destino": por_destino,
            "proveedor": por_proveedor,
            "cooperativa": por_cooperativa,
            "lineas_recurrentes": top_lineas,
        },
        "promedios": {
            "por_categoria": promedio_por_categoria,
            "por_cooperativa": coop_stats,
        },
        "backlog": backlog,
    }


def _ticket_en_rango(t: Ticket, desde: datetime | None, hasta: datetime | None) -> bool:
    created = _as_aware(t.created_at)
    if desde and created < desde:
        return False
    if hasta and created > hasta:
        return False
    return True


def _as_aware(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.now(UTC)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _horas_entre(a: datetime, b: datetime) -> float:
    return max((b - a).total_seconds() / 3600, 0)


def _conteo(tickets: list[Ticket], key_fn) -> list[dict]:
    counts: dict[str, int] = {}
    for t in tickets:
        key = str(key_fn(t) or "Sin dato")
        counts[key] = counts.get(key, 0) + 1
    return [
        {"label": k, "count": v}
        for k, v in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _agrupar(tickets: list[Ticket], key_fn) -> dict[str, list[Ticket]]:
    grupos: dict[str, list[Ticket]] = {}
    for t in tickets:
        key = str(key_fn(t) or "Sin dato")
        grupos.setdefault(key, []).append(t)
    return grupos


def _serie_diaria(
    tickets: list[Ticket],
    desde: datetime | None,
    hasta: datetime | None,
) -> list[dict]:
    end = (hasta or datetime.now(UTC)).date()
    start = (desde.date() if desde else end - timedelta(days=29))
    counts: dict[str, int] = {}
    for t in tickets:
        d = _as_aware(t.created_at).date()
        if start <= d <= end:
            k = d.isoformat()
            counts[k] = counts.get(k, 0) + 1
    days = (end - start).days
    return [
        {"label": (start + timedelta(days=i)).isoformat(), "count": counts.get((start + timedelta(days=i)).isoformat(), 0)}
        for i in range(max(days, 0) + 1)
    ]


def _serie_mensual(tickets: list[Ticket]) -> list[dict]:
    counts: dict[str, int] = {}
    for t in tickets:
        d = _as_aware(t.created_at)
        k = f"{d.year}-{d.month:02d}"
        counts[k] = counts.get(k, 0) + 1
    return [
        {"label": k, "count": v}
        for k, v in sorted(counts.items())
    ][-12:]


def search_kb(db: Session, org_id: str, query: str, limit: int = 5) -> list[KnowledgeArticle]:
    q = query.lower()
    arts = list_kb(db, org_id)
    scored = []
    for a in arts:
        blob = f"{a.titulo} {a.categoria} {a.contenido}".lower()
        score = sum(1 for w in q.split() if len(w) > 3 and w in blob)
        if score:
            scored.append((score, a))
    scored.sort(key=lambda x: -x[0])
    return [a for _, a in scored[:limit]]


def get_linea_by_msisdn(
    db: Session, org_id: str, msisdn: str, *, admin_global: bool = False
) -> LineaJSC | None:
    q = select(LineaJSC).where(LineaJSC.msisdn == msisdn)
    if not admin_global:
        q = q.where(LineaJSC.organizacion_id == org_id)
    return db.scalar(q.limit(1))


def list_lineas(
    db: Session, org_id: str, *, limit: int = 50, admin_global: bool = False
) -> list[LineaJSC]:
    q = select(LineaJSC)
    if not admin_global:
        q = q.where(LineaJSC.organizacion_id == org_id)
    return list(db.scalars(q.order_by(LineaJSC.msisdn).limit(limit)).all())


def search_lineas(
    db: Session, org_id: str, query: str, *, limit: int = 10, admin_global: bool = False
) -> list[LineaJSC]:
    q = (query or "").strip()
    if not q:
        return list_lineas(db, org_id, limit=limit, admin_global=admin_global)
    digits = re.sub(r"\D", "", q)
    stmt = select(LineaJSC)
    if not admin_global:
        stmt = stmt.where(LineaJSC.organizacion_id == org_id)
    if digits:
        stmt = stmt.where(LineaJSC.msisdn.contains(digits))
    else:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            (LineaJSC.abonado.ilike(like)) | (LineaJSC.plan.ilike(like))
        )
    return list(db.scalars(stmt.limit(limit)).all())


def telemetry_anomalies(db: Session, org_id: str) -> list[NetworkElement]:
    expire_stale_anomalies(db, org_id)
    return [
        e
        for e in list_telemetry(db, org_id)
        if e.estado_actual != "Normal"
    ]


def _ticket_resumen(t: Ticket) -> dict:
    return {
        "id": t.id,
        "linea": t.linea,
        "estado": t.estado,
        "categoria": t.categoria,
        "nivel": t.nivel,
        "descripcion_falla": (t.descripcion_falla or "")[:120],
        "created_at": t.created_at.isoformat() if t.created_at else "",
    }


def buscar_tickets_similares(
    db: Session,
    org_id: str,
    linea: str,
    sintoma: str = "",
    *,
    limit: int = 5,
) -> list[dict]:
    if not linea:
        return []
    tickets = list_tickets(db, org_id)
    linea_digits = re.sub(r"\D", "", linea)
    tokens = [w.lower() for w in re.split(r"\W+", sintoma or "") if len(w) > 3][:6]
    scored: list[tuple[int, Ticket]] = []
    for t in tickets:
        if linea_digits and linea_digits not in re.sub(r"\D", "", t.linea or ""):
            continue
        score = 10
        blob = f"{t.descripcion_falla} {t.categoria}".lower()
        score += sum(2 for tok in tokens if tok in blob)
        if t.estado != "Cerrado":
            score += 5
        scored.append((score, t))
    scored.sort(key=lambda x: -x[0])
    return [_ticket_resumen(t) for _, t in scored[:limit]]


def ticket_abierto_por_linea_categoria(
    db: Session,
    org_id: str,
    linea: str,
    categoria: str,
) -> Ticket | None:
    if not linea:
        return None
    linea_digits = re.sub(r"\D", "", linea)
    for t in list_tickets(db, org_id):
        if t.estado == "Cerrado":
            continue
        if linea_digits in re.sub(r"\D", "", t.linea or ""):
            if not categoria or t.categoria == categoria or categoria == "General":
                return t
    return None


def get_caso_abierto_por_linea(db: Session, org_id: str, linea: str) -> dict | None:
    if not linea:
        return None
    linea_digits = re.sub(r"\D", "", linea)
    rows = list(
        db.scalars(
            select(CasoConversacion)
            .where(CasoConversacion.organizacion_id == org_id)
            .order_by(CasoConversacion.updated_at.desc())
        ).all()
    )
    for row in rows:
        if row.estado in ESTADOS_CASO_CERRADO:
            continue
        row_linea = row.linea_msisdn or ""
        if not row_linea:
            try:
                datos = json.loads(row.datos_triaje_json or "{}")
                row_linea = datos.get("linea", "")
            except json.JSONDecodeError:
                row_linea = ""
        if linea_digits and linea_digits in re.sub(r"\D", "", row_linea):
            return _caso_to_dict(row)
    return None


ESTADOS_CASO_CERRADO = {"cerrado_resuelto"}


def _caso_to_dict(row: CasoConversacion) -> dict:
    try:
        datos = json.loads(row.datos_triaje_json or "{}")
    except json.JSONDecodeError:
        datos = {}
    try:
        clasif = json.loads(row.clasificacion_json or "{}")
    except json.JSONDecodeError:
        clasif = {}
    return {
        "id": row.id,
        "session_id": row.session_id,
        "linea_msisdn": row.linea_msisdn or datos.get("linea", ""),
        "usuario": row.usuario,
        "estado": row.estado,
        "intencion_pendiente": row.intencion_pendiente or "",
        "datos_triaje": datos,
        "clasificacion": clasif,
        "paso_kb_idx": int(row.paso_kb_idx or "0"),
        "kb_agotada": row.kb_agotada == "Sí",
        "ticket_id": row.ticket_id,
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


def get_caso_conversacion(db: Session, org_id: str, session_id: str) -> dict | None:
    if not session_id:
        return None
    row = db.scalar(
        select(CasoConversacion).where(
            CasoConversacion.organizacion_id == org_id,
            CasoConversacion.session_id == session_id,
        )
    )
    return _caso_to_dict(row) if row else None


def upsert_caso_conversacion(
    db: Session,
    org_id: str,
    session_id: str,
    *,
    usuario: str = "",
    estado: str,
    datos_triaje: dict,
    clasificacion: dict,
    paso_kb_idx: int = 0,
    kb_agotada: bool = False,
    ticket_id: str = "",
    linea_msisdn: str = "",
    intencion_pendiente: str = "",
    caso_id: str | None = None,
    forzar_nuevo: bool = False,
) -> dict:
    row = None
    if caso_id and not forzar_nuevo:
        row = db.scalar(
            select(CasoConversacion).where(
                CasoConversacion.id == caso_id,
                CasoConversacion.organizacion_id == org_id,
            )
        )
    linea = linea_msisdn or datos_triaje.get("linea") or ""
    if not row and linea and not forzar_nuevo:
        prev = get_caso_abierto_por_linea(db, org_id, linea)
        if prev:
            row = db.scalar(
                select(CasoConversacion).where(CasoConversacion.id == prev["id"])
            )
    if not row and not forzar_nuevo:
        row = db.scalar(
            select(CasoConversacion).where(
                CasoConversacion.organizacion_id == org_id,
                CasoConversacion.session_id == session_id,
            )
        )
    if not row:
        row = CasoConversacion(
            organizacion_id=org_id,
            session_id=session_id,
            usuario=usuario,
        )
        db.add(row)
    else:
        # Conservar claves auxiliares (ej. historial_mensajes anti-injection) si el motor no las trae
        try:
            prev_datos = json.loads(row.datos_triaje_json or "{}")
        except json.JSONDecodeError:
            prev_datos = {}
        if isinstance(prev_datos, dict):
            for key in ("historial_mensajes",):
                if key in prev_datos and key not in (datos_triaje or {}):
                    datos_triaje = {**(datos_triaje or {}), key: prev_datos[key]}
    row.session_id = session_id
    row.usuario = usuario or row.usuario
    row.estado = estado
    row.linea_msisdn = linea or row.linea_msisdn
    row.intencion_pendiente = intencion_pendiente
    row.datos_triaje_json = json.dumps(datos_triaje, ensure_ascii=False)
    row.clasificacion_json = json.dumps(clasificacion, ensure_ascii=False)
    row.paso_kb_idx = str(paso_kb_idx)
    row.kb_agotada = "Sí" if kb_agotada else "No"
    row.ticket_id = ticket_id or row.ticket_id
    row.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return _caso_to_dict(row)


def merge_caso_historial_mensajes(
    db: Session,
    org_id: str,
    session_id: str,
    nuevos: list[dict],
    *,
    max_msgs: int = 40,
) -> None:
    """Persiste turnos de consola en datos_triaje.historial_mensajes (anti prompt-injection)."""
    if not session_id or not nuevos:
        return
    from app.services.prompt_safety import sanitize_historial_messages

    row = db.scalar(
        select(CasoConversacion).where(
            CasoConversacion.organizacion_id == org_id,
            CasoConversacion.session_id == session_id,
        )
    )
    if not row:
        return
    try:
        datos = json.loads(row.datos_triaje_json or "{}")
    except json.JSONDecodeError:
        datos = {}
    hist = list(datos.get("historial_mensajes") or [])
    hist.extend(sanitize_historial_messages(nuevos, max_msgs=max_msgs))
    datos["historial_mensajes"] = sanitize_historial_messages(hist, max_msgs=max_msgs)
    row.datos_triaje_json = json.dumps(datos, ensure_ascii=False)
    row.updated_at = datetime.now(UTC)
    db.commit()


def patch_caso_datos_triaje(
    db: Session,
    org_id: str,
    caso_id: str,
    datos_triaje: dict,
) -> None:
    row = db.scalar(
        select(CasoConversacion).where(
            CasoConversacion.id == caso_id,
            CasoConversacion.organizacion_id == org_id,
        )
    )
    if not row:
        return
    row.datos_triaje_json = json.dumps(datos_triaje, ensure_ascii=False)
    row.updated_at = datetime.now(UTC)
    db.commit()


def list_tickets_abiertos(db: Session, org_id: str) -> list[Ticket]:
    """Tickets no cerrados del tenant (cualquier estado distinto de Cerrado)."""
    return list(
        db.scalars(
            select(Ticket)
            .where(
                Ticket.organizacion_id == org_id,
                Ticket.estado != "Cerrado",
            )
            .order_by(Ticket.created_at.desc())
        ).all()
    )


def cerrar_tickets_abiertos(
    db: Session,
    org_id: str,
    *,
    resolucion_tecnica: str,
    actor: str = "sistema",
    dry_run: bool = False,
) -> dict:
    """Cierra en lote tickets abiertos del tenant sin learning/KB ni encuesta CSAT.

    Pensado para limpieza operativa antes de pruebas (pilotar/prod), no para
    resolución real de casos productivos.
    """
    resolucion = (resolucion_tecnica or "").strip()
    if not resolucion:
        raise ValueError("resolucion_tecnica es obligatoria")

    abiertos = list_tickets_abiertos(db, org_id)
    ids = [t.id for t in abiertos]
    preview = {
        "tickets_abiertos": len(ids),
        "ticket_ids": ids[:50],
        "ticket_ids_truncados": max(0, len(ids) - 50),
        "dry_run": dry_run,
    }
    if dry_run or not ids:
        return {
            **preview,
            "tickets_cerrados": 0,
            "conversaciones_cerradas": 0,
            "notificaciones_leidas": 0,
        }

    now = datetime.now(UTC)
    for t in abiertos:
        t.estado = "Cerrado"
        t.estado_sla = "Cerrado"
        t.resolucion_tecnica = resolucion
        t.updated_at = now
        db.add(
            TicketEvent(
                organizacion_id=org_id,
                ticket_id=t.id,
                tipo="cierre_masivo",
                titulo="Cierre masivo (limpieza operativa)",
                detalle=resolucion[:500],
                nivel=t.nivel or "N1",
                estado="Cerrado",
                actor=actor,
                visible_cliente="No",
            )
        )

    notifs = list(
        db.scalars(
            select(TicketNotification).where(
                TicketNotification.organizacion_id == org_id,
                TicketNotification.ticket_id.in_(ids),
                TicketNotification.leida == "No",
            )
        ).all()
    )
    for n in notifs:
        n.leida = "Sí"

    convs = list(
        db.scalars(
            select(ConversacionCanal).where(
                ConversacionCanal.organizacion_id == org_id,
                ConversacionCanal.ticket_id.in_(ids),
                ConversacionCanal.estado != "cerrado",
            )
        ).all()
    )
    for c in convs:
        c.estado = "cerrado"
        c.updated_at = now

    db.commit()
    return {
        **preview,
        "tickets_cerrados": len(ids),
        "conversaciones_cerradas": len(convs),
        "notificaciones_leidas": len(notifs),
    }


def reset_demo_validacion(
    db: Session,
    org_id: str,
    *,
    incluir_tickets: bool = True,
) -> dict:
    """Limpia estado operativo de demo: casos conversacionales y tickets opcionales."""
    casos = db.scalar(
        select(func.count()).select_from(CasoConversacion).where(
            CasoConversacion.organizacion_id == org_id
        )
    ) or 0
    db.execute(delete(CasoConversacion).where(CasoConversacion.organizacion_id == org_id))

    tickets = 0
    if incluir_tickets:
        tickets = db.scalar(
            select(func.count()).select_from(Ticket).where(Ticket.organizacion_id == org_id)
        ) or 0
        ticket_ids = list(
            db.scalars(select(Ticket.id).where(Ticket.organizacion_id == org_id)).all()
        )
        if ticket_ids:
            db.execute(
                delete(TicketNotification).where(TicketNotification.ticket_id.in_(ticket_ids))
            )
            db.execute(delete(TicketEvent).where(TicketEvent.ticket_id.in_(ticket_ids)))
        db.execute(delete(Ticket).where(Ticket.organizacion_id == org_id))

    pilot_n = db.scalar(
        select(func.count()).select_from(PilotEvent).where(PilotEvent.organizacion_id == org_id)
    ) or 0
    db.execute(delete(PilotEvent).where(PilotEvent.organizacion_id == org_id))

    db.commit()
    return {
        "casos_eliminados": casos,
        "tickets_eliminados": tickets if incluir_tickets else 0,
        "eventos_piloto_eliminados": pilot_n,
    }


def add_pilot_event(
    db: Session,
    org_id: str,
    tipo: str,
    *,
    session_id: str = "",
    escenario_id: str = "",
    categoria: str = "",
    paso_id: str = "",
    ticket_id: str = "",
    actor: str = "",
    detalle: dict | None = None,
) -> dict:
    row = PilotEvent(
        organizacion_id=org_id,
        session_id=session_id,
        tipo=tipo,
        escenario_id=escenario_id,
        categoria=categoria,
        paso_id=paso_id,
        ticket_id=ticket_id,
        actor=actor,
        detalle_json=json.dumps(detalle or {}, ensure_ascii=False),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _pilot_event_to_dict(row)


def _pilot_event_to_dict(row: PilotEvent) -> dict:
    try:
        detalle = json.loads(row.detalle_json or "{}")
    except json.JSONDecodeError:
        detalle = {}
    return {
        "id": row.id,
        "tipo": row.tipo,
        "session_id": row.session_id,
        "escenario_id": row.escenario_id,
        "categoria": row.categoria,
        "paso_id": row.paso_id,
        "ticket_id": row.ticket_id,
        "actor": row.actor,
        "detalle": detalle,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def list_pilot_events(db: Session, org_id: str, *, limit: int = 100) -> list[dict]:
    rows = db.scalars(
        select(PilotEvent)
        .where(PilotEvent.organizacion_id == org_id)
        .order_by(PilotEvent.created_at.desc())
        .limit(limit)
    ).all()
    return [_pilot_event_to_dict(r) for r in rows]


def limpiar_pilot_events(db: Session, org_id: str) -> int:
    n = db.scalar(
        select(func.count()).select_from(PilotEvent).where(PilotEvent.organizacion_id == org_id)
    ) or 0
    db.execute(delete(PilotEvent).where(PilotEvent.organizacion_id == org_id))
    return n


def resumen_pilot_events(db: Session, org_id: str) -> dict:
    eventos = list_pilot_events(db, org_id, limit=500)
    por_tipo: dict[str, int] = {}
    por_escenario: dict[str, dict[str, int]] = {}
    sesiones: dict[str, dict] = {}

    for ev in eventos:
        por_tipo[ev["tipo"]] = por_tipo.get(ev["tipo"], 0) + 1
        esc = ev.get("escenario_id") or "_sin_escenario"
        bucket = por_escenario.setdefault(
            esc,
            {"iniciados": 0, "pasos": 0, "tickets": 0},
        )
        if ev["tipo"] == "escenario_iniciado":
            bucket["iniciados"] += 1
        elif ev["tipo"] == "paso_confirmado":
            bucket["pasos"] += 1
        elif ev["tipo"] == "ticket_creado":
            bucket["tickets"] += 1

        sid = ev.get("session_id") or ""
        if sid:
            s = sesiones.setdefault(
                sid,
                {
                    "session_id": sid,
                    "escenario_id": ev.get("escenario_id") or "",
                    "pasos": 0,
                    "ticket_id": "",
                    "inicio": ev.get("created_at", ""),
                    "ultimo_evento": ev.get("created_at", ""),
                },
            )
            if ev["tipo"] == "paso_confirmado":
                s["pasos"] += 1
            if ev["tipo"] == "ticket_creado":
                s["ticket_id"] = ev.get("ticket_id") or s["ticket_id"]
            if ev.get("escenario_id"):
                s["escenario_id"] = ev["escenario_id"]

    sesiones_list = sorted(
        sesiones.values(),
        key=lambda x: x.get("ultimo_evento") or "",
        reverse=True,
    )[:20]

    return {
        "total_eventos": len(eventos),
        "por_tipo": por_tipo,
        "por_escenario": por_escenario,
        "sesiones_recientes": sesiones_list,
        "ultimos_eventos": eventos[:15],
    }


# --- Network outages (incidentes masivos) ---


def list_network_outages(
    db: Session,
    org_id: str,
    *,
    estado: str | None = "activo",
) -> list[NetworkOutage]:
    q = select(NetworkOutage).where(NetworkOutage.organizacion_id == org_id)
    if estado:
        q = q.where(NetworkOutage.estado == estado)
    q = q.order_by(NetworkOutage.started_at.desc())
    return list(db.scalars(q).all())


def get_network_outage(db: Session, org_id: str, outage_id: str) -> NetworkOutage | None:
    return db.scalar(
        select(NetworkOutage).where(
            NetworkOutage.organizacion_id == org_id,
            NetworkOutage.id == outage_id,
        )
    )


def create_network_outage(
    db: Session,
    org_id: str,
    *,
    nas_shortname: str,
    nas_ip: str = "",
    alcance: str = "total",
    tipo: str = "DOWN",
    comentario: str = "",
    mensaje_cliente: str = "",
    eta_minutos: int = 45,
    eta_validada: str = "Sí",
    nas_reachable_at_declare: str = "",
    created_by: str = "",
    fuente: str = "manual",
) -> NetworkOutage:
    o = NetworkOutage(
        organizacion_id=org_id,
        nas_shortname=(nas_shortname or "").strip(),
        nas_ip=(nas_ip or "").strip(),
        alcance=(alcance or "total").strip().lower() or "total",
        tipo=(tipo or "DOWN").strip() or "DOWN",
        comentario=(comentario or "").strip(),
        mensaje_cliente=(mensaje_cliente or "").strip(),
        eta_minutos=max(1, int(eta_minutos or 45)),
        eta_validada=(eta_validada or "Sí").strip() or "Sí",
        nas_reachable_at_declare=(nas_reachable_at_declare or "").strip(),
        estado="activo",
        fuente=(fuente or "manual").strip() or "manual",
        created_by=(created_by or "").strip(),
        started_at=datetime.now(UTC),
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def update_network_outage(
    db: Session,
    outage: NetworkOutage,
    *,
    alcance: str | None = None,
    tipo: str | None = None,
    comentario: str | None = None,
    mensaje_cliente: str | None = None,
    eta_minutos: int | None = None,
    eta_validada: str | None = None,
) -> NetworkOutage:
    if alcance is not None:
        outage.alcance = (alcance or "total").strip().lower() or "total"
    if tipo is not None:
        outage.tipo = (tipo or "DOWN").strip() or "DOWN"
    if comentario is not None:
        outage.comentario = (comentario or "").strip()
    if mensaje_cliente is not None:
        outage.mensaje_cliente = (mensaje_cliente or "").strip()
    if eta_minutos is not None:
        outage.eta_minutos = max(1, int(eta_minutos))
    if eta_validada is not None:
        outage.eta_validada = (eta_validada or "No").strip() or "No"
    outage.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(outage)
    return outage


def resolve_network_outage(db: Session, outage: NetworkOutage) -> NetworkOutage:
    outage.estado = "resuelto"
    outage.resolved_at = datetime.now(UTC)
    outage.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(outage)
    return outage
