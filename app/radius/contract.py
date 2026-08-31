"""Contrato normalizado de sesión PPPoE / NAS (independiente del backend Radius)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ServicioConectividad:
    """Servicio de internet en BillTrack (api_service)."""

    login: str
    service_type_code: str = ""
    service_type_label: str = ""
    product: str = ""
    label: str = ""
    state: str = ""
    service_on: bool = True
    base_account_number: str = ""
    id: str = ""
    locality: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "login": self.login,
            "service_type_code": self.service_type_code,
            "service_type_label": self.service_type_label,
            "product": self.product,
            "label": self.label,
            "state": self.state,
            "service_on": self.service_on,
            "base_account_number": self.base_account_number,
            "id": self.id,
            "locality": self.locality,
        }


@dataclass
class SesionPPPoE:
    """Estado de sesión PPP en NAS (vía API Radius/MikroTik)."""

    username: str
    online: bool = False
    nas: str = ""
    public_ip: str = ""
    uptime: str = ""
    caller_id: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "online": self.online,
            "nas": self.nas,
            "public_ip": self.public_ip,
            "uptime": self.uptime,
            "caller_id": self.caller_id,
            "error": self.error,
        }


@dataclass
class EstadoConexionPPPoE:
    """Resultado listo para el bot: servicio BillTrack + sesión NAS."""

    servicio: ServicioConectividad | None = None
    sesion: SesionPPPoE | None = None
    servicios: list[ServicioConectividad] = field(default_factory=list)
    fuente: str = "radius"
    error: str = ""

    @property
    def online(self) -> bool | None:
        if self.sesion is None:
            return None
        if self.sesion.error and not self.sesion.online:
            return None
        return bool(self.sesion.online)

    def resumen_prompt(self) -> str:
        """Texto corto para CONTEXTO_ABONADO (sin inventar)."""
        if self.error and not self.servicio:
            return f"error consulta: {self.error[:80]}"
        if not self.servicio:
            return "sin servicio de conectividad en padrón"
        tipo = (
            self.servicio.service_type_label
            or self.servicio.product
            or self.servicio.service_type_code
            or "internet"
        )
        login = self.servicio.login or "(sin login)"
        parts = [f"tipo={tipo}", f"login={login}"]
        producto = (self.servicio.product or self.servicio.label or "").strip()
        if producto:
            parts.append(f"producto={producto}")
            from app.services.velocidad_plan import extraer_mbps_plan

            mbps = extraer_mbps_plan(producto)
            if mbps is not None:
                parts.append(f"plan_mbps={mbps:g}")
        if self.sesion is None:
            if self.error:
                parts.append(f"sesion=(sin dato — {self.error[:60]})")
            else:
                parts.append("sesion=(sin dato)")
            return "; ".join(parts)
        if self.sesion.error and not self.sesion.online:
            parts.append(f"sesion=error ({self.sesion.error[:60]})")
            return "; ".join(parts)
        if self.sesion.online:
            parts.append("estado=conectado")
            if self.sesion.public_ip:
                parts.append(f"ip={self.sesion.public_ip}")
            if self.sesion.uptime:
                parts.append(f"uptime={self.sesion.uptime}")
            if self.sesion.nas:
                parts.append(f"nas={self.sesion.nas}")
        else:
            parts.append("estado=desconectado (sin sesión PPP activa)")
            if self.sesion.nas:
                parts.append(f"nas={self.sesion.nas}")
        return "; ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "servicio": self.servicio.to_dict() if self.servicio else None,
            "sesion": self.sesion.to_dict() if self.sesion else None,
            "servicios": [s.to_dict() for s in self.servicios],
            "online": self.online,
            "resumen": self.resumen_prompt(),
            "fuente": self.fuente,
            "error": self.error,
        }


@dataclass
class NasInfo:
    """Entrada del inventario Radius (get_all_nas)."""

    shortname: str
    nasname: str = ""  # IP
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "shortname": self.shortname,
            "nasname": self.nasname,
            "ip": self.nasname,
        }


@dataclass
class NasResourceStatus:
    """Resultado de rest_list_resources (conectividad MikroTik)."""

    shortname: str
    reachable: bool
    error: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "shortname": self.shortname,
            "reachable": self.reachable,
            "error": self.error,
            "alcance_sugerido": "parcial" if self.reachable else "total",
            "resources": self.raw if self.reachable else {},
        }


@runtime_checkable
class RadiusNasProvider(Protocol):
    def get_nas(self, username: str) -> str: ...

    def list_ppp_session(self, nas: str, login: str) -> SesionPPPoE: ...

    def get_all_nas(self) -> list[NasInfo]: ...

    def rest_list_resources(self, shortname: str) -> NasResourceStatus: ...
