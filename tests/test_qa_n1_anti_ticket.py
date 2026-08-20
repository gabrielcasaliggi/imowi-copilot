"""Regresiones QA N1 — anti-ticket prematuro, falso cierre, QR, typos."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.domain.flujos_abonado import (
    clasificar_intencion,
    contiene_sintoma_canal,
    detecta_frustracion,
    es_escape_agente,
    indica_resuelto,
    pide_humano,
)
from main import app

client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": "admin", "password": "admin"})
    assert r.status_code == 200
    return {
        "Authorization": f"Bearer {r.json()['token']}",
        "X-Tenant-Slug": "coop-batan",
    }


def _guest_portal() -> str:
    r = client.post("/api/v1/portal/session", json={"org_slug": "coop-batan"})
    assert r.status_code == 200
    return r.json()["portal_token"]


def _identified_portal(dni: str = "30111222") -> str:
    start = client.post(
        "/api/v1/portal/auth/start",
        json={"dni": dni, "org_slug": "coop-batan"},
    )
    assert start.status_code == 200, start.text
    otp = start.json()["debug_otp"]
    verify = client.post(
        "/api/v1/portal/auth/verify",
        json={
            "challenge_id": start.json()["challenge_id"],
            "otp": otp,
            "org_slug": "coop-batan",
        },
    )
    assert verify.status_code == 200, verify.text
    data = verify.json()
    # Aislar casos N1: reabrir hilo en bot aunque un test previo lo haya derivado
    from app.estate import canal_repo as crepo
    from app.estate.database import get_session_factory
    from app.estate.models import ConversacionCanal

    conv_id = data["conversacion"]["id"]
    Session = get_session_factory()
    with Session() as db:
        c = db.get(ConversacionCanal, conv_id)
        if c:
            c.estado = "bot"
            c.ticket_id = ""
            c.agente_id = ""
            ctx = crepo.get_contexto(c)
            for k in (
                "visitante",
                "cola_prioridad",
                "motivo_derivacion",
                "invitado",
                "intencion",
                "paso_idx",
                "diag_turnos",
                "pidio_humano",
                "pedido_humano_count",
            ):
                ctx.pop(k, None)
            ctx["identificado"] = True
            ctx["saludo"] = True
            crepo.set_contexto(c, ctx)
            db.commit()
    return data["portal_token"]


def _portal_msg(token: str, texto: str, *, usar_hint: bool = False) -> dict:
    # Portal messages always go through canal; usar_llama resolved server-side.
    r = client.post(
        "/api/v1/portal/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"texto": texto},
    )
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Unitarios dominio
# ---------------------------------------------------------------------------

def test_indica_resuelto_no_cierra_cobertura_parcial():
    assert indica_resuelto("En el living anda bien, lejos no") is False
    assert indica_resuelto("anda bien en el living pero no llega al fondo") is False
    assert indica_resuelto("ya anda todo") is True
    assert indica_resuelto("mejoró") is True
    assert indica_resuelto("ya funciona") is True


def test_si_me_contesto_no_cierra_como_resuelto():
    """«si me contestó» (Whisper: contesto) ≠ servicio OK ni paso playbook."""
    from app.domain.flujos_abonado import (
        confirma_contacto_sin_servicio,
        respuesta_paso_ok,
    )

    for msg in ("si me contesto", "si me contestó", "sí me contestaron", "me llamaron"):
        assert confirma_contacto_sin_servicio(msg) is True
        assert indica_resuelto(msg) is False
        assert respuesta_paso_ok(msg) is None
    assert confirma_contacto_sin_servicio("me contestó y ya anda") is False
    assert indica_resuelto("me contestó y ya anda todo") is True


def test_indica_resuelto_cierre_wifi_gracias_ticket():
    msg = (
        "impecable, si ahí moví un poco más cerca del baño en el rutor wifi "
        "y ahora ya me funcionaba bien, muchas gracias, puede cerrar el ticket"
    )
    assert indica_resuelto(msg) is True


def test_cliente_cable_ok_no_impecable():
    from app.services.canal_abonado import _cliente_cable_ok

    assert not _cliente_cable_ok(
        "impecable, moví el router wifi y ahora ya me funcionaba bien, muchas gracias"
    )
    assert _cliente_cable_ok("por cable funciona bien")
    assert _cliente_cable_ok("el cable anda ok")


def test_detecta_frustracion_requiere_progreso_n1():
    ctx0 = {"ultima_queja": "no tengo internet", "paso_idx": 0, "reiteracion_queja": 1}
    assert detecta_frustracion("No tengo internet", ctx0) is False
    ctx2 = {"ultima_queja": "no tengo internet", "paso_idx": 2, "reiteracion_queja": 1}
    assert detecta_frustracion("No tengo internet", ctx2) is True


def test_escape_agente_y_sintoma():
    from app.domain.flujos_abonado import pide_humano_en_flujo_activo

    assert es_escape_agente("*agente*") is True
    assert es_escape_agente("agente") is True
    assert es_escape_agente("Quiero hablar con un operador") is False
    assert contiene_sintoma_canal("pasame con operador que no anda internet") is True
    assert contiene_sintoma_canal("quiero un operador") is False
    assert pide_humano("quiero un operador") is True
    assert pide_humano("nose como hacer eso, deberia venir un tecnico") is True
    assert pide_humano("tienen que mandar una visita técnica") is True
    # Opción del menú móvil ≠ pedido de agente
    assert pide_humano("Tecnico") is False
    assert pide_humano("técnico") is False
    assert pide_humano("tema tecnico") is False
    assert pide_humano("mandame un tecnico") is True
    assert pide_humano_en_flujo_activo(
        "deberia venir un tecnico",
        {"intencion": "wifi", "diag_turnos": 2},
    ) is True
    assert pide_humano_en_flujo_activo(
        "deberia venir un tecnico",
        {"intencion": "wifi", "diag_turnos": 0, "paso_idx": 0},
    ) is False
    assert pide_humano_en_flujo_activo(
        "quiero un operador",
        {"intencion": "", "diag_turnos": 0},
    ) is False
    assert pide_humano_en_flujo_activo(
        "Tecnico",
        {"intencion": "movil", "diag_turnos": 0, "paso_idx": 0},
    ) is False


def test_clasifica_datos_moviles_coloquial():
    assert clasificar_intencion("Si, no me andan los datos moviles en el celu") == "movil_datos"
    assert clasificar_intencion("no andan los datos del celular") == "movil_datos"
    assert contiene_sintoma_canal("no me andan los datos moviles") is True


def test_detectar_so_movil_y_bloquea_apn_iphone():
    import json
    from unittest.mock import patch

    from app.services.diagnostico_n1 import (
        _MSG_APN_ANDROID,
        detectar_so_movil,
        diagnosticar_turno,
    )

    assert detectar_so_movil("Es android, ya te dije que es un Moto g72") == "android"
    assert detectar_so_movil("No es iPhone, es android") == "android"
    assert detectar_so_movil("tengo un iPhone 13") == "ios"
    hist = [
        {"autor": "cliente", "texto": "Es un Moto g72"},
        {"autor": "bot", "texto": "¿Android o iPhone?"},
    ]
    assert detectar_so_movil("ya te dije", hist) == "android"

    def _fake(*_a, **_k):
        return json.dumps(
            {
                "accion": "ask",
                "mensaje": (
                    "Para iPhone anteriores, andá a Configuración > Datos celulares > "
                    "Opciones > Red de datos celulares. Poné APN: apn1.catel.org.ar "
                    "y Usuario: imowi. ¿Te funcionó?"
                ),
                "paso_cubierto": "apn_datos",
                "motivo": "ia",
            },
            ensure_ascii=False,
        )

    with patch("app.llm.chat_completion", side_effect=_fake):
        out = diagnosticar_turno(
            intencion="movil_datos",
            checklist=[
                {"id": "apn_datos", "pregunta": "Revisá el APN Android…"},
            ],
            historial_mensajes=[
                {"autor": "cliente", "texto": "Es android, es un Moto g72"},
            ],
            mensaje_cliente="No es iPhone, es android",
            turnos_diagnostico=3,
            pasos_cubiertos=["datos_activados", "so_dispositivo"],
        )
    assert out["accion"] == "ask"
    assert out["motivo"] == "bloqueado_apn_so_android"
    assert "iphone" not in (out.get("mensaje") or "").lower()
    assert "android" in (out.get("mensaje") or "").lower()
    assert "apn1.catel.org.ar" in (out.get("mensaje") or "")
    assert out["mensaje"] == _MSG_APN_ANDROID


def test_typo_internet_clasifica():
    assert clasificar_intencion("ola no anda el interntt, no me carga nadaa") == "internet"
    assert clasificar_intencion("Me cortaron por falta de pago, como pago") == "corte_deuda"


def test_clasifica_tv_sensa():
    from app.domain.flujos_abonado import PLAYBOOKS, tag_para_intencion
    from app.services.diagnostico_n1 import es_intencion_diagnostico

    assert clasificar_intencion("No puedo ver televisión OTT (Sensa)") == "tv_sensa"
    assert clasificar_intencion("no funciona sensa") == "tv_sensa"
    assert clasificar_intencion("no anda la tele en la smart tv") == "tv_sensa"
    assert clasificar_intencion("la tv no reproduce nada") == "tv_sensa"
    # Sin internet + Sensa → primero conectividad
    assert clasificar_intencion("no tengo internet y no anda sensa") == "internet"
    assert "tv_sensa" in PLAYBOOKS
    assert len(PLAYBOOKS["tv_sensa"]) >= 5
    assert PLAYBOOKS["tv_sensa"][0].id == "triaje_tv_sensa"
    assert tag_para_intencion("tv_sensa") == "[TEC_TV_SENSA]"
    assert es_intencion_diagnostico("tv_sensa") is True
    assert contiene_sintoma_canal("no anda sensa, quiero un agente") is True


def test_clasifica_telefono_fija_y_cobertura_playbook():
    from app.domain.flujos_abonado import PLAYBOOKS, tag_para_intencion

    assert clasificar_intencion("no anda el fijo, sin tono") == "telefono_fija"
    assert clasificar_intencion("no me llaman al fijo") == "telefono_fija"
    assert clasificar_intencion("problema con telefonía fija") == "telefono_fija"
    # ADSL no debe caer en fija solo por "línea"
    assert clasificar_intencion("se me cae el adsl, parpadea el modem") == "internet_adsl"
    assert len(PLAYBOOKS["telefono_fija"]) >= 5
    assert tag_para_intencion("telefono_fija") == "[TEL_FIJA]"


def test_clasifica_imowi_robo_datos_y_a2p():
    assert clasificar_intencion("me robaron el celular imowi") == "movil"
    assert clasificar_intencion("perdi el celular necesito *910") == "movil"
    assert clasificar_intencion("se me acabaron los datos del abono") == "movil_datos"
    assert clasificar_intencion("no me llega el sms de verificación del banco") == "movil_llamadas"
    assert contiene_sintoma_canal("me robaron el celu *910") is True


def test_kb_batan_seed_cubre_servicios_oficiales():
    from app.estate.seed import _articulos_kb_batan

    arts = _articulos_kb_batan("org-test")
    by_title = {a.titulo: a.contenido for a in arts}
    assert "Telefonía fija — sin tono o falla" in by_title
    assert "IMOWI — robo o pérdida de celular" in by_title
    assert "IMOWI — SMS de verificación (A2P)" in by_title
    assert "IMOWI — FAQ operativa N1" in by_title
    assert "IMOWI — baja o arrepentimiento" in by_title
    planes = by_title["Planes IMOWI móvil — vigentes"]
    assert "8GB" in planes
    assert "25GB" in planes
    assert "1,5GB" in planes or "1.5GB" in planes
    assert "30GB" not in planes and "50GB" not in planes
    assert "ov.batan.coop" in planes
    assert "imowi.com.ar/autogestion" not in planes.lower() or "NO" in planes
    faq = by_title["IMOWI — FAQ operativa N1"]
    assert "ov.batan.coop" in faq
    assert "NO redirigir" in faq or "NO" in faq
    assert "imowi.com.ar/autogestion" in faq
    datos = by_title["IMOWI — sin datos móviles"]
    assert "apn1.catel.org.ar" in datos
    assert "usuario = imowi" in datos or "Nombre de usuario = imowi" in datos
    assert "ov.batan.coop" in datos
    assert "NO orientar" in datos or "NO" in datos
    assert "*333" in by_title["IMOWI — llamadas y SMS"]
    assert "*#06#" in by_title["IMOWI — activar SIM / eSIM"]
    assert "10 días" in by_title["IMOWI — baja o arrepentimiento"]
    assert "24" in by_title["IMOWI — portabilidad numérica"]
    assert "ov.batan.coop" in by_title["Cooperativa Batán — información general"]
    assert "464-3006" in by_title["Cooperativa Batán — información general"]
    assert "no es necesario avisar" in by_title["Corte por deuda — rehabilitación automática"].lower()
    assert "decodificador" in by_title["TV OTT Sensa — sin reproducción o no abre"].lower()
    assert any("BAI" in c or "puerto AZUL" in c for c in by_title.values())
    assert "100M" in by_title["Planes internet Ecolan — vigentes"]
    assert "600M" in by_title["Planes internet Ecolan — vigentes"]
    ftth = by_title["Internet FTTH (fibra óptica) — sin servicio"]
    assert "NO manipular" in ftth or "no manipular" in ftth.lower()
    assert "LOS" in ftth
    assert "Internet — cortes o intermitencia" in by_title
    assert "N1 hogareño — luces PON y LOS" in by_title
    assert "N1 hogareño — cable vs WiFi" in by_title
    assert "N1 hogareño — lentitud en horario pico" in by_title
    assert "N1 hogareño — PoE y antena de techo" in by_title
    assert "N1 hogareño — adulto mayor y WhatsApp (línea OK)" in by_title
    assert "LOS" in by_title["N1 hogareño — luces PON y LOS"]
    whatsapp = by_title["N1 hogareño — adulto mayor y WhatsApp (línea OK)"]
    assert "WhatsApp" in whatsapp
    assert "PPPoE" in whatsapp or "sesión" in whatsapp.lower()
    assert "No abrir visita" in whatsapp or "no abrir visita" in whatsapp.lower()
    assert "internet_intermitente" in by_title["Internet — cortes o intermitencia"]
    assert "WiFi — cambiar clave o nombre de red" in by_title
    assert "cambio_clave_wifi" in by_title["WiFi — cambiar clave o nombre de red"]
    assert "Facturación — descargar factura o talón" in by_title
    assert "ov.batan.coop" in by_title["Facturación — informar un pago"]
    assert "facturacion_estado_cuenta" in by_title["Facturación — estado de cuenta"]


def test_playbooks_imowi_apn_y_autogestion_batan():
    from app.domain.flujos_abonado import PLAYBOOKS

    apn = next(p.pregunta for p in PLAYBOOKS["movil"] if p.id == "apn_imovi")
    assert "apn1.catel.org.ar" in apn
    assert "usuario imowi" in apn.lower() or "usuario = imowi" in apn.lower()
    assert "android" in apn.lower()
    datos = next(p.pregunta for p in PLAYBOOKS["movil_datos"] if p.id == "consumo_paquete")
    assert "ov.batan.coop" in datos
    assert "imowi.com.ar" in datos  # se menciona para decir que NO usarla
    assert "no uses" in datos.lower() or "no" in datos.lower()
    apn_datos = next(p.pregunta for p in PLAYBOOKS["movil_datos"] if p.id == "apn_datos")
    assert "apn1.catel.org.ar" in apn_datos
    assert "NO mezcles" in apn_datos or "no mezcles" in apn_datos.lower()
    so = next(p for p in PLAYBOOKS["movil_datos"] if p.id == "so_dispositivo")
    assert "android" in so.pregunta.lower() and "iphone" in so.pregunta.lower()
    robo = next(p.pregunta for p in PLAYBOOKS["movil"] if p.id == "robo_perdida_hint")
    assert "*910" in robo and "*303" in robo
    assert clasificar_intencion("quiero escuchar el correo de voz *333") == "movil_llamadas"
    assert clasificar_intencion("necesito activar la esim imowi") == "movil"
    assert clasificar_intencion("quiero dar de baja imowi") == "alta_plan"


def test_playbooks_menu_y_portal_mencionan_servicios():
    from app.domain.flujos_abonado import PLAYBOOKS

    menu = PLAYBOOKS["general"][0].pregunta.lower()
    assert "fijo" in menu
    assert "telefonía móvil" in menu or "telefonia movil" in menu.replace("í", "i")
    assert "imowi" not in menu
    portal = PLAYBOOKS["portal_tramites"][0].pregunta.lower()
    assert "ov.batan.coop" in portal
    assert any(p.id == "cable_wan_bai" for p in PLAYBOOKS["internet_radio"])


def test_playbooks_botmaker_intermitente_clave_wifi_y_los():
    from app.domain.flujos_abonado import PLAYBOOKS, tag_para_intencion
    from app.services.diagnostico_n1 import es_intencion_diagnostico

    assert clasificar_intencion("se me cae el internet a cada rato") == "internet_intermitente"
    assert clasificar_intencion("el servicio va y viene, es intermitente") == "internet_intermitente"
    assert clasificar_intencion("quiero cambiar la clave del wifi") == "cambio_clave_wifi"
    assert clasificar_intencion("cambiar el nombre del wifi") == "cambio_clave_wifi"
    assert clasificar_intencion("no llega wifi al fondo") == "wifi"
    assert clasificar_intencion("cómo va mi reclamo técnico") == "estado_reclamo"
    assert clasificar_intencion("se me corta la fibra") == "internet_ftth"

    inter = PLAYBOOKS["internet_intermitente"]
    assert inter[0].id == "alcance_cortes"
    assert any(p.id == "frecuencia_cortes" for p in inter)
    assert any(p.id == "turno_campo_intermitente" for p in inter)
    assert tag_para_intencion("internet_intermitente") == "[TEC_INTERMITENCIA]"
    assert es_intencion_diagnostico("internet_intermitente") is True

    clave = PLAYBOOKS["cambio_clave_wifi"]
    assert clave[0].id == "cambio_clave_wifi_detalle"
    assert any("etiqueta" in p.pregunta.lower() for p in clave)
    assert es_intencion_diagnostico("cambio_clave_wifi") is True

    cable = next(p.pregunta for p in PLAYBOOKS["internet_ftth"] if p.id == "cable_fibra")
    assert "sin tocar" in cable.lower() or "sin desconectar" in cable.lower()
    assert "amarillo" in cable.lower()
    radio = next(p.pregunta for p in PLAYBOOKS["internet_radio"] if p.id == "cable_wan_bai")
    assert "antena" in radio.lower()
    assert any(p.id == "validacion_navegacion_adsl" for p in PLAYBOOKS["internet_adsl"])
    assert any(p.id == "medio_prueba" for p in PLAYBOOKS["internet_lento"])
    assert any(p.id == "conexion_cableada" for p in PLAYBOOKS["wifi"])
    assert PLAYBOOKS["estado_reclamo"][0].id == "estado_reclamo_detalle"


def test_playbooks_facturacion_botmaker_desglose():
    from app.domain.flujos_abonado import PLAYBOOKS, intencion_es_facturacion, tag_para_intencion
    from app.services.diagnostico_n1 import es_intencion_diagnostico
    from app.services.outages import intencion_bloquea_outage

    assert clasificar_intencion("cómo pago la factura") == "facturacion_pago"
    assert clasificar_intencion("quiero descargar el talón de pago") == "facturacion_descarga"
    assert clasificar_intencion("ya pagué y no figura el pago") == "facturacion_informar_pago"
    assert clasificar_intencion("mandame la factura por mail") == "facturacion_factura"
    assert clasificar_intencion("cuánto debo, estado de cuenta") == "facturacion_estado_cuenta"
    assert clasificar_intencion("me cobraron de más este mes") == "facturacion_reclamo"
    assert clasificar_intencion("pagué y sigue cortado el servicio") == "reactivacion_pago"
    assert clasificar_intencion("Me cortaron por falta de pago, como pago") == "corte_deuda"
    # Dos motivos de factura → enrutador
    assert clasificar_intencion(
        "Queria saber cuanto me vino en mi factura de internet y cual es la web para abonarla?"
    ) == "facturacion"

    pago = next(p.pregunta for p in PLAYBOOKS["facturacion_pago"] if p.id == "medios_pago_qr")
    assert "Fiserv" in pago
    assert "ov.batan.coop" in pago
    assert "acredita" in pago.lower() or "acreditación" in pago.lower()
    informar = PLAYBOOKS["facturacion_informar_pago"][0].pregunta.lower()
    assert "no hace falta" in informar or "reactiva solo" in informar
    assert PLAYBOOKS["facturacion"][0].id == "triaje_motivo"
    assert tag_para_intencion("facturacion_pago") == "[PAGOS_QR]"
    assert es_intencion_diagnostico("facturacion_pago") is True
    assert es_intencion_diagnostico("corte_deuda") is False
    assert intencion_es_facturacion("facturacion_descarga") is True
    assert intencion_bloquea_outage("facturacion_pago") is True
    assert intencion_bloquea_outage("reactivacion_pago") is True


# ---------------------------------------------------------------------------
# Portal / canal — N1 con abonado identificado
# ---------------------------------------------------------------------------

def test_pedido_humano_sin_sintoma_no_crea_ticket_inmediato():
    token = _identified_portal()
    data = _portal_msg(token, "Quiero hablar con una persona, pasame con un operador")
    assert data.get("ok") is True
    assert data.get("estado") == "bot"
    assert not data.get("ticket_id")
    resp = (data.get("respuesta") or "").lower()
    assert "ticket" not in resp
    assert "agente" in resp or "internet" in resp or "contame" in resp


def test_escape_agente_explicito_crea_ticket():
    token = _identified_portal()
    _portal_msg(token, "Hola")
    data = _portal_msg(token, "*agente*")
    assert data.get("ok") is True
    assert data.get("ticket_id")
    assert data.get("estado") == "espera_agente"


def test_segunda_insistencia_humano_crea_ticket():
    token = _identified_portal()
    r1 = _portal_msg(token, "Quiero hablar con un agente humano")
    assert not r1.get("ticket_id")
    r2 = _portal_msg(token, "Pasame con un operador ya")
    assert r2.get("ticket_id")
    assert r2.get("estado") == "espera_agente"


def test_humano_con_sintoma_entra_n1():
    """Pedido de operador + síntoma: entra a N1 (no crea ticket en el primer turno sin *agente*)."""
    token = _identified_portal()
    data = _portal_msg(
        token,
        "No me anda internet desde ayer, se corta todo el tiempo",
    )
    assert data.get("ok") is True
    assert data.get("estado") == "bot"
    assert not data.get("ticket_id")
    resp = (data.get("respuesta") or "").lower()
    assert "jsc-" not in resp


def test_reiteracion_temprana_no_ticket():
    token = _identified_portal()
    r1 = _portal_msg(token, "No tengo internet")
    assert r1.get("estado") == "bot"
    assert not r1.get("ticket_id")
    r2 = _portal_msg(token, "No tengo internet")
    assert r2.get("estado") == "bot"
    assert not r2.get("ticket_id")
    r3 = _portal_msg(token, "No tengo internet")
    assert r3.get("estado") == "bot"
    assert not r3.get("ticket_id")


def test_padron_solo_movil_no_diagnostica_internet():
    """Si el padrón no tiene internet fijo, no ofrecer fibra/Wi‑Fi ni asumir corte."""
    from sqlalchemy import select

    from app.estate import canal_repo as crepo
    from app.estate.database import get_session_factory
    from app.estate.models import Abonado, ConversacionCanal, Organization
    from app.services.canal_abonado import procesar_mensaje_entrante

    tel = "5492235599991"
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        assert org
        abo = db.scalar(select(Abonado).where(Abonado.dni == "32123456"))
        assert abo is not None
        abo.servicio = "movil"
        for c in db.scalars(
            select(ConversacionCanal).where(ConversacionCanal.telefono.contains(tel[-10:]))
        ).all():
            c.estado = "cerrado"
            c.contexto_json = "{}"
            c.ticket_id = ""
            c.agente_id = ""
            c.abonado_id = ""
        db.commit()
        conv = crepo.get_or_create_conversacion(
            db, org.id, telefono=tel, canal="whatsapp", wa_id=tel
        )
        conv.estado = "bot"
        conv.abonado_id = abo.id
        conv.contexto_json = "{}"
        db.commit()
        org_id = org.id

    with Session() as db:
        r0 = procesar_mensaje_entrante(
            db, org_id, telefono=tel, texto="hol", canal="whatsapp", usar_llama=False
        )
    resp_hola = (r0.get("respuesta") or "").lower()
    assert r0.get("estado") == "bot"
    assert "diagnóstico de internet" not in resp_hola
    assert "imowi" in resp_hola or "móvil" in resp_hola or "movil" in resp_hola
    assert "internet," not in resp_hola

    with Session() as db:
        r1 = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto="no tengo internet",
            canal="whatsapp",
            usar_llama=False,
        )
    resp = (r1.get("respuesta") or "").lower()
    assert r1.get("estado") == "bot"
    assert "no figura internet" in resp
    assert "wi-fi" not in resp and "wifi" not in resp
    assert "cajita" not in resp
    assert "línea ya está ok" not in resp and "linea ya esta ok" not in resp


def test_visitante_portal_deriva_sin_ticket_n2():
    """Guest: cola de agente con prioridad baja; sin ticket N2 ni N1."""
    r = client.post("/api/v1/portal/session", json={"org_slug": "coop-batan"})
    assert r.status_code == 200
    sess = r.json()
    assert sess["conversacion"]["estado"] == "espera_agente"
    assert sess["conversacion"].get("cola_prioridad") == "baja"
    assert not sess["conversacion"].get("ticket_id")
    token = sess["portal_token"]
    data = _portal_msg(token, "Me cortaron el servicio por falta de pago, como pago?")
    assert data.get("ok") is True
    assert data.get("estado") == "espera_agente"
    assert not data.get("ticket_id")
    resp = (data.get("respuesta") or "").lower()
    assert "fiserv" not in resp


def test_saldo_billtrack_no_fuerza_cobro_ante_aumento_imowi():
    """Regresión: billing_balance > 0 no debe pisar reclamo IMOWI + aumento con QR."""
    from app.domain.flujos_abonado import clasificar_intencion, detectar_temas_duales
    from app.estate.models import Abonado
    from app.services.canal_abonado import _deberia_priorizar_corte_deuda, _es_solo_dni

    msg = "tengo problemas con imowi y quiero reclamar por una factura con aumento"
    # IMOWI + factura sin síntoma técnico de fallo = solo facturación (no dual).
    assert set(detectar_temas_duales(msg)) == {"facturacion"}
    assert clasificar_intencion(msg) == "facturacion_reclamo"
    # Dual real: síntoma técnico + factura.
    assert set(detectar_temas_duales("internet lento y factura con aumento")) == {
        "tecnico",
        "facturacion",
    }

    abo = Abonado(
        organizacion_id="x",
        dni="30111222",
        nombre="JORGE",
        estado="activo",
        deuda_monto="55779.99",
    )
    assert _deberia_priorizar_corte_deuda(abo, msg, "facturacion") is False
    assert _deberia_priorizar_corte_deuda(
        abo, "Me cortaron por falta de pago, como pago?", "general"
    ) is True
    assert _es_solo_dni("13920806") is True
    assert _es_solo_dni("mi dni es 13920806") is True
    # Whisper / dictado dígito a dígito
    from app.services.canal_abonado import _extraer_dni

    assert _es_solo_dni("24, 9, 14, 8, 6, 7") is True
    assert _extraer_dni("24, 9, 14, 8, 6, 7") == "24914867"
    assert _extraer_dni("2 4 9 1 4 8 6 7") == "24914867"
    assert _extraer_dni("24.914.867") == "24914867"
    assert _extraer_dni("24,914,867") == "24914867"
    assert _extraer_dni("mi dni es 24.914.867") == "24914867"
    assert _extraer_dni("dos cuatro nueve uno cuatro ocho seis siete") == "24914867"
    assert _extraer_dni("veinticuatro nueve uno cuatro ocho seis siete") == "24914867"
    # Whisper: "nueve"/"9" → "no"; "6 7" → "67"
    assert _extraer_dni("24, no y 14, 8, 67.") == "24914867"
    assert _es_solo_dni("24, no y 14, 8, 67.") is True
    assert _es_solo_dni("corte desde el 10/08/2024 y no anda") is False


def test_wifi_parcial_no_cierra_resuelto():
    token = _identified_portal()
    _portal_msg(token, "El WiFi no llega a la habitación del fondo")
    data = _portal_msg(token, "En el living anda bien, lejos no")
    assert data.get("estado") != "cerrado"
    resp = (data.get("respuesta") or "").lower()
    assert "quedó resuelto" not in resp
    assert "quedo resuelto" not in resp
    assert "genial" not in resp or "lejos" in resp or "wifi" in resp or "router" in resp


def test_inbox_pide_agente_ya_no_ticket_en_primer_turno():
    """Regresión del comportamiento anterior: 1er pedido humano ≠ ticket."""
    from sqlalchemy import select

    from app.estate.database import get_session_factory
    from app.estate.models import ConversacionCanal

    tel = "5492235560199"
    Session = get_session_factory()
    with Session() as db:
        suf = tel[-10:]
        for c in db.scalars(select(ConversacionCanal)).all():
            if (c.telefono or "").endswith(suf) or c.telefono == tel:
                c.estado = "cerrado"
                c.contexto_json = "{}"
                c.ticket_id = ""
                c.agente_id = ""
        db.commit()

    headers = _admin_headers()
    r0 = client.post(
        "/api/v1/inbox/simulate",
        headers=headers,
        json={"telefono": tel, "texto": "Hola", "usar_llama": False},
    )
    assert r0.status_code == 200
    r = client.post(
        "/api/v1/inbox/simulate",
        headers=headers,
        json={
            "telefono": tel,
            "texto": "Quiero hablar con un agente humano",
            "usar_llama": False,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("estado") == "bot"
    assert not data.get("ticket_id")
    # Escape hatch sigue funcionando
    r2 = client.post(
        "/api/v1/inbox/simulate",
        headers=headers,
        json={"telefono": tel, "texto": "*agente*", "usar_llama": False},
    )
    assert r2.status_code == 200
    assert r2.json().get("ticket_id")
    assert r2.json().get("estado") == "espera_agente"


def test_menu_movil_tecnico_no_ticket_inmediato():
    """Regresión Armando: menú móvil → Técnico → síntoma datos → N1, sin ticket."""
    from sqlalchemy import select

    from app.estate import canal_repo as crepo
    from app.estate.database import get_session_factory
    from app.estate.models import Abonado, ConversacionCanal, Organization
    from app.services.canal_abonado import procesar_mensaje_entrante

    tel = "5492235599992"
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        assert org
        abo = db.scalar(select(Abonado).where(Abonado.dni == "32123456"))
        assert abo is not None
        abo.servicio = "movil"
        abo.deuda_monto = "0"
        abo.estado = "activo"
        for c in db.scalars(
            select(ConversacionCanal).where(ConversacionCanal.telefono.contains(tel[-10:]))
        ).all():
            c.estado = "cerrado"
            c.contexto_json = "{}"
            c.ticket_id = ""
            c.agente_id = ""
            c.abonado_id = ""
        db.commit()
        conv = crepo.get_or_create_conversacion(
            db, org.id, telefono=tel, canal="whatsapp", wa_id=tel
        )
        conv.estado = "bot"
        conv.abonado_id = abo.id
        conv.ticket_id = ""
        crepo.set_contexto(
            conv,
            {
                "saludo": True,
                "menu_paso": "servicio",
                "intencion": "general",
                "paso_idx": 0,
            },
        )
        db.commit()
        org_id = org.id

    with Session() as db:
        r1 = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto="Telefonia movil",
            canal="whatsapp",
            usar_llama=False,
        )
    assert r1.get("estado") == "bot"
    assert not r1.get("ticket_id")
    resp1 = (r1.get("respuesta") or "").lower()
    assert "técnico" in resp1 or "tecnico" in resp1
    assert "comercial" in resp1

    with Session() as db:
        r2 = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto="Tecnico",
            canal="whatsapp",
            usar_llama=False,
        )
    assert r2.get("estado") == "bot"
    assert not r2.get("ticket_id")
    assert r2.get("intencion") in ("movil", "movil_datos", "movil_llamadas")
    resp2 = (r2.get("respuesta") or "").lower()
    assert "ticket" not in resp2
    assert "generé" not in resp2 and "genere" not in resp2
    assert any(k in resp2 for k in ("datos", "señal", "senal", "llamar", "móvil", "movil"))

    with Session() as db:
        r3 = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto="Si, no me andan los datos moviles en el celu",
            canal="whatsapp",
            usar_llama=False,
        )
    assert r3.get("estado") == "bot"
    assert not r3.get("ticket_id")
    assert r3.get("intencion") == "movil_datos"
    resp3 = (r3.get("respuesta") or "").lower()
    assert "ticket" not in resp3
    assert "generé" not in resp3 and "genere" not in resp3
    assert any(k in resp3 for k in ("datos", "avión", "avion", "apn", "abon"))
