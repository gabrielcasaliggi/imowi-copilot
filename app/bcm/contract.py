"""Contrato normalizado de ONU/ONT FTTH (Sopnet BCM), independiente del JSON crudo."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

CalidadOptica = Literal["buena", "aceptable", "mala", ""]
RamaBcm = Literal["onu_offline", "potencia_mala", "enlace_ok", ""]
BandaWifiBcm = Literal["2", "5"]
OperacionWifiBcm = Literal["password", "ssid"]


@dataclass
class ResultadoCambioWifi:
    """Resultado de un POST TR Wi‑Fi (una banda). Nunca incluir la clave en logs."""

    ok: bool
    banda: BandaWifiBcm
    operacion: OperacionWifiBcm
    http_status: int | None = None
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "banda": self.banda,
            "operacion": self.operacion,
            "http_status": self.http_status,
            "error": self.error,
        }


@dataclass
class EstadoOnuBcm:
    """ONU/ONT vista desde BCM, indexada por número de cliente del ERP (BillTrack)."""

    numero_cliente: str
    encontrado: bool = False
    online: bool | None = None
    nombre: str = ""
    apellido: str = ""
    serial: str = ""
    modelo: str = ""
    mac: str = ""
    olt_nombre: str = ""
    pon: str = ""
    rx_dbm: float | None = None
    tx_dbm: float | None = None
    calidad_optica: CalidadOptica = ""
    fuente: str = "bcm"
    error: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def resumen_prompt(self) -> str:
        """Texto corto para CONTEXTO_ABONADO (sin inventar)."""
        if self.error and not self.encontrado:
            return f"error consulta: {self.error[:80]}"
        nro = self.numero_cliente or "(sin nro_cliente)"
        parts = [f"nro_cliente={nro}"]
        if not self.encontrado:
            parts.append("onu=(no encontrado en BCM)")
            return "; ".join(parts)
        if self.serial:
            parts.append(f"serial={self.serial}")
        if self.modelo:
            parts.append(f"modelo={self.modelo}")
        if self.olt_nombre:
            parts.append(f"olt={self.olt_nombre}")
        if self.pon:
            parts.append(f"pon={self.pon}")
        if self.online is True:
            parts.append("estado=en_linea")
        elif self.online is False:
            parts.append("estado=fuera_de_linea")
        else:
            parts.append("estado=sin_dato")
        if self.rx_dbm is not None:
            parts.append(f"rx={self.rx_dbm:.1f}dBm")
        if self.tx_dbm is not None:
            parts.append(f"tx={self.tx_dbm:.1f}dBm")
        if self.calidad_optica:
            parts.append(f"calidad={self.calidad_optica}")
        return "; ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "numero_cliente": self.numero_cliente,
            "encontrado": self.encontrado,
            "online": self.online,
            "nombre": self.nombre,
            "apellido": self.apellido,
            "serial": self.serial,
            "modelo": self.modelo,
            "mac": self.mac,
            "olt_nombre": self.olt_nombre,
            "pon": self.pon,
            "rx_dbm": self.rx_dbm,
            "tx_dbm": self.tx_dbm,
            "calidad_optica": self.calidad_optica,
            "fuente": self.fuente,
            "error": self.error,
            "resumen": self.resumen_prompt(),
        }


@runtime_checkable
class BcmProvider(Protocol):
    def ping(self) -> dict[str, Any]: ...

    def buscar_onu_por_cliente(self, numero_cliente: str) -> EstadoOnuBcm: ...

    def modificar_wifi_password_por_serial(
        self, serial: str, password: str, wifi: BandaWifiBcm
    ) -> ResultadoCambioWifi: ...

    def modificar_wifi_ssid_por_serial(
        self, serial: str, ssid: str, wifi: BandaWifiBcm
    ) -> ResultadoCambioWifi: ...
