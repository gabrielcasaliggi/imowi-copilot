"""Catálogo operativo local — réplica JSC para desarrollo y pruebas sin API real."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.estate.models import KnowledgeArticle, LineaJSC, NetworkElement, Organization, User


def _org(db: Session, slug: str) -> Organization | None:
    return db.scalar(select(Organization).where(Organization.slug == slug))


def seed_estate(db: Session) -> dict:
    if db.scalar(select(Organization).limit(1)):
        return {"seeded": False, "message": "Data Estate ya inicializado"}

    orgs = [
        Organization(nombre="imowi NOC", slug="imowi", logo_label="i", brand_color="#22d3ee"),
        Organization(nombre="Cooperativa Batán", slug="coop-batan", logo_label="B", brand_color="#34d399"),
        Organization(nombre="Cooperativa Viamonte", slug="coop-viamonte", logo_label="V", brand_color="#818cf8"),
    ]
    db.add_all(orgs)
    db.flush()

    imowi, batan, viamonte = orgs

    users = [
        User(organizacion_id=imowi.id, email="admin@imowi.com", nombre="Admin Sistema imowi", password="admin", rol="admin_sistema"),
        User(organizacion_id=imowi.id, email="noc@imowi.com", nombre="Ingeniero NOC imowi", password="noc", rol="ingeniero_noc"),
        User(organizacion_id=batan.id, email="noc@coopbatan.com", nombre="Ingeniero NOC CoopBatán", password="noc", rol="ingeniero_noc"),
        User(organizacion_id=batan.id, email="cliente@coopbatan.com", nombre="Operador Coop Batán", password="cliente", rol="cliente"),
        User(organizacion_id=viamonte.id, email="cliente@coopviamonte.com", nombre="Cliente Coop Viamonte", password="cliente", rol="cliente"),
    ]
    db.add_all(users)

    kb = [
        KnowledgeArticle(
            organizacion_id=batan.id,
            titulo="Roaming internacional — Brasil",
            categoria="Roaming",
            contenido=(
                "Verificar registro en red visitada. Pasos: 1) Reinicio equipo. "
                "2) Forzar modo 3G/4G. 3) Verificar APN datos. "
                "4) Si persiste en zona Güemes, revisar Celda-Movistar-Güemes."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=batan.id,
            titulo="APN datos móviles",
            categoria="APN",
            contenido="APN: internet.coopbatan.ar — MCC 722 MNC 310. Validar con ping a 8.8.8.8.",
        ),
        KnowledgeArticle(
            organizacion_id=batan.id,
            titulo="eSIM activación",
            categoria="eSIM",
            contenido="Confirmar EID, reenviar QR OTA, validar perfil activo en ajustes del dispositivo.",
        ),
        KnowledgeArticle(
            organizacion_id=imowi.id,
            titulo="Procedimiento NOC — escalamiento core",
            categoria="Fibra",
            contenido="Escalar a core si OLT presenta anomalía predictiva >15min o pérdida de paquetes >5%.",
        ),
        KnowledgeArticle(
            organizacion_id=viamonte.id,
            titulo="Fibra FTTH — sin servicio",
            categoria="Fibra",
            contenido="Revisar potencia ONT, estado OLT-Viamonte-Norte, reiniciar ONT remotamente.",
        ),
    ]
    db.add_all(kb)

    telemetry = [
        NetworkElement(organizacion_id=batan.id, elemento_red="OLT-Batan-Centro", metrica="latencia", valor_actual="12ms", estado_actual="Normal"),
        NetworkElement(organizacion_id=batan.id, elemento_red="Celda-Movistar-Güemes", metrica="pérdida_paquetes", valor_actual="0.2%", estado_actual="Normal"),
        NetworkElement(organizacion_id=batan.id, elemento_red="PGW-Roaming-SUR", metrica="consumo", valor_actual="68%", estado_actual="Normal"),
        NetworkElement(organizacion_id=imowi.id, elemento_red="Core-IMOWI-01", metrica="latencia", valor_actual="8ms", estado_actual="Normal"),
        NetworkElement(organizacion_id=viamonte.id, elemento_red="OLT-Viamonte-Norte", metrica="latencia", valor_actual="14ms", estado_actual="Normal"),
    ]
    db.add_all(telemetry)
    db.commit()
    lineas_info = seed_lineas_jsc(db)
    return {
        "seeded": True,
        "organizaciones": len(orgs),
        "usuarios": len(users),
        "lineas_jsc": lineas_info.get("lineas", 0),
    }


def seed_lineas_jsc(db: Session) -> dict:
    """Réplica local de líneas/abonados JSC (catálogo operativo para entorno local)."""
    if db.scalar(select(LineaJSC).limit(1)):
        n = db.scalar(select(func.count()).select_from(LineaJSC))
        return {"seeded": False, "lineas": n or 0}

    batan = _org(db, "coop-batan")
    viamonte = _org(db, "coop-viamonte")
    imowi = _org(db, "imowi")
    if not batan:
        return {"seeded": False, "lineas": 0}

    lineas = [
        LineaJSC(organizacion_id=batan.id, msisdn="2235551234", jsc_ref="JSC-L-10001", abonado="María González", plan="Móvil 5GB", estado_linea="Activa", iccid="8956123450001234", apn="internet.coopbatan.ar", roaming_habilitado="Sí", estado_cuenta="Al día", saldo_resumen="$0"),
        LineaJSC(organizacion_id=batan.id, msisdn="2235555678", jsc_ref="JSC-L-10002", abonado="Carlos Pérez", plan="Móvil 10GB", estado_linea="Activa", iccid="8956123450005678", apn="internet.coopbatan.ar", roaming_habilitado="Sí", estado_cuenta="Al día", saldo_resumen="$1.240"),
        LineaJSC(organizacion_id=batan.id, msisdn="2235559012", jsc_ref="JSC-L-10003", abonado="Ana Ruiz", plan="Móvil 3GB", estado_linea="Suspendida", iccid="8956123450009012", apn="internet.coopbatan.ar", roaming_habilitado="No", estado_cuenta="Deuda", saldo_resumen="$-2.800"),
        LineaJSC(organizacion_id=batan.id, msisdn="2235560001", jsc_ref="JSC-L-10004", abonado="Jorge Martínez", plan="Móvil 8GB", estado_linea="Activa", iccid="8956123450010001", apn="internet.coopbatan.ar", roaming_habilitado="Sí", estado_cuenta="Al día", saldo_resumen="$0"),
        LineaJSC(organizacion_id=batan.id, msisdn="2235560002", jsc_ref="JSC-L-10005", abonado="Laura Díaz", plan="Móvil 15GB", estado_linea="Activa", iccid="8956123450010002", apn="internet.coopbatan.ar", roaming_habilitado="Sí", estado_cuenta="Al día", saldo_resumen="$560"),
        LineaJSC(organizacion_id=viamonte.id, msisdn="2235571001", jsc_ref="JSC-L-20001", abonado="Pedro Sosa", plan="Fibra 50Mb", estado_linea="Activa", iccid="8956123450020001", apn="internet.coopviamonte.ar", roaming_habilitado="N/A", estado_cuenta="Al día", saldo_resumen="$0"),
        LineaJSC(organizacion_id=viamonte.id, msisdn="2235571002", jsc_ref="JSC-L-20002", abonado="Silvia Acosta", plan="Móvil 5GB", estado_linea="Activa", iccid="8956123450020002", apn="internet.coopviamonte.ar", roaming_habilitado="Sí", estado_cuenta="Revisar", saldo_resumen="$-450"),
        LineaJSC(organizacion_id=viamonte.id, msisdn="2235571003", jsc_ref="JSC-L-20003", abonado="Miguel Torres", plan="Móvil 10GB", estado_linea="Activa", iccid="8956123450020003", apn="internet.coopviamonte.ar", roaming_habilitado="Sí", estado_cuenta="Al día", saldo_resumen="$0"),
    ]
    if imowi:
        lineas.append(
            LineaJSC(organizacion_id=imowi.id, msisdn="2235500001", jsc_ref="JSC-L-90001", abonado="Línea corporativa NOC", plan="Corporativo", estado_linea="Activa", iccid="8956123450090001", apn="internet.imowi.ar", roaming_habilitado="Sí", estado_cuenta="Al día", saldo_resumen="$0")
        )
    db.add_all(lineas)
    db.commit()
    return {"seeded": True, "lineas": len(lineas)}
