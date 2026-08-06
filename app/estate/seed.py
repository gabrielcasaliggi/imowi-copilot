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
                "   Si LOS está en rojo → corte de fibra en algún punto del tramo.\n"
                "3) Cable de fibra: verificar que no esté doblado, aplastado por muebles ni "
                "   desenchufado del conector SC/APC (verde) en la ONT.\n"
                "4) Probar cable vs WiFi: si por cable al router anda, el problema es WiFi.\n"
                "5) Si nada de lo anterior resuelve → N2 (posible corte de fibra en la acometida "
                "   o falla en el splitter/OLT de la central). Registrar dirección y síntoma."
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
                "Cooperativa Batán — Internet inalámbrico por radio (enlace punto-multipunto). "
                "El abonado tiene un CPE/antena en el techo apuntando a una torre de la cooperativa, "
                "alimentado por PoE (inyector de corriente conectado al tomacorriente).\n\n"
                "Diagnóstico N1:\n"
                "1) Reiniciar: desenchufar el inyector PoE del CPE y el router 30s. Enchufar "
                "   primero el inyector, esperar 1 min a que el CPE enganche señal, luego el router.\n"
                "2) LED del CPE: enlace/señal fijo = OK; parpadeo rápido o rojo = sin enlace.\n"
                "3) Línea de vista: ¿crecieron árboles? ¿hay construcción nueva entre la antena "
                "   y la torre? Obstáculos generan pérdida de señal.\n"
                "4) Inyector PoE: ¿tiene luz encendida? Si no, verificar enchufe y fusible.\n"
                "5) Probar cable vs WiFi.\n"
                "6) Consultar si vecinos de la misma torre tienen problemas → probable falla zonal.\n"
                "Escalar a N2 con: dirección, torre a la que apunta, síntoma, si es zonal o individual."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Internet radio — señal intermitente",
            categoria="Internet",
            contenido=(
                "Cuando la conexión por radio se cae y vuelve periódicamente:\n"
                "1) Puede ser interferencia en la banda (5GHz generalmente). Ocurre más en "
                "   zonas con muchos equipos inalámbricos.\n"
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
                "Cooperativa Batán — Internet ADSL por par de cobre (línea telefónica).\n\n"
                "Diagnóstico N1:\n"
                "1) Reiniciar módem ADSL 30s. Esperar ~2 min a sincronización (luz DSL/Sync fija).\n"
                "2) Luces: DSL fija = sincronización OK. Si parpadea → no sincroniza con DSLAM.\n"
                "3) Filtro/Splitter: todos los aparatos telefónicos (teléfonos, alarmas, fax) "
                "   DEBEN tener filtro ADSL. El módem se conecta al puerto sin filtro del splitter.\n"
                "4) Probar en la primera toma (la que viene de la calle), sin extensiones ni "
                "   cables internos largos.\n"
                "5) Cable vs WiFi: si por cable anda, es tema WiFi.\n"
                "6) Si no sincroniza → posible falla en par de cobre o en el DSLAM de la central.\n"
                "Escalar a N2 con: dirección, N° de línea telefónica, estado de luces."
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
                "   - Radio/antena en el techo → playbook Radio\n"
                "   - Línea telefónica/módem ADSL → playbook ADSL\n"
                "2) Si no sabe: preguntar si tiene antena en el techo (radio), cable "
                "   amarillo finito (fibra), o si es por la línea del teléfono (ADSL).\n"
                "3) Siempre verificar primero si hay deuda/corte antes del diagnóstico técnico."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Internet lento — diagnóstico general",
            categoria="Internet",
            contenido=(
                "Cuando reportan lentitud:\n"
                "1) Pedir test por cable (no WiFi): fast.com o speedtest.net.\n"
                "2) Si da >70% del plan contratado, es aceptable.\n"
                "3) Si por cable da bien y WiFi no → problema WiFi, no de línea.\n"
                "4) Verificar cuántos dispositivos conectados y qué hacen.\n"
                "5) En horarios pico puede haber congestión (sobre todo en radio).\n"
                "6) Si por cable da <50% del plan → escalar N2 indicando plan y resultado."
            ),
        ),

        # ==================== WIFI ====================
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="WiFi — cobertura y rendimiento",
            categoria="Internet",
            contenido=(
                "Problemas de WiFi (no es un problema de internet, es de la red del hogar):\n"
                "1) El WiFi pierde señal con cada pared (especialmente hormigón/ladrillo).\n"
                "2) Router en el centro de la casa = mejor cobertura.\n"
                "3) Banda 2.4GHz: más alcance, menos velocidad. 5GHz: menos alcance, más velocidad.\n"
                "4) Interferencia: microondas, teléfonos inalámbricos, vecinos en mismo canal.\n"
                "5) Solución: reiniciar router, cambiar canal WiFi, agregar extensor/mesh.\n"
                "6) Si muchas habitaciones sin señal → sugerir access point o mesh.\n"
                "La cooperativa puede ofrecer servicio de instalación de extensores (consultar área comercial)."
            ),
        ),

        # ==================== MÓVIL IMOWI ====================
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="IMOWI — sin señal o sin servicio",
            categoria="Móvil",
            contenido=(
                "Cooperativa Batán — servicio móvil IMOWI (MVNO).\n\n"
                "Diagnóstico N1:\n"
                "1) Reiniciar el teléfono.\n"
                "2) Modo avión 15s y desactivar → fuerza re-registro en la red.\n"
                "3) Selección de red manual: Ajustes > Redes móviles > Operador > elegir otra red "
                "   (Personal/Claro), esperar registro, volver a IMOWI. Genera nuevo registro.\n"
                "4) Verificar que la SIM esté bien insertada (sacar y poner).\n"
                "5) Probar la SIM en otro teléfono para descartar problema del equipo.\n"
                "6) Si en otra ubicación anda → zona sin cobertura.\n"
                "Escalar a N2 con: MSISDN (número de línea), ubicación, si es solo señal o también datos."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="IMOWI — sin datos móviles",
            categoria="Móvil",
            contenido=(
                "Cuando hay señal (llamadas funcionan) pero no navega:\n"
                "1) Verificar que datos móviles estén activados.\n"
                "2) Verificar APN: nombre=internet.coopbatan.ar, MCC=722, MNC=310. "
                "   En Android: Ajustes > Redes móviles > Nombres de punto de acceso.\n"
                "   En iPhone: Ajustes > Datos móviles > Red de datos móviles.\n"
                "3) Verificar que no haya un límite de datos alcanzado.\n"
                "4) Reiniciar configuración de red (borra WiFi guardadas pero resuelve APN).\n"
                "5) Si persiste → escalar N2 indicando MSISDN y si la señal está OK."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="IMOWI — llamadas y SMS",
            categoria="Móvil",
            contenido=(
                "Problemas con llamadas o mensajes de texto:\n"
                "1) Si no puede hacer llamadas: reiniciar, modo avión, selección manual de red.\n"
                "2) Si no recibe llamadas: verificar desvíos activos (*#21# para consultar).\n"
                "3) Si las llamadas se cortan: probable zona de baja señal.\n"
                "4) SMS de verificación que no llegan (A2P): son mensajes de apps/bancos. "
                "   Estos dependen de acuerdos con las plataformas y pueden no llegar. "
                "   Sugerir validar por otro medio (email, llamada). Si es crítico, escalar.\n"
                "5) Si nada funciona (ni llamadas ni datos) → ver artículo 'sin señal'."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="IMOWI — portabilidad numérica",
            categoria="Móvil",
            contenido=(
                "Portabilidad de número a IMOWI:\n"
                "1) Se solicita en oficina comercial con DNI y última factura del operador anterior.\n"
                "2) El proceso tarda entre 3 y 5 días hábiles.\n"
                "3) Durante la portabilidad puede haber un corte breve del servicio.\n"
                "4) Si pasaron más de 5 días y no se completó → escalar a N2 con el número y DNI.\n"
                "5) Para portar DESDE IMOWI a otro operador, se gestiona con el nuevo operador."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="IMOWI — activar SIM / eSIM",
            categoria="Móvil",
            contenido=(
                "Activación de SIM/eSIM nueva:\n"
                "1) SIM física: insertar, reiniciar teléfono, esperar 5 min a registro automático.\n"
                "2) eSIM: escanear QR proporcionado en oficina. Verificar perfil activo en "
                "   Ajustes > Datos móviles > Planes de datos.\n"
                "3) Si no se activa en 30 min → verificar EID/ICCID con el agente.\n"
                "4) Configurar APN manualmente si los datos no funcionan post-activación.\n"
                "Escalar si la activación no completa tras reiniciar y esperar."
            ),
        ),

        # ==================== FACTURACIÓN ====================
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Facturación — medios de pago",
            categoria="Facturación",
            contenido=(
                "Medios de pago disponibles en Cooperativa Batán:\n"
                "1) Rapipago y Pago Fácil (con código de barras de la boleta).\n"
                "2) Transferencia bancaria al CBU de la Cooperativa (informar en oficina).\n"
                "3) Débito automático (se tramita en oficina con CBU o tarjeta).\n"
                "4) Oficina comercial: Av. Brown 1234, Batán. Lunes a viernes 8-16h.\n"
                "5) Mercado Pago: buscar 'Cooperativa Batán' (en implementación).\n"
                "Acreditación: Rapipago/PF en 24-48h, transferencia bancaria en 24h, "
                "débito automático en fecha de vencimiento."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Corte por deuda — rehabilitación automática",
            categoria="Facturación",
            contenido=(
                "Cuando el abonado tiene estado corte/suspendido:\n"
                "1) Informar el saldo pendiente y los medios de pago.\n"
                "2) La rehabilitación es AUTOMÁTICA tras acreditación del pago (no requiere "
                "   llamar ni pedir habilitación manual).\n"
                "3) Tiempo de rehabilitación: hasta 2 horas después de la acreditación.\n"
                "4) NO intentar diagnóstico técnico si el servicio está cortado por deuda.\n"
                "5) Si pagó hace más de 4 horas y sigue cortado → escalar a N2."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Facturación — reclamo de monto",
            categoria="Facturación",
            contenido=(
                "Si el abonado no reconoce un monto en la factura:\n"
                "1) Verificar si hubo cambio de plan, cargo por instalación, o mora.\n"
                "2) Si es un cargo que no se puede explicar en N1 → derivar a agente con "
                "   acceso al sistema de facturación.\n"
                "3) Siempre ser empático: 'Entiendo la preocupación, vamos a revisarlo'."
            ),
        ),

        # ==================== TV OTT SENSA ====================
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="TV OTT Sensa — sin reproducción o no abre",
            categoria="TV",
            contenido=(
                "Cooperativa Batán — Sensa es el servicio de TV por internet (OTT). "
                "Depende de una conexión a internet estable en el dispositivo.\n\n"
                "Diagnóstico N1 (checklist para Eco / agente):\n"
                "1) Confirmar internet en el mismo dispositivo. Si no hay internet → "
                "   aplicar flujo de internet antes de seguir con Sensa.\n"
                "2) Registrar dispositivo: Smart TV, celular/tablet, PC/notebook o Android TV Box.\n"
                "3) ¿Navega internet en ese equipo? Si no → WiFi/cable/router (no es falla de Sensa).\n"
                "4) ¿Abre la app/web de Sensa? Si no → reinstalar, actualizar SO, chequear "
                "   compatibilidad del equipo.\n"
                "5) Síntoma al ver contenido:\n"
                "   - No reproduce: velocidad (>5 Mbps orientativo), probar otro dispositivo "
                "     u otra red (datos 4G). Si en otra red anda → red local.\n"
                "   - Buffering infinito: estabilidad WiFi + speed test; si velocidad baja → "
                "     flujo de internet lento.\n"
                "   - Error de cuenta/usuario: credenciales, servicio habilitado (CRM — agente), "
                "     dispositivos autorizados. N1 no inventa estado de cuenta.\n"
                "   - Calidad baja / se detiene: cable si es posible, otros equipos saturando, QoS.\n"
                "6) Acciones rápidas: cerrar apps que consuman red, reiniciar router/ONT y "
                "   dispositivo, actualizar app Sensa.\n"
                "Escalar con: dispositivo, captura/error, velocidad medida, usuario afectado, "
                "fecha/hora de la falla. No afirmar habilitación en CRM sin acceso al sistema."
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
                "- Temas de alta/baja del servicio Sensa o autorización de dispositivos → "
                "  derivar a área con acceso a CRM (no resolver solo con el bot)."
            ),
        ),

        # ==================== GENERAL ====================
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Cooperativa Batán — información general",
            categoria="General",
            contenido=(
                "Cooperativa de Provisión de Servicios Telefónicos y Otros Batán Ltda.\n"
                "Servicios: Internet (FTTH, radio/wireless, ADSL), Telefonía móvil (IMOWI), "
                "TV OTT (Sensa).\n"
                "Marca internet: Ecolan.\n"
                "Planes internet: desde 25Mb hasta 300Mb según tecnología y zona.\n"
                "Planes IMOWI: desde 3GB hasta 50GB con minutos ilimitados nacionales.\n"
                "Oficina: Av. Brown 1234, Batán. Tel: 0223-XXX-XXXX.\n"
                "Horarios: Lunes a viernes 8-16h.\n"
                "Guardia técnica: fuera de horario, los reclamos se atienden al día siguiente "
                "salvo corte masivo."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Planes internet Ecolan — vigentes",
            categoria="Comercial",
            contenido=(
                "Planes internet Ecolan vigentes (precios orientativos, confirmar en oficina):\n"
                "- Ecolan 25Mb: ideal para 1-2 dispositivos, navegación y redes.\n"
                "- Ecolan 50Mb: recomendado para 3-5 dispositivos, streaming HD.\n"
                "- Ecolan 100Mb: familias con múltiples dispositivos y streaming 4K.\n"
                "- Ecolan 200Mb: gamers, trabajo remoto pesado, múltiples streams 4K.\n"
                "- Ecolan 300Mb: uso intensivo, disponible solo en FTTH.\n"
                "Disponibilidad de velocidades según tecnología: FTTH hasta 300Mb, "
                "radio hasta 100Mb, ADSL hasta 20Mb (según distancia a central).\n"
                "Para contratar o cambiar → derivar a área comercial (agente)."
            ),
        ),
        KnowledgeArticle(
            organizacion_id=org_id,
            titulo="Planes IMOWI móvil — vigentes",
            categoria="Comercial",
            contenido=(
                "Planes IMOWI vigentes (confirmar precios en oficina):\n"
                "- IMOWI 3GB: 3GB datos + minutos ilimitados + SMS ilimitados.\n"
                "- IMOWI 5GB: 5GB datos + minutos ilimitados + SMS ilimitados.\n"
                "- IMOWI 15GB: 15GB datos + minutos ilimitados + WhatsApp libre.\n"
                "- IMOWI 30GB: 30GB datos + minutos ilimitados + redes sociales libres.\n"
                "- IMOWI 50GB: 50GB datos + todo ilimitado.\n"
                "Todos los planes incluyen roaming nacional.\n"
                "Portabilidad: se puede traer el número de otro operador (3-5 días hábiles).\n"
                "Para contratar → oficina comercial con DNI."
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
                "3) Problema claramente fuera de alcance del bot (falla masiva, configuración "
                "   avanzada, reclamo comercial complejo).\n"
                "4) Se necesita acceso a sistemas internos (facturación, HLR, NMS).\n\n"
                "Al escalar incluir: servicio afectado, pasos ya realizados en N1, dirección "
                "del abonado (si aplica), teléfono de contacto, resumen del síntoma."
            ),
        ),
    ]


def seed_kb_batan_servicios(db: Session) -> dict:
    """Asegura artículos KB de radio/ADSL/IMOWI/Sensa (idempotente por título).

    También corrige el typo histórico IMOVI → IMOWI en títulos/contenido ya seedados.
    """
    batan = _org(db, "coop-batan")
    if not batan:
        return {"seeded": False, "articulos": 0}

    fixed = 0
    for art in db.scalars(
        select(KnowledgeArticle).where(KnowledgeArticle.organizacion_id == batan.id)
    ).all():
        new_titulo = (art.titulo or "").replace("IMOVI", "IMOWI")
        new_contenido = (art.contenido or "").replace("IMOVI", "IMOWI")
        if new_titulo != (art.titulo or "") or new_contenido != (art.contenido or ""):
            art.titulo = new_titulo
            art.contenido = new_contenido
            fixed += 1
    if fixed:
        db.commit()

    existentes = {
        a.titulo
        for a in db.scalars(
            select(KnowledgeArticle).where(KnowledgeArticle.organizacion_id == batan.id)
        ).all()
    }
    nuevos = [a for a in _articulos_kb_batan(batan.id) if a.titulo not in existentes]
    if not nuevos and not fixed:
        return {"seeded": False, "articulos": len(existentes), "fixed_imowi": 0}
    if nuevos:
        db.add_all(nuevos)
        db.commit()
    return {"seeded": bool(nuevos), "articulos": len(nuevos), "fixed_imowi": fixed}


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
