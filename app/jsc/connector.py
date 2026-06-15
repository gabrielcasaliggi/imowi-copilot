"""Adaptador JSC — implementa JSCProvider sobre réplica local (demo)."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.estate import repository as repo
from app.jsc.contract import FichaLineaJSC


def _normalizar_msisdn(msisdn: str) -> str:
    digits = re.sub(r"\D", "", msisdn or "")
    return digits[-10:] if len(digits) > 10 else digits


def _row_a_ficha(linea) -> FichaLineaJSC | None:
    if not linea:
        return None
    return FichaLineaJSC(
        msisdn=linea.msisdn,
        jsc_ref=linea.jsc_ref,
        abonado=linea.abonado,
        plan=linea.plan,
        estado_linea=linea.estado_linea,
        iccid=linea.iccid,
        roaming_habilitado=linea.roaming_habilitado,
        apn=linea.apn,
        estado_cuenta=linea.estado_cuenta,
        saldo_resumen=linea.saldo_resumen,
        ultima_sync=linea.ultima_sync,
        fuente="JSC (sync demo)",
        contable="Sistema contable (consulta demo)",
    )


class JSCConnectorDemo:
    """Implementación demo del contrato JSCProvider."""

    def __init__(self, db: Session):
        self._db = db

    def buscar_linea(
        self, org_id: str, msisdn: str, *, admin_global: bool = False
    ) -> FichaLineaJSC | None:
        n = _normalizar_msisdn(msisdn)
        if not n:
            return None
        row = repo.get_linea_by_msisdn(self._db, org_id, n, admin_global=admin_global)
        return _row_a_ficha(row)

    def listar_lineas(
        self, org_id: str, *, limit: int = 50, admin_global: bool = False
    ) -> list[FichaLineaJSC]:
        rows = repo.list_lineas(self._db, org_id, limit=limit, admin_global=admin_global)
        return [f for r in rows if (f := _row_a_ficha(r))]

    def buscar(
        self, org_id: str, query: str, *, limit: int = 10, admin_global: bool = False
    ) -> list[FichaLineaJSC]:
        rows = repo.search_lineas(self._db, org_id, query, limit=limit, admin_global=admin_global)
        return [f for r in rows if (f := _row_a_ficha(r))]


def get_connector(db: Session) -> JSCConnectorDemo:
    return JSCConnectorDemo(db)


def buscar_linea(db: Session, org_id: str, msisdn: str, *, admin_global: bool = False):
    """Compatibilidad con código existente — retorna fila ORM."""
    n = _normalizar_msisdn(msisdn)
    if not n:
        return None
    return repo.get_linea_by_msisdn(db, org_id, n, admin_global=admin_global)


def ficha_linea(linea) -> dict | None:
    ficha = _row_a_ficha(linea)
    return ficha.to_dict() if ficha else None


def listar_lineas_org(db: Session, org_id: str, *, limit: int = 50, admin_global: bool = False):
    conn = JSCConnectorDemo(db)
    return [f.to_dict() for f in conn.listar_lineas(org_id, limit=limit, admin_global=admin_global)]
