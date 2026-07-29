"""Catálogo operativo local — réplica JSC para desarrollo y pruebas sin API real."""

from __future__ import annotations

from app.estate.models import Abonado, KnowledgeArticle, LineaJSC, NetworkElement, Organization, User
from app.estate.security import hash_password
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _org(db: Session, slug: str) -> Organization | None:
    return db.scalar(select(Organization).where(Organization.slug == slug))


def seed_estate(db: Session) -> dict:
    if db.scalar(select(Organization).limit(1)):
        return {"seeded": False, "message": "Data Estate ya inicializado"}

    orgs = [
        Organization(nombre="Administración", slug="imowi", logo_label="A", brand_color="#22d3ee"),
        Organization(nombre="Cooperativa Batán", slug="coop-batan", logo_label="B", brand_color="#34d399"),
        Organization(nombre="Cooperativa Viamonte", slug="coop-viamonte", logo_label="V", brand_color="#818cf8"),
    ]
    db.add_all(orgs)
    db.flush()

    imowi, batan, viamonte = orgs

    users = [
        User(organizacion_id=imowi.id, email="admin@ops-hub.demo", nombre="Admin Sistema NOC", password=hash_password("admin"), rol="admin_sistema"),
        User(organizacion_id=imowi.id, email="noc@ops-hub.demo", nombre="Ingeniero NOC", password=hash_password("noc"), rol="ingeniero_noc"),
        User(organizacion_id=batan.id, email="noc@coopbatan.com", nombre="Ingeniero NOC CoopBatán", password=hash_password("noc"), rol="ingeniero_noc"),
        User(organizacion_id=batan.id, email="cliente@coopbatan.com", nombre="Operador Coop Batán", password=hash_password("cliente"), rol="cliente", must_change_password="Sí"),
        User(organizacion_id=viamonte.id, email="cliente@coopviamonte.com", nombre="Cliente Coop Viamonte", password=hash_password("cliente"), rol="cliente", must_change_password="Sí"),
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
        NetworkElement(organizacion_id=imowi.id, elemento_red="Core-NOC-01", metrica="latencia", valor_actual="8ms", estado_actual="Normal"),
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
            LineaJSC(organizacion_id=imowi.id, msisdn="2235500001", jsc_ref="JSC-L-90001", abonado="Línea corporativa NOC", plan="Corporativo", estado_linea="Activa", iccid="8956123450090001", apn="internet.movil", roaming_habilitado="Sí", estado_cuenta="Al día", saldo_resumen="$0")
        )
    db.add_all(lineas)
    db.commit()
    return {"seeded": True, "lineas": len(lineas)}


def seed_abonados(db: Session) -> dict:
    """Abonados demo Ecolan / móvil para canal WhatsApp (idempotente)."""
    if db.scalar(select(Abonado).limit(1)):
        n = db.scalar(select(func.count()).select_from(Abonado))
        return {"seeded": False, "abonados": n or 0}

    batan = _org(db, "coop-batan")
    if not batan:
        return {"seeded": False, "abonados": 0}

    abonados = [
        Abonado(
            organizacion_id=batan.id,
            dni="30111222",
            telefono_e164="5492235551234",
            nombre="María González",
            servicio="ambos",
            estado="activo",
            deuda_monto="0",
            plan="Ecolan 50Mb + Móvil 5GB",
            linea_msisdn="2235551234",
        ),
        Abonado(
            organizacion_id=batan.id,
            dni="28555666",
            telefono_e164="5492235555678",
            nombre="Carlos Pérez",
            servicio="internet",
            estado="activo",
            deuda_monto="0",
            plan="Ecolan 100Mb",
            linea_msisdn="",
        ),
        Abonado(
            organizacion_id=batan.id,
            dni="32123456",
            telefono_e164="5492235559012",
            nombre="Ana Ruiz",
            servicio="movil",
            estado="corte",
            deuda_monto="2800",
            plan="Móvil 3GB",
            linea_msisdn="2235559012",
        ),
        Abonado(
            organizacion_id=batan.id,
            dni="27333444",
            telefono_e164="5492235560001",
            nombre="Jorge Martínez",
            servicio="internet",
            estado="suspendido",
            deuda_monto="4500",
            plan="Ecolan 50Mb",
            linea_msisdn="",
        ),
        Abonado(
            organizacion_id=batan.id,
            dni="29888777",
            telefono_e164="5492235560002",
            nombre="Laura Díaz",
            servicio="ambos",
            estado="activo",
            deuda_monto="0",
            plan="Ecolan 100Mb + Móvil 15GB",
            linea_msisdn="2235560002",
        ),
        Abonado(
            organizacion_id=batan.id,
            dni="26444555",
            telefono_e164="5492235560099",
            nombre="Pedro Ecolan",
            servicio="internet",
            estado="activo",
            deuda_monto="0",
            plan="Ecolan 30Mb",
            linea_msisdn="",
        ),
    ]
    db.add_all(abonados)

    # KB internet Ecolan
    kb_extra = [
        KnowledgeArticle(
            organizacion_id=batan.id,
            titulo="Ecolan — sin internet en casa",
            categoria="Internet",
            contenido=(
                "N1 Ecolan: 1) Reiniciar módem 30s. 2) Probar cable vs WiFi. "
                "3) Verificar luces del módem. 4) Si hay deuda/corte, informar medios de pago. "
                "5) Persistencia → ticket N2."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=batan.id,
            titulo="Corte por deuda — rehabilitación",
            categoria="Facturación",
            contenido=(
                "Si el abonado tiene estado corte/suspendido, indicar regularización de saldo. "
                "La rehabilitación es automática tras acreditación. No reiniciar equipos hasta regularizar."
            ),
        ),
    ]
    db.add_all(kb_extra)
    db.commit()
    return {"seeded": True, "abonados": len(abonados)}


def seed_inbox_conversaciones(db: Session) -> dict:
    """Hilos WhatsApp abiertos para operar la bandeja sin Meta (idempotente)."""
    from app.estate.models import ConversacionCanal, MensajeCanal
    import json

    batan = _org(db, "coop-batan")
    if not batan:
        return {"seeded": False, "conversaciones": 0}

    abiertas = db.scalar(
        select(func.count())
        .select_from(ConversacionCanal)
        .where(
            ConversacionCanal.organizacion_id == batan.id,
            ConversacionCanal.estado != "cerrado",
        )
    )
    if abiertas and abiertas > 0:
        return {"seeded": False, "conversaciones": abiertas}

    by_tel = {
        a.telefono_e164: a
        for a in db.scalars(select(Abonado).where(Abonado.organizacion_id == batan.id)).all()
    }
    maria = by_tel.get("5492235551234")
    ana = by_tel.get("5492235559012")
    carlos = by_tel.get("5492235555678")
    if not maria or not ana or not carlos:
        return {"seeded": False, "conversaciones": 0, "reason": "faltan_abonados"}

    scenarios: list[tuple[Abonado, str, str, list[tuple[str, str, str]], dict]] = [
        (
            maria,
            "bot",
            "internet",
            [
                ("in", "cliente", "Hola, no me anda el internet"),
                (
                    "out",
                    "bot",
                    "Hola María. Vamos con internet Ecolan. ¿Podés apagar el módem 30 segundos, "
                    "encenderlo y decirme si vuelve la conexión?",
                ),
            ],
            {"intencion": "internet", "paso_idx": 0, "identificado": True},
        ),
        (
            ana,
            "espera_agente",
            "corte_deuda",
            [
                ("in", "cliente", "Hola, me cortaron el servicio"),
                (
                    "out",
                    "bot",
                    "Tu cuenta figura con estado «corte» y saldo pendiente $2800. "
                    "Tu cuenta tiene un saldo pendiente y el servicio puede estar limitado. "
                    "¿Querés que te indique cómo regularizarlo?",
                ),
                ("in", "cliente", "Quiero hablar con un agente"),
                (
                    "out",
                    "bot",
                    "Te derivo con un agente de Cooperativa Batán. Quedás en cola.",
                ),
            ],
            {"intencion": "corte_deuda", "paso_idx": 0, "identificado": True, "escalado": True},
        ),
        (
            carlos,
            "espera_agente",
            "internet",
            [
                ("in", "cliente", "Sigue sin internet después de reiniciar"),
                (
                    "out",
                    "bot",
                    "¿Las luces del módem son normales (sin alarma roja fija)? Respondé sí o no.",
                ),
                ("in", "cliente", "También por cable, necesito un técnico"),
                (
                    "out",
                    "bot",
                    "Entendido. Generamos el seguimiento y un agente de Batán te va a atender.",
                ),
            ],
            {"intencion": "internet", "paso_idx": 1, "identificado": True, "escalado": True},
        ),
    ]

    created = 0
    for abo, estado, servicio, msgs, ctx in scenarios:
        conv = ConversacionCanal(
            organizacion_id=batan.id,
            canal="whatsapp",
            wa_id=abo.telefono_e164,
            telefono=abo.telefono_e164,
            abonado_id=abo.id,
            estado=estado,
            servicio_detectado=servicio,
            session_id=f"wa:{batan.id}:{abo.telefono_e164}",
            contexto_json=json.dumps(ctx, ensure_ascii=False),
            ticket_id="",
        )
        db.add(conv)
        db.flush()
        for direccion, autor, texto in msgs:
            db.add(
                MensajeCanal(
                    organizacion_id=batan.id,
                    conversacion_id=conv.id,
                    direccion=direccion,
                    autor=autor,
                    texto=texto,
                )
            )
        created += 1

    db.commit()
    return {"seeded": True, "conversaciones": created}
