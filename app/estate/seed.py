"""Catálogo operativo local — réplica JSC para desarrollo y pruebas sin API real."""

from __future__ import annotations

import os

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.estate.models import (
    Abonado,
    KnowledgeArticle,
    LineaJSC,
    NetworkElement,
    Organization,
    User,
)
from app.estate.security import hash_password


def _org(db: Session, slug: str) -> Organization | None:
    return db.scalar(select(Organization).where(Organization.slug == slug))


def _hash_seed(*candidates: str) -> str:
    """Hash seguro para seed: usa la primera clave; no aplica política estricta."""
    for raw in candidates:
        plain = (raw or "").strip()
        if len(plain) >= 6:
            return hash_password(plain, enforce_policy=False)
    return hash_password("Changeme1a", enforce_policy=False)


def _seed_production_minimal(db: Session) -> dict:
    """Solo orgs base + admin inicial desde env (sin passwords demo)."""
    admin_pw = os.getenv("ADMIN_PASSWORD", "").strip()
    admin_email = (os.getenv("ADMIN_EMAIL", "") or "admin@localhost").strip().lower()
    if not admin_pw:
        return {
            "seeded": False,
            "message": "Production: definí ADMIN_PASSWORD para seed inicial o creá usuarios vía invite",
        }

    orgs = [
        Organization(nombre="Administración", slug="imowi", logo_label="A", brand_color="#2298A6"),
        Organization(nombre="Cooperativa Batán", slug="coop-batan", logo_label="B", brand_color="#2298A6"),
    ]
    db.add_all(orgs)
    db.flush()
    imowi = orgs[0]
    must = "No" if len(admin_pw) >= 10 else "Sí"
    # Si la clave no cumple política, hashear igual y forzar cambio
    try:
        pw_hash = hash_password(admin_pw)
        must = "Sí"  # primer acceso: cambiar
    except ValueError:
        pw_hash = hash_password(admin_pw, enforce_policy=False)
        must = "Sí"
    db.add(
        User(
            organizacion_id=imowi.id,
            email=admin_email,
            nombre=os.getenv("ADMIN_NOMBRE", "Administración"),
            password=pw_hash,
            rol="admin",
            must_change_password=must,
            email_verified_at=None,
        )
    )
    db.commit()
    return {"seeded": True, "organizaciones": len(orgs), "usuarios": 1, "mode": "production_minimal"}


def seed_estate(db: Session) -> dict:
    from app.config import demo_users_disabled, es_produccion

    if db.scalar(select(Organization).limit(1)):
        return {"seeded": False, "message": "Data Estate ya inicializado"}

    # En production no seedear usuarios demo débiles: solo org admin + admin inicial si hay env
    if es_produccion() or demo_users_disabled():
        return _seed_production_minimal(db)

    orgs = [
        Organization(nombre="Administración", slug="imowi", logo_label="A", brand_color="#2298A6"),
        Organization(nombre="Cooperativa Batán", slug="coop-batan", logo_label="B", brand_color="#2298A6"),
        Organization(nombre="Cooperativa Viamonte", slug="coop-viamonte", logo_label="V", brand_color="#1A7985"),
    ]
    db.add_all(orgs)
    db.flush()

    imowi, batan, viamonte = orgs

    admin_pw = os.getenv("ADMIN_PASSWORD", "").strip()
    coop_pw = os.getenv("COOP_PASSWORD", "").strip()

    users = [
        User(
            organizacion_id=imowi.id,
            email="admin@ops-hub.demo",
            nombre="Administración",
            password=_hash_seed(admin_pw, "Admin12Demo!"),
            rol="admin",
            must_change_password="Sí" if not admin_pw else "No",
        ),
        User(
            organizacion_id=imowi.id,
            email="noc@ops-hub.demo",
            nombre="Supervisor plataforma",
            password=_hash_seed("Noc123Demo!"),
            rol="admin",
            must_change_password="Sí",
        ),
        User(
            organizacion_id=batan.id,
            email="agente@coopbatan.com",
            nombre="Agente Batán",
            password=_hash_seed(coop_pw, "Batan1Demo!"),
            rol="agente",
            must_change_password="Sí",
        ),
        User(
            organizacion_id=batan.id,
            email="supervisor@coopbatan.com",
            nombre="Supervisor Batán",
            password=_hash_seed("Supervisor1!"),
            rol="supervisor",
            must_change_password="Sí",
        ),
        User(
            organizacion_id=batan.id,
            email="ejecutivo@coopbatan.com",
            nombre="Ejecutivo Batán",
            password=_hash_seed("Ejecutivo1!"),
            rol="ejecutivo",
            must_change_password="Sí",
        ),
        User(
            organizacion_id=batan.id,
            email="noc@coopbatan.com",
            nombre="Supervisor Batán (legacy)",
            password=_hash_seed("Noc123Demo!"),
            rol="supervisor",
            must_change_password="Sí",
        ),
        User(
            organizacion_id=viamonte.id,
            email="agente@coopviamonte.com",
            nombre="Agente Viamonte",
            password=_hash_seed("Viamonte1!"),
            rol="agente",
            must_change_password="Sí",
        ),
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
            contenido="APN: apn1.catel.org.ar — MCC 722 MNC 310. Validar con ping a 8.8.8.8.",
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
        LineaJSC(organizacion_id=batan.id, msisdn="2235551234", jsc_ref="JSC-L-10001", abonado="María González", plan="Móvil 5GB", estado_linea="Activa", iccid="8956123450001234", apn="apn1.catel.org.ar", roaming_habilitado="Sí", estado_cuenta="Al día", saldo_resumen="$0"),
        LineaJSC(organizacion_id=batan.id, msisdn="2235555678", jsc_ref="JSC-L-10002", abonado="Carlos Pérez", plan="Móvil 10GB", estado_linea="Activa", iccid="8956123450005678", apn="apn1.catel.org.ar", roaming_habilitado="Sí", estado_cuenta="Al día", saldo_resumen="$1.240"),
        LineaJSC(organizacion_id=batan.id, msisdn="2235559012", jsc_ref="JSC-L-10003", abonado="Ana Ruiz", plan="Móvil 3GB", estado_linea="Suspendida", iccid="8956123450009012", apn="apn1.catel.org.ar", roaming_habilitado="No", estado_cuenta="Deuda", saldo_resumen="$-2.800"),
        LineaJSC(organizacion_id=batan.id, msisdn="2235560001", jsc_ref="JSC-L-10004", abonado="Jorge Martínez", plan="Móvil 8GB", estado_linea="Activa", iccid="8956123450010001", apn="apn1.catel.org.ar", roaming_habilitado="Sí", estado_cuenta="Al día", saldo_resumen="$0"),
        LineaJSC(organizacion_id=batan.id, msisdn="2235560002", jsc_ref="JSC-L-10005", abonado="Laura Díaz", plan="Móvil 15GB", estado_linea="Activa", iccid="8956123450010002", apn="apn1.catel.org.ar", roaming_habilitado="Sí", estado_cuenta="Al día", saldo_resumen="$560"),
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

    # KB servicios Batán (también se asegura en seed_kb_batan_servicios)
    kb_extra = _articulos_kb_batan(batan.id)
    db.add_all(kb_extra)
    db.commit()
    return {"seeded": True, "abonados": len(abonados)}


def _articulos_kb_batan(org_id: str) -> list[KnowledgeArticle]:
    return [
        # ==================== INTERNET FTTH ====================
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Internet FTTH (fibra óptica) — sin servicio",
            categoria="Internet",
            contenido=(
                "Cooperativa Batán — Internet por fibra óptica hasta el hogar (FTTH/GPON). "
                "El abonado tiene una ONT (cajita blanca) conectada con un cable de fibra "
                "amarillo que viene de la calle, y un router WiFi conectado a la ONT por cable UTP.\n\n"
                "Diagnóstico N1:\n"
                "1) Reiniciar: desenchufar ONT y router 30s. Encender primero la ONT, esperar "
                "   luz PON verde fija (~1 min), luego encender router.\n"
                "2) Verificar luces ONT: PON=verde fijo (enlace OK), LOS=apagada (sin alarma). "
                "   Si LOS está en rojo → alarma óptica: NO manipular el cable amarillo; "
                "   derivar N2 (visita). Completar preguntas no equivale a resolver.\n"
                "3) Cables de energía y red (UTP) firmes, sin daño visible. "
                "   No desconectar ni doblar la fibra.\n"
                "4) Probar cable vs WiFi: si por cable al router anda, el problema es WiFi.\n"
                "5) Si nada de lo anterior resuelve → N2 (posible corte de fibra en la acometida "
                "   o falla en el splitter/OLT de la central). Registrar dirección y síntoma.\n"
                "Soporte: 0223 464-3006 · Mi Cuenta: https://ov.batan.coop"
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Internet FTTH — velocidad baja",
            categoria="Internet",
            contenido=(
                "Si la fibra anda pero lento:\n"
                "1) Verificar con speed test por cable (no WiFi). Si da >70% del plan, es normal.\n"
                "2) Verificar cuántos dispositivos conectados: streaming 4K, descargas, etc.\n"
                "3) Si por cable da bien y por WiFi no → problema de cobertura WiFi "
                "   (ver artículo WiFi — cobertura y rendimiento).\n"
                "4) Si por cable también da bajo → posible saturación del puerto PON o "
                "   configuración incorrecta del perfil de velocidad. Escalar a N2."
            ),
        ),

        # ==================== INTERNET RADIO/WIRELESS ====================
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Internet radio/wireless — sin servicio",
            categoria="Internet",
            contenido=(
                "Cooperativa Batán / Ecolan — Internet inalámbrico BAI (banda ancha inalámbrica, "
                "enlace punto-multipunto). El abonado tiene un CPE/antena en el techo apuntando "
                "a una torre, alimentado por PoE (inyector conectado al tomacorriente).\n\n"
                "Diagnóstico N1:\n"
                "1) Inyector PoE: ¿tiene luz encendida? Si no, verificar enchufe y fusible.\n"
                "2) Cable PoE: la salida LAN del inyector/transformador va al puerto AZUL "
                "   (también rotulado Internet/WAN) del router WiFi (FAQ Ecolan).\n"
                "3) Reiniciar: desenchufar inyector PoE y router 30s. Enchufar primero el inyector, "
                "   esperar ~1 min a que el CPE enganche señal, luego el router.\n"
                "4) LED del CPE: enlace/señal fijo = OK; parpadeo rápido o rojo = sin enlace.\n"
                "5) Línea de vista: ¿crecieron árboles o hay construcción entre antena y torre?\n"
                "6) Probar cable vs WiFi en un dispositivo.\n"
                "7) ¿Vecinos de la misma torre con problemas? → falla zonal.\n"
                "Escalar a N2 con: dirección, torre, síntoma, zonal o individual.\n"
                "Soporte: 0223 464-3006."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Internet radio — señal intermitente",
            categoria="Internet",
            contenido=(
                "Cuando la conexión BAI/radio se cae y vuelve periódicamente:\n"
                "1) Puede ser interferencia en la banda (suele ser 5 GHz).\n"
                "2) Verificar que el CPE no se mueva con el viento (soporte flojo).\n"
                "3) Luego de lluvia/tormenta, puede haber humedad en conectores.\n"
                "4) Si parece cíclico (siempre a la misma hora), puede ser saturación de la torre.\n"
                "Escalar a N2 indicando horarios del problema y si es zonal."
            ),
        ),

        # ==================== INTERNET ADSL ====================
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Internet ADSL — sin servicio",
            categoria="Internet",
            contenido=(
                "Cooperativa Batán / Ecolan — Internet ADSL/xDSL por par de cobre (línea telefónica).\n\n"
                "Diagnóstico N1:\n"
                "1) Reiniciar módem ADSL 30s. Esperar ~2 min a sincronización (luz DSL/Sync fija).\n"
                "2) Luces: DSL fija = sincronización OK. Si parpadea → no sincroniza con DSLAM.\n"
                "3) Filtro/Splitter: todos los aparatos telefónicos (teléfonos, alarmas, fax) "
                "   DEBEN tener filtro ADSL. El módem se conecta al puerto sin filtro del splitter.\n"
                "4) Probar en la primera toma (la que viene de la calle), sin extensiones ni "
                "   cables internos largos.\n"
                "5) Cable vs WiFi: si por cable anda, es tema WiFi.\n"
                "6) Si no sincroniza → posible falla en par de cobre o en el DSLAM.\n"
                "Escalar a N2 con: dirección, N° de línea telefónica, estado de luces.\n"
                "Soporte: 0223 464-3006. Ver también FAQ Ecolan (Conectar Modem ADSL)."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Internet ADSL — desconexiones frecuentes",
            categoria="Internet",
            contenido=(
                "ADSL se desconecta y reconecta (la luz DSL parpadea):\n"
                "1) Verificar filtros en TODOS los aparatos. Un teléfono sin filtro causa ruido.\n"
                "2) Cable telefónico interno en mal estado o muy largo genera atenuación.\n"
                "3) Humedad en la caja de distribución de la calle (poste o fachada).\n"
                "4) Si hay tormenta eléctrica reciente, el par puede haberse dañado.\n"
                "5) Verificar si el tono del teléfono fijo tiene ruido/estática → indica par malo.\n"
                "Escalar a N2 con: frecuencia de las caídas, si hay ruido en línea."
            ),
        ),

        # ==================== INTERNET GENÉRICO ====================
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Internet — sin servicio (genérico)",
            categoria="Internet",
            contenido=(
                "Cuando el abonado dice 'no tengo internet' sin especificar tipo:\n"
                "1) Preguntar qué tipo de conexión tiene:\n"
                "   - Fibra (cable amarillo a cajita blanca) → playbook FTTH\n"
                "   - Radio/antena en el techo (BAI) → playbook Radio\n"
                "   - Línea telefónica/módem ADSL → playbook ADSL\n"
                "2) Si no sabe: preguntar si tiene antena en el techo (BAI), cable "
                "   amarillo finito (fibra), o si es por la línea del teléfono (ADSL).\n"
                "3) Siempre verificar primero si hay deuda/corte antes del diagnóstico técnico.\n"
                "4) Reclamos y autogestión: https://ov.batan.coop (Mi Cuenta)."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Internet lento — diagnóstico general",
            categoria="Internet",
            contenido=(
                "Cuando reportan lentitud (FAQ Ecolan):\n"
                "1) Pedir test por cable (no WiFi): fast.com o medidor de velocidad Ecolan.\n"
                "2) La velocidad contratada es la de descarga; >70% del plan suele ser aceptable.\n"
                "3) Si por cable da bien y WiFi no → problema WiFi, no de línea.\n"
                "4) Verificar cuántos dispositivos conectados y qué hacen.\n"
                "5) En PCs Windows, una actualización descargándose es causa frecuente de lentitud.\n"
                "6) En horarios pico puede haber congestión (sobre todo en BAI/radio).\n"
                "7) Si por cable da <50% del plan → escalar N2 indicando plan y resultado."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Internet — cortes o intermitencia",
            categoria="Internet",
            contenido=(
                "Cuando el servicio se cae y vuelve (no es un corte total):\n"
                "1) Consultar incidente masivo de zona antes de pedir pruebas.\n"
                "2) ¿Afecta a uno, varios o todos los dispositivos?\n"
                "3) ¿Ocurre por WiFi, por cable o por ambos? Si solo WiFi y el cable anda → playbook WiFi.\n"
                "4) Frecuencia: cada cuánto se corta y cuánto tarda en volver.\n"
                "5) Luces durante el corte: ¿cambia PON/LOS/DSL/WAN?\n"
                "6) Si no hay alarma física ni incidente: reinicio controlado y prueba de estabilidad.\n"
                "7) Si sigue inestable → N2 con frecuencia, luces y acciones N1. "
                "No repetir el diagnóstico ya hecho.\n"
                "Playbook: internet_intermitente."
            ),
        ),

        # ==================== WIFI ====================
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="WiFi — cobertura y rendimiento",
            categoria="Internet",
            contenido=(
                "Problemas de WiFi (red del hogar, no necesariamente de la línea):\n"
                "1) El WiFi pierde señal con cada pared (especialmente hormigón/ladrillo).\n"
                "2) Router en el centro de la casa = mejor cobertura.\n"
                "3) Banda 2.4 GHz: más alcance, menos velocidad. 5 GHz: menos alcance, más velocidad.\n"
                "4) Interferencia: microondas, teléfonos inalámbricos, vecinos en mismo canal.\n"
                "5) Clave olvidada: resetear el módem/router y usar nombre/clave de la etiqueta "
                "   debajo del equipo (datos de fábrica).\n"
                "6) Recomendación Ecolan BAI: cablear PCs, Smart TV y consolas a puertos LAN; "
                "   dejar WiFi para celulares/tablets.\n"
                "7) Si muchas habitaciones sin señal → sugerir access point o mesh (comercial).\n"
                "La cooperativa puede ofrecer instalación de extensores (consultar comercial)."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="WiFi — cambiar clave o nombre de red",
            categoria="Internet",
            contenido=(
                "Cambio de contraseña o SSID (no es falla de cobertura):\n"
                "1) Confirmar si quieren cambiar clave, nombre de red o ambos.\n"
                "2) Acceso: etiqueta de fábrica debajo del módem/router, o gestión remota autorizada. "
                "   Nunca pedir ni registrar la clave actual en el chat.\n"
                "3) Usar el flujo del modelo; no improvisar parámetros.\n"
                "4) Avisar que todos los dispositivos deberán reconectarse.\n"
                "5) Validar con un dispositivo. Si no hay acceso al equipo → derivar N2.\n"
                "Playbook: cambio_clave_wifi."
            ),
        ),

        # ==================== TELEFONÍA FIJA ====================
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Telefonía fija — sin tono o falla",
            categoria="Telefonía",
            contenido=(
                "Cooperativa Batán / Ecolan — telefonía fija.\n\n"
                "Diagnóstico N1:\n"
                "1) ¿Hay tono al descolgar?\n"
                "2) ¿Falla en todos los aparatos o solo en uno? Si solo uno → probar otro teléfono "
                "   en la misma toma (descarta aparato defectuoso).\n"
                "3) Cable bien enchufado en la toma de pared.\n"
                "4) ¿Hay ruido o estática? Puede indicar par de cobre deteriorado.\n"
                "5) Si en la misma línea hay internet ADSL: no quitar splitter/filtros; "
                "   un teléfono sin filtro genera ruido y caídas de ADSL.\n"
                "6) Si no hay tono en ningún aparato y el cableado está OK → falla de planta/central.\n"
                "Escalar a N2 con: N° de línea, tono sí/no, ruido, si es un aparato o todos, "
                "dirección. Soporte: 0223 464-3006."
            ),
        ),

        # ==================== MÓVIL IMOWI ====================
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="IMOWI — sin señal o sin servicio",
            categoria="Móvil",
            contenido=(
                "Cooperativa Batán — servicio móvil IMOWI (MVNO). Cobertura 4G nacional.\n\n"
                "Diagnóstico N1:\n"
                "1) Reiniciar el teléfono.\n"
                "2) Modo avión 15s y desactivar → fuerza re-registro en la red.\n"
                "3) Selección de red manual: Ajustes > Redes móviles > Operador > elegir otra red "
                "   (Personal/Claro), esperar registro, volver a IMOWI.\n"
                "4) Verificar que la SIM esté bien insertada (sacar y poner).\n"
                "5) Probar la SIM en otro teléfono para descartar problema del equipo.\n"
                "6) Si en otra ubicación anda → zona sin cobertura.\n"
                "Escalar a N2 con: MSISDN, ubicación, si es solo señal o también datos.\n"
                "Contacto: WhatsApp 0223 4643010 · 464-3000 · oficina comercial."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="IMOWI — sin datos móviles",
            categoria="Móvil",
            contenido=(
                "Cuando hay señal (llamadas funcionan) pero no navega "
                "(FAQ imowi.com.ar + canales Batán):\n"
                "1) Verificar que datos móviles estén activados y modo avión apagado.\n"
                "2) APN: según el sistema del abonado. Si YA dijo Android, "
                "   NUNCA des pasos de iPhone.\n"
                "   Android: Nombre = imowi · APN = apn1.catel.org.ar "
                "   (resto en blanco). Ajustes > Conexiones/Redes móviles > APN > Nuevo.\n"
                "   iPhone: iPhone 11+ o eSIM → APN automático. "
                "   Modelos anteriores: Configuración > Datos celulares > Opciones > "
                "   Red de datos celulares → Punto de acceso internet = apn1.catel.org.ar · "
                "   Nombre de usuario = imowi.\n"
                "3) Sin datos del abono (FAQ): sigue WhatsApp mensajería (textos/audios/fotos/"
                "   videos) y páginas educativas; para el resto hay que comprar un bono.\n"
                "4) Bonos: Autogestión Batán https://ov.batan.coop u oficina Cooperativa Batán. "
                "   NO orientar a la autogestión de imowi.com.ar (es de otra cooperativa).\n"
                "5) Apagar WiFi del celular y probar solo datos.\n"
                "6) Si persiste → escalar N2 con MSISDN y si la señal está OK."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="IMOWI — llamadas y SMS",
            categoria="Móvil",
            contenido=(
                "Problemas con llamadas o mensajes de texto (FAQ imowi):\n"
                "1) Si no puede hacer llamadas: reiniciar, modo avión, selección manual de red.\n"
                "2) Si no recibe llamadas: verificar desvíos activos (*#21# para consultar).\n"
                "3) Si las llamadas se cortan: probable zona de baja señal.\n"
                "4) El plan incluye 1000 SMS a numeración de cliente nacional; "
                "   NO incluye números cortos (bancos/apps) → ver artículo A2P.\n"
                "5) Correo de voz: marcar *333 desde la línea imowi.\n"
                "6) Bloqueo de llamadas/SMS internacionales: *303 (red imowi) o canales Batán.\n"
                "7) Si nada funciona (ni llamadas ni datos) → ver artículo 'sin señal'."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="IMOWI — SMS de verificación (A2P)",
            categoria="Móvil",
            contenido=(
                "SMS A2P (Application-to-Person) de bancos, apps y validaciones:\n"
                "1) No es un SMS persona-a-persona; depende de acuerdos del remitente con la red.\n"
                "2) El plan imowi de 1000 SMS es solo a numeración de cliente; "
                "   no incluye números cortos de verificación.\n"
                "3) N1: sugerir validar por otro medio (email, llamada, WhatsApp del banco/app).\n"
                "4) Confirmar que la línea tiene señal y puede enviar/recibir SMS normales.\n"
                "5) Pedir nombre de la app/banco y el número corto del remitente para el ticket.\n"
                "6) No prometer plazo corto de habilitación A2P; si es crítico, escalar a N2.\n"
                "Escalar con: MSISDN, app/entidad, número corto, fecha/hora del intento."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="IMOWI — robo o pérdida de celular",
            categoria="Móvil",
            contenido=(
                "Robo o pérdida del equipo IMOWI (FAQ imowi.com.ar):\n"
                "1) Desde línea de otra compañía: *910 (opción 4 – imowi) para interrumpir.\n"
                "2) Desde línea imowi: *303.\n"
                "3) Desde línea fija: 0800-147-0303.\n"
                "4) También canales Batán: WhatsApp 0223 4643010 · 464-3000 · oficina.\n"
                "5) El operador indica pasos para reposición de SIM/eSIM y rehabilitar.\n"
                "6) N1 no repone SIM sola: derivar con DNI y MSISDN.\n"
                "7) Tras nueva SIM física: APN Nombre imowi / APN apn1.catel.org.ar.\n"
                "8) Si era eSIM: pedir nuevo QR por *303 o en oficina Batán."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="IMOWI — portabilidad numérica",
            categoria="Móvil",
            contenido=(
                "Portabilidad de número a IMOWI (canales Batán; FAQ imowi):\n"
                "1) Inicio en Batán: WhatsApp 0223 4643010, 464-3000 u oficina comercial "
                "   (DNI, equipo liberado, titular ≥18 años).\n"
                "2) El trámite dura entre 24 y 72 horas hábiles (batan.coop/imowi).\n"
                "3) Durante la portabilidad puede haber un corte breve del servicio.\n"
                "4) Si pasaron más de 72 hs hábiles y no se completó → escalar a N2.\n"
                "5) Para portar DESDE IMOWI a otro operador, se gestiona con el nuevo operador.\n"
                "6) Chip/SIM: retirar en oficina comercial Batán.\n"
                "Cobertura: el servicio móvil imowi cubre el territorio argentino; "
                "Batán (Gral. Pueyrredón, CP 7601) es localidad de comercialización."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="IMOWI — activar SIM / eSIM",
            categoria="Móvil",
            contenido=(
                "Activación SIM/eSIM (FAQ imowi.com.ar):\n\n"
                "SIM física:\n"
                "1) Insertar, reiniciar, esperar ~5 min a registro automático.\n"
                "2) Si no navega: configurar APN (Android Nombre imowi / APN apn1.catel.org.ar).\n\n"
                "Compatibilidad eSIM: marcar *#06# — si aparece EID, el equipo soporta eSIM.\n"
                "Requisitos: WiFi + QR enviado por e-mail (o reenviado desde oficina/*303).\n"
                "Android: Ajustes > Conexiones > Administrador SIM > Añadir eSIM > escanear QR.\n"
                "iPhone: cámara sobre el QR → Añadir plan, o Configuración > Red celular > "
                "Agregar eSIM.\n"
                "Notas:\n"
                "- La eSIM se activa en un solo dispositivo a la vez (seguridad).\n"
                "- El mismo QR puede usarse hasta 5 veces si se da de baja en el equipo anterior.\n"
                "- Si se pierde el QR → *303 o oficina Batán para reenviar.\n"
                "iPhone 11+ / eSIM: APN suele ser automático.\n"
                "Escalar si no completa tras reiniciar y esperar."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="IMOWI — FAQ operativa N1",
            categoria="Móvil",
            contenido=(
                "Resumen operativo desde FAQ imowi.com.ar (usar canales Batán para gestión):\n\n"
                "Autogestión: en Batán usar https://ov.batan.coop u oficina/WhatsApp Batán. "
                "NO redirigir a imowi.com.ar/autogestion (pertenece a otra cooperativa).\n\n"
                "Alta / primera factura: se prorratean GB, minutos, SMS y el monto según "
                "días restantes del mes calendario. Alta el día 1 = cuota completa.\n\n"
                "Plan base típico: datos contratados + 1000 min voz nacional + 1000 SMS "
                "a numeración de cliente + WhatsApp libre. Llamadas/SMS internacionales "
                "se facturan como excedente; se pueden bloquear vía *303 o Batán.\n\n"
                "Sin datos: WhatsApp mensajería sigue; resto requiere bono "
                "(eventual por días o recurrente hasta fin de mes / renovable).\n\n"
                "imowi no vende celulares; cualquier equipo homologado para Argentina sirve.\n\n"
                "Correo de voz: *333.\n"
                "Atención red imowi: *303 · 0800-147-0303 (24 hs).\n"
                "Atención Batán IMOWI: WhatsApp 0223 4643010 · 464-3000 · oficina.\n\n"
                "Baja / arrepentimiento: solo titular; mínimo 10 días corridos desde "
                "activación; implica pérdida del número; contactan en 48 hs. "
                "Puede emitirse factura según ciclo. Gestionar en Batán (no formulario genérico "
                "de imowi.com.ar salvo que comercial lo indique)."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="IMOWI — baja o arrepentimiento",
            categoria="Móvil",
            contenido=(
                "Baja de línea IMOWI / derecho de arrepentimiento (FAQ imowi):\n"
                "1) Solo el titular puede solicitarla.\n"
                "2) Deben haber pasado al menos 10 días corridos desde la activación.\n"
                "3) Implica pérdida del número y beneficios del plan.\n"
                "4) Contactan dentro de 48 hs para confirmar; si no logran contacto, "
                "   pueden procesar la baja igual.\n"
                "5) Según el ciclo de facturación, puede emitir factura posterior a la baja.\n"
                "N1: no procesar la baja en el bot — derivar a comercial/agente Batán "
                "con MSISDN y DNI del titular. Canales: WhatsApp 0223 4643010 · 464-3000 · oficina."
            ),
        ),

        # ==================== FACTURACIÓN ====================
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Facturación — medios de pago",
            categoria="Facturación",
            contenido=(
                "Medios de pago Cooperativa Batán:\n"
                "1) QR Fiserv de la factura (Mercado Pago, MODO, etc.).\n"
                "2) Rapipago y Pago Fácil (código de barras de la boleta).\n"
                "3) Transferencia bancaria al CBU de la Cooperativa (consultar en oficina).\n"
                "4) Débito automático (tramitar en oficina con CBU o tarjeta).\n"
                "5) Autogestión / Mi Cuenta: https://ov.batan.coop\n"
                "6) Atención: 0223 464-3006 · WhatsApp comercial IMOWI 0223 4643010 · 464-3000.\n"
                "Acreditación: el tiempo de imputación varía según el medio. "
                "No inventar montos ni CBU en el chat."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Corte por deuda — rehabilitación automática",
            categoria="Facturación",
            contenido=(
                "Cuando el abonado tiene estado corte/suspendido (FAQ Ecolan):\n"
                "1) Informar medios de pago (QR Fiserv, boleta, Mi Cuenta ov.batan.coop).\n"
                "2) NO es necesario avisar que pagó: la rehabilitación es AUTOMÁTICA "
                "   cuando ingresa el pago al sistema.\n"
                "3) El tiempo de imputación depende del medio de pago.\n"
                "4) Si pagó luego del vencimiento, la próxima factura puede incluir intereses "
                "   y cargo de reconexión.\n"
                "5) NO intentar diagnóstico técnico si el servicio está cortado por deuda.\n"
                "6) Si pagó hace varias horas y sigue cortado → escalar a N2."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Facturación — reclamo de monto",
            categoria="Facturación",
            contenido=(
                "Si el abonado no reconoce un monto en la factura:\n"
                "1) Verificar si hubo cambio de plan, cargo por instalación, mora o reconexión.\n"
                "2) Si es un cargo que no se puede explicar en N1 → derivar a agente con "
                "   acceso al sistema de facturación.\n"
                "3) Siempre ser empático: 'Entiendo la preocupación, vamos a revisarlo'."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Facturación — descargar factura o talón",
            categoria="Facturación",
            contenido=(
                "Descarga de factura, boleta o talón/cupón:\n"
                "1) Confirmar si necesita factura, boleta o talón para pagar.\n"
                "2) Pedir período si hay varios.\n"
                "3) Autogestión: https://ov.batan.coop — no inventar adjuntos en el chat.\n"
                "4) Si no puede autenticarse → pedir DNI/N.º de socio y derivar.\n"
                "Playbook: facturacion_descarga."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Facturación — informar un pago",
            categoria="Facturación",
            contenido=(
                "Si el abonado quiere avisar que pagó:\n"
                "1) NO es necesario avisar: la imputación y la rehabilitación son automáticas.\n"
                "2) No afirmar acreditación sin consultar el sistema.\n"
                "3) Aviso opcional en Mi Cuenta ov.batan.coop.\n"
                "4) Si pagó hace varias horas y no figura → derivar N2 con medio y fecha.\n"
                "Playbook: facturacion_informar_pago."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Facturación — estado de cuenta",
            categoria="Facturación",
            contenido=(
                "Consulta de saldo, vencimiento o estado de factura:\n"
                "1) Mostrar solo el dato del padrón/BillTrack; no inventar montos.\n"
                "2) Identificado: usar deuda_monto. Invitado: pedir DNI.\n"
                "3) Si disputa el saldo → playbook facturacion_reclamo / derivar.\n"
                "Playbook: facturacion_estado_cuenta."
            ),
        ),

        # ==================== TV OTT SENSA ====================
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="TV OTT Sensa — sin reproducción o no abre",
            categoria="TV",
            contenido=(
                "Cooperativa Batán — Sensa es el servicio de TV por internet (OTT / app / "
                "Android TV Box). Depende de una conexión a internet estable.\n\n"
                "Diagnóstico N1:\n"
                "1) Triaje: ¿app/web Sensa o decodificador / Android TV Box de la cooperativa?\n"
                "2) Confirmar internet en el mismo dispositivo. Si no hay internet → "
                "   flujo de internet antes de seguir con Sensa.\n"
                "3) Registrar dispositivo: Smart TV, celular/tablet, PC/notebook o Android TV Box.\n"
                "4) ¿Navega internet en ese equipo? Si no → WiFi/cable/router.\n"
                "5) ¿Abre la app/web de Sensa? Si no → reinstalar, actualizar SO, compatibilidad.\n"
                "6) Síntoma al ver contenido:\n"
                "   - No reproduce: velocidad (>5 Mbps orientativo), otro dispositivo u otra red.\n"
                "   - Buffering: estabilidad WiFi + speed test; si baja → internet lento.\n"
                "   - Error de cuenta: credenciales / habilitación CRM (agente; N1 no inventa estado).\n"
                "   - Calidad baja: cable si es posible, otros equipos saturando.\n"
                "7) Acciones: reiniciar router/ONT y dispositivo, actualizar Sensa.\n"
                "Escalar con: dispositivo, error, velocidad, usuario, fecha/hora."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="TV OTT Sensa — requisitos y escalamiento",
            categoria="TV",
            contenido=(
                "Sensa corre sobre la conexión del abonado (WiFi o cable al router).\n"
                "- Velocidad orientativa mínima para reproducción estable: ~5 Mbps "
                "  (más si hay varios streams en paralelo).\n"
                "- Si el equipo cumple requisitos, hay internet OK y el síntoma sigue → N2.\n"
                "- Alta/baja de Sensa, packs premium (HBO, Universal, etc.) o autorización "
                "  de dispositivos → derivar a comercial/CRM (no resolver solo con el bot).\n"
                "Grilla y packs: consultar batan.coop (sección Televisión)."
            ),
        ),

        # ==================== GENERAL ====================
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Cooperativa Batán — información general",
            categoria="General",
            contenido=(
                "Cooperativa de Provisión de Servicios Telefónicos y Otros Batán Ltda.\n"
                "Servicios:\n"
                "- Internet Ecolan: FTTH (fibra), BAI (banda ancha inalámbrica), ADSL.\n"
                "- Telefonía fija Ecolan/Batán.\n"
                "- Telefonía móvil y datos: IMOWI.\n"
                "- TV: Sensa (OTT / Android TV) y packs premium.\n"
                "- B2B Ecolan: conectividad empresarial, datacenter, housing/hosting.\n\n"
                "Autogestión / Mi Cuenta: https://ov.batan.coop\n"
                "Webs: https://batan.coop · https://ecolan.com · https://batan.coop/imowi\n"
                "Soporte técnico: 0223 464-3006\n"
                "Horario soporte Ecolan: Lunes a Viernes 8 a 21 hs · Sábados 9 a 14 hs.\n"
                "IMOWI WhatsApp: 0223 4643010 · Central: 464-3000\n"
                "Fuera de horario: los reclamos no urgentes se atienden el siguiente día hábil "
                "salvo corte masivo."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Planes internet Ecolan — vigentes",
            categoria="Comercial",
            contenido=(
                "Planes internet Ecolan (tiers orientativos; confirmar precios y promo en "
                "ecolan.com — N1 no cotiza montos):\n"
                "FTTH (fibra): 100M, 200M, 300M, 600M (simétricos según plan publicado).\n"
                "BAI (banda ancha inalámbrica): 10M, 15M, 25M.\n"
                "ADSL: 10M (según distancia a central).\n"
                "Disponibilidad según zona y tecnología.\n"
                "Para contratar o cambiar → derivar a comercial (agente) o consultar ecolan.com."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Planes IMOWI móvil — vigentes",
            categoria="Comercial",
            contenido=(
                "Planes IMOWI (tiers según imowi.com.ar / batan.coop/imowi; "
                "confirmar precios en web u oficina — N1 no cotiza montos):\n"
                "- 1,5GB · 3GB · 5GB · 8GB · 15GB · 25GB de datos.\n"
                "- Incluyen: 1000 minutos nacionales, 1000 SMS a numeración de cliente "
                "  (no números cortos), WhatsApp libre, cobertura 4G nacional.\n"
                "- Llamadas/SMS internacionales: excedente (se pueden bloquear).\n"
                "- Bonos adicionales (eventuales por días o recurrentes) desde "
                "  Autogestión Batán https://ov.batan.coop u oficina — "
                "  NO imowi.com.ar/autogestion.\n"
                "Portabilidad: 24–72 hs hábiles (WhatsApp 0223 4643010 / 464-3000 / oficina).\n"
                "Primera factura / alta a mitad de mes: prorrateo de GB, minutos, SMS y monto.\n"
                "Para contratar → oficina comercial Batán con DNI."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Escalamiento a N2 — cuándo y cómo",
            categoria="Procedimiento",
            contenido=(
                "Derivar a agente humano (N2) cuando:\n"
                "1) El playbook N1 se agotó sin solución.\n"
                "2) El abonado pide explícitamente hablar con una persona.\n"
                "3) Problema fuera de alcance del bot (falla masiva, CRM, reclamo comercial).\n"
                "4) Se necesita acceso a sistemas internos (facturación, HLR, NMS).\n"
                "5) Robo/pérdida (*910) con reposición de SIM, portabilidad trabada, packs TV.\n\n"
                "Al escalar incluir: servicio afectado, pasos N1 hechos, dirección (si aplica), "
                "teléfono de contacto, resumen del síntoma."
            ),
        ),
    ]


def seed_kb_batan_servicios(db: Session) -> dict:
    """Asegura artículos KB Batán (idempotente por título) y refresca contenido canónico.

    También corrige el typo histórico IMOVI → IMOWI en títulos/contenido ya seedados
    y el APN Batán incorrecto internet.coopbatan.ar → apn1.catel.org.ar.
    """
    batan = _org(db, "coop-batan")
    if not batan:
        return {"seeded": False, "articulos": 0}

    fixed = 0
    for art in db.scalars(
        select(KnowledgeArticle).where(KnowledgeArticle.organizacion_id == batan.id)
    ).all():
        new_titulo = (art.titulo or "").replace("IMOVI", "IMOWI")
        new_contenido = (
            (art.contenido or "")
            .replace("IMOVI", "IMOWI")
            .replace("internet.coopbatan.ar", "apn1.catel.org.ar")
        )
        if new_titulo != (art.titulo or "") or new_contenido != (art.contenido or ""):
            art.titulo = new_titulo
            art.contenido = new_contenido
            fixed += 1

    # Playbooks / config admin guardados con el APN viejo
    from app.estate.models import PlatformConfig

    cfg = db.get(PlatformConfig, "default")
    if cfg and cfg.payload_json and "internet.coopbatan.ar" in cfg.payload_json:
        cfg.payload_json = cfg.payload_json.replace(
            "internet.coopbatan.ar", "apn1.catel.org.ar"
        )
        fixed += 1

    # Líneas demo JSC con APN viejo
    from app.estate.models import LineaJSC

    for linea in db.scalars(
        select(LineaJSC).where(LineaJSC.organizacion_id == batan.id)
    ).all():
        if (linea.apn or "") == "internet.coopbatan.ar":
            linea.apn = "apn1.catel.org.ar"
            fixed += 1

    if fixed:
        db.commit()

    canon = {a.titulo: a for a in _articulos_kb_batan(batan.id)}
    existentes = {
        a.titulo: a
        for a in db.scalars(
            select(KnowledgeArticle).where(KnowledgeArticle.organizacion_id == batan.id)
        ).all()
    }

    updated = 0
    for titulo, plantilla in canon.items():
        actual = existentes.get(titulo)
        if not actual:
            continue
        if (actual.contenido or "") != (plantilla.contenido or "") or (
            actual.categoria or ""
        ) != (plantilla.categoria or ""):
            actual.contenido = plantilla.contenido
            actual.categoria = plantilla.categoria
            updated += 1

    nuevos = [a for titulo, a in canon.items() if titulo not in existentes]
    if updated or nuevos:
        if nuevos:
            db.add_all(nuevos)
        db.commit()

    if not nuevos and not fixed and not updated:
        return {
            "seeded": False,
            "articulos": len(existentes),
            "fixed_imowi": 0,
            "updated": 0,
        }
    return {
        "seeded": bool(nuevos or updated),
        "articulos": len(nuevos),
        "fixed_imowi": fixed,
        "updated": updated,
    }


def seed_inbox_conversaciones(db: Session) -> dict:
    """Hilos WhatsApp abiertos para operar la bandeja sin Meta (solo 1ª vez).

    No recrea demos si ya hubo conversaciones (aunque estén cerradas): así un restart/
    redeploy no vuelve a llenar la bandeja después de que el equipo las cerró.
    En production tampoco seedea demos de bandeja.
    """
    import json

    from app.config import es_produccion
    from app.estate.models import ConversacionCanal, MensajeCanal

    if es_produccion():
        return {"seeded": False, "conversaciones": 0, "reason": "production"}

    batan = _org(db, "coop-batan")
    if not batan:
        return {"seeded": False, "conversaciones": 0}

    existentes = db.scalar(
        select(func.count())
        .select_from(ConversacionCanal)
        .where(ConversacionCanal.organizacion_id == batan.id)
    )
    if existentes and existentes > 0:
        return {"seeded": False, "conversaciones": int(existentes), "reason": "ya_existen"}

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
                    "Tu cuenta figura con estado «corte» y saldo pendiente 2.800,00 pesos. "
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
