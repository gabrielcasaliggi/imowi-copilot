"""Contrato normalizado de CPE radio (UISP NMS), independiente del JSON crudo."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

CalidadSenal = Literal["buena", "aceptable", "mala", ""]
RamaUisp = Literal["cpe_offline", "senal_mala", "enlace_ok", ""]


@dataclass
class EstadoCpeUisp:
    """CPE radio visto desde UISP, indexado por el username Radius (identification.name)."""

    login: str
    encontrado: bool = False
    online: bool | None = None
    nombre: str = ""
    modelo: str = ""
    mac: str = ""
    sitio: str = ""
    ap_nombre: str = ""
    signal_dbm: float | None = None
    calidad_senal: CalidadSenal = ""
    uptime_seg: int | None = None
    device_id: str = ""
    fuente: str = "uisp"
    error: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def resumen_prompt(self) -> str:
        """Texto corto para CONTEXTO_ABONADO (sin inventar)."""
        if self.error and not self.encontrado:
            return f"error consulta: {self.error[:80]}"
        login = self.login or "(sin login)"
        parts = [f"login={login}"]
        if not self.encontrado:
            parts.append("cpe=(no encontrado en UISP)")
            return "; ".join(parts)
        parts.append(f"nombre={self.nombre or login}")
        if self.modelo:
            parts.append(f"modelo={self.modelo}")
        if self.sitio:
            parts.append(f"sitio={self.sitio}")
        if self.ap_nombre:
            parts.append(f"ap={self.ap_nombre}")
        if self.online is True:
            parts.append("estado=en_linea")
        elif self.online is False:
            parts.append("estado=fuera_de_linea")
        else:
            parts.append("estado=sin_dato")
        if self.signal_dbm is not None:
            parts.append(f"senal={self.signal_dbm:.0f}dBm")
        if self.calidad_senal:
            parts.append(f"calidad={self.calidad_senal}")
        if self.uptime_seg is not None and self.uptime_seg >= 0:
            parts.append(f"uptime_s={self.uptime_seg}")
        return "; ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "login": self.login,
            "encontrado": self.encontrado,
            "online": self.online,
            "nombre": self.nombre,
            "modelo": self.modelo,
            "mac": self.mac,
            "sitio": self.sitio,
            "ap_nombre": self.ap_nombre,
            "signal_dbm": self.signal_dbm,
            "calidad_senal": self.calidad_senal,
            "uptime_seg": self.uptime_seg,
            "device_id": self.device_id,
            "fuente": self.fuente,
            "error": self.error,
            "resumen": self.resumen_prompt(),
        }


@runtime_checkable
class UispNmsProvider(Protocol):
    def ping(self) -> dict[str, Any]: ...

    def buscar_cpe_por_login(self, login: str) -> EstadoCpeUisp: ...
