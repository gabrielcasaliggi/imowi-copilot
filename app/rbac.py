"""Catálogo RBAC de consola — roles, permisos y matriz por defecto.

Ver docs/RBAC-ROLES-PERMISOS.md.
"""

from __future__ import annotations

from collections.abc import Iterable

# Roles efectivos en JWT / consola
ROLES_CONSOLA = ("admin", "supervisor", "ejecutivo", "agente")

ROLE_META: dict[str, dict[str, str]] = {
    "admin": {
        "nombre": "Administrador",
        "descripcion": "Plataforma: config bot, cooperativas, usuarios, roles y vista global.",
    },
    "supervisor": {
        "nombre": "Supervisor de área",
        "descripcion": "Su cooperativa: cola, derivar tickets, performance y gestión de agentes.",
    },
    "ejecutivo": {
        "nombre": "Ejecutivo",
        "descripcion": "Su cooperativa: stats del bot, dashboards y exportación de reportes.",
    },
    "agente": {
        "nombre": "Agente",
        "descripcion": "Su cooperativa: disponibilidad, cola completa y performance propia.",
    },
}

PERMISSION_META: dict[str, dict[str, str]] = {
    "orgs.manage": {"dominio": "plataforma", "descripcion": "Crear y editar cooperativas"},
    "bot.configure": {"dominio": "plataforma", "descripcion": "Configurar bot y settings de plataforma"},
    "roles.manage": {"dominio": "plataforma", "descripcion": "Gestionar roles y matriz de permisos"},
    "users.manage": {"dominio": "plataforma", "descripcion": "CRUD global de usuarios"},
    "users.manage_agents": {"dominio": "usuarios", "descripcion": "Crear y desactivar agentes de su cooperativa"},
    "tenant.switch": {"dominio": "plataforma", "descripcion": "Cambiar de tenant / ver otras orgs"},
    "tickets.queue.view": {"dominio": "tickets", "descripcion": "Ver cola de tickets"},
    "tickets.view": {"dominio": "tickets", "descripcion": "Ver detalle de tickets abiertos/cerrados"},
    "tickets.reassign": {"dominio": "tickets", "descripcion": "Derivar / reasignar tickets"},
    "tickets.update": {"dominio": "tickets", "descripcion": "Actualizar seguimiento / estado de tickets"},
    "agent.availability": {"dominio": "agente", "descripcion": "Cambiar estado de disponibilidad"},
    "stats.global": {"dominio": "stats", "descripcion": "Estadísticas globales multi-cooperativa"},
    "stats.bot": {"dominio": "stats", "descripcion": "Performance del bot (su org)"},
    "stats.agents": {"dominio": "stats", "descripcion": "Performance de agentes (su org)"},
    "stats.self": {"dominio": "stats", "descripcion": "Actividad / performance propia"},
    "reports.export": {"dominio": "stats", "descripcion": "Exportar reportes"},
    "kb.propose": {"dominio": "kb", "descripcion": "Proponer artículos a la base de conocimiento"},
    "kb.publish": {"dominio": "kb", "descripcion": "Publicar / revisar propuestas KB"},
}

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": frozenset(PERMISSION_META.keys()),
    "supervisor": frozenset(
        {
            "users.manage_agents",
            "tickets.queue.view",
            "tickets.view",
            "tickets.reassign",
            "tickets.update",
            "stats.agents",
            "stats.self",
            "reports.export",
            "kb.propose",
        }
    ),
    "ejecutivo": frozenset(
        {
            "stats.bot",
            "stats.self",
            "reports.export",
        }
    ),
    "agente": frozenset(
        {
            "tickets.queue.view",
            "tickets.view",
            "agent.availability",
            "stats.self",
            "kb.propose",
        }
    ),
}

_LEGACY_A_CONSOLA = {
    "admin": "admin",
    "admin_sistema": "admin",
    "supervisor": "supervisor",
    "admin_org": "supervisor",
    "ejecutivo": "ejecutivo",
    "agente": "agente",
    "operador": "agente",
    "cooperativa": "agente",
    "cliente": "agente",
}


def normalizar_rol_consola(rol: str, org_slug: str | None = None) -> str:
    """Mapea roles legacy/DB al rol efectivo de consola."""
    r = (rol or "").strip().lower()
    if r == "ingeniero_noc":
        return "admin" if (org_slug or "").strip().lower() == "imowi" else "supervisor"
    mapped = _LEGACY_A_CONSOLA.get(r)
    if mapped:
        return mapped
    if r in ROLES_CONSOLA:
        return r
    return "agente"


def permisos_para_rol(rol: str) -> frozenset[str]:
    rol_n = normalizar_rol_consola(rol)
    return ROLE_PERMISSIONS.get(rol_n, ROLE_PERMISSIONS["agente"])


def puede(rol_o_permisos: str | Iterable[str], codigo: str) -> bool:
    if isinstance(rol_o_permisos, str):
        perms = permisos_para_rol(rol_o_permisos)
    else:
        perms = frozenset(rol_o_permisos)
    return codigo in perms


def catalogo_roles() -> list[dict]:
    out = []
    for codigo in ROLES_CONSOLA:
        meta = ROLE_META[codigo]
        out.append(
            {
                "codigo": codigo,
                "nombre": meta["nombre"],
                "descripcion": meta["descripcion"],
                "permisos": sorted(ROLE_PERMISSIONS[codigo]),
                "system": True,
            }
        )
    return out


def catalogo_permisos() -> list[dict]:
    return [
        {
            "codigo": codigo,
            "dominio": meta["dominio"],
            "descripcion": meta["descripcion"],
        }
        for codigo, meta in sorted(PERMISSION_META.items())
    ]


def roles_alta_permitidos(*, actor_rol: str, org_slug: str) -> frozenset[str]:
    """Roles que un actor puede asignar al crear usuarios."""
    actor = normalizar_rol_consola(actor_rol, org_slug)
    if actor == "admin":
        if org_slug == "imowi":
            return frozenset({"admin", "supervisor", "ejecutivo", "agente"})
        return frozenset({"supervisor", "ejecutivo", "agente"})
    if actor == "supervisor":
        return frozenset({"agente"})
    return frozenset()
