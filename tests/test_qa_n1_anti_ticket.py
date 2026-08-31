"""Regresiones QA N1 — anti-ticket prematuro, falso cierre, QR, typos."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.domain.flujos_abonado import (
    clasificar_intencion,
    contiene_sintoma_canal,
    detecta_frustracion,
    es_escape_agente,
    indica_resuelto,
    parse_menu_servicio,
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


def test_es_cambio_tema_claro_entre_dominios():
    from app.domain.flujos_abonado import es_cambio_tema_claro, parece_consulta_nueva

    assert parece_consulta_nueva("Se me acabaron los datos del abono") is False
    assert (
        es_cambio_tema_claro("Se me acabaron los datos del abono", "tv_sensa")
        == "movil_datos"
    )
    assert (
        es_cambio_tema_claro(
            "Se me acabaron los datos del abono", "facturacion_factura"
        )
        == "movil_datos"
    )
    assert (
        es_cambio_tema_claro("No anda Sensa en la smart tv", "facturacion_factura")
        == "tv_sensa"
    )
    # Misma familia móvil o respuesta corta de playbook: no resetear
    assert es_cambio_tema_claro("no me andan los datos", "movil_llamadas") is None
    assert es_cambio_tema_claro("smart tv", "tv_sensa") is None
    assert es_cambio_tema_claro("si", "tv_sensa") is None
    # Mid-playbook: mención incidental de internet/WiFi no es cambio de dominio (P18/P19)
    assert (
        es_cambio_tema_claro("Sí, internet anda bien en la casa", "tv_sensa") is None
    )
    assert (
        es_cambio_tema_claro(
            "Apagué el WiFi y sigo sin datos móviles", "movil_datos"
        )
        is None
    )


def test_cliente_pide_pagar_no_confunde_modo_avion():
    from app.services.diagnostico_n1 import _cliente_pide_pagar

    assert _cliente_pide_pagar("Sí, datos prendidos y sin modo avión") is False
    assert _cliente_pide_pagar("modo avion apagado") is False
    assert _cliente_pide_pagar("quiero pagar con modo") is True
    assert _cliente_pide_pagar("mercado pago") is True


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
    assert parse_menu_servicio(",ovil") == "movil"
    assert parse_menu_servicio("ovil") == "movil"
    assert parse_menu_servicio("movil") == "movil"
    assert parse_menu_servicio("No tengo datos en Mar del Plata") == "movil"
    assert (
        parse_menu_servicio("Quiero dar de baja todo el internet y sensa")
        == "comercial"
    )
    from app.domain.flujos_abonado import resolver_menu_servicio

    assert resolver_menu_servicio("No tengo datos en Mar del Plata", "movil") == "movil"
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


def test_patricia_moto_g72_no_pasos_iphone_ni_3g():
    """Caso real: Android ya dicho → no iPhone; APN OK → no 3G; pack OK sin datos → N2."""
    import json
    from unittest.mock import patch

    from app.services.diagnostico_n1 import (
        _MSG_APN_ANDROID,
        _MSG_PACK_ACREDITADO,
        _MSG_PACK_CHEQUEO,
        diagnosticar_turno,
        pack_acreditado_sin_datos,
    )

    hist = [
        {"autor": "cliente", "texto": "No Tengo datos en Mar del Plata"},
        {"autor": "bot", "texto": "¿Qué modelo de celular tenés?"},
        {"autor": "cliente", "texto": "Moto g72"},
    ]
    checklist = [
        {"id": "datos_activados", "pregunta": "¿Datos prendidos?"},
        {"id": "consumo_paquete", "pregunta": "¿Te quedan datos del abono?"},
        {"id": "so_dispositivo", "pregunta": "¿Android o iPhone?"},
        {"id": "apn_datos", "pregunta": "Revisá el APN Android…"},
        {"id": "derivar_datos", "pregunta": "¿Te derivo?"},
    ]

    def _fake_iphone(*_a, **_k):
        return json.dumps(
            {
                "accion": "ask",
                "mensaje": (
                    "Si es un iPhone, ¿es modelo 11 en adelante o usás eSIM? "
                    "Para iPhone anteriores: Configuración > Datos celulares."
                ),
                "paso_cubierto": "so_dispositivo",
                "motivo": "ia",
            },
            ensure_ascii=False,
        )

    with patch("app.llm.chat_completion", side_effect=_fake_iphone):
        out = diagnosticar_turno(
            intencion="movil_datos",
            checklist=checklist,
            historial_mensajes=hist,
            mensaje_cliente="Es android, ya te dije que es un Moto g72",
            turnos_diagnostico=6,
            pasos_cubiertos=["datos_activados", "apn_datos"],
        )
    assert "iphone" not in (out.get("mensaje") or "").lower()
    assert "3g" not in (out.get("mensaje") or "").lower()
    assert out["motivo"] in (
        "bloqueado_apn_so_android",
        "bloqueado_repregunta_so",
    )
    assert _MSG_APN_ANDROID in (out.get("mensaje") or "") or _MSG_PACK_CHEQUEO in (
        out.get("mensaje") or ""
    )

    def _fake_3g(*_a, **_k):
        return json.dumps(
            {
                "accion": "ask",
                "mensaje": (
                    "¿Podrías cambiar el tipo de red preferida a 3G un momento "
                    "para probar si así navega?"
                ),
                "paso_cubierto": "apn_datos",
                "motivo": "ia",
            },
            ensure_ascii=False,
        )

    with patch("app.llm.chat_completion", side_effect=_fake_3g):
        out3 = diagnosticar_turno(
            intencion="movil_datos",
            checklist=checklist,
            historial_mensajes=hist,
            mensaje_cliente="Sigue igual, no navega",
            turnos_diagnostico=8,
            pasos_cubiertos=["datos_activados", "so_dispositivo", "apn_datos"],
        )
    assert "3g" not in (out3.get("mensaje") or "").lower()
    assert out3["motivo"] == "bloqueado_tipo_red_inventada"
    assert "pack" in (out3.get("mensaje") or "").lower()

    pack_txt = (
        "El inconveniente es que cargue un pack de datos, me dio el ok el sistema "
        "pero no los tengo disponibles"
    )
    assert pack_acreditado_sin_datos(pack_txt, hist) is True
    outp = diagnosticar_turno(
        intencion="movil_datos",
        checklist=checklist,
        historial_mensajes=hist,
        mensaje_cliente=pack_txt,
        turnos_diagnostico=2,
        pasos_cubiertos=["datos_activados", "apn_datos"],
    )
    assert outp["accion"] == "escalate"
    assert outp["motivo"] == "pack_acreditado_sin_datos"
    assert outp["mensaje"] == _MSG_PACK_ACREDITADO
    assert "iphone" not in outp["mensaje"].lower()
    assert "3g" not in outp["mensaje"].lower()


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


def test_negacion_adsl_en_fijo_no_cambia_tema_ni_clasifica_adsl():
    from app.domain.flujos_abonado import (
        es_cambio_tema_claro,
        refinar_intencion_internet,
        respuesta_negacion_adsl_en_fijo,
    )

    msg = "No, en esa línea no tengo ADSL"
    assert respuesta_negacion_adsl_en_fijo(msg) is True
    assert refinar_intencion_internet(msg) is None
    assert clasificar_intencion(msg) != "internet_adsl"
    assert es_cambio_tema_claro(msg, "telefono_fija", "") is None


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
    assert "pack" in datos.lower() or "bono acreditado" in datos.lower()
    assert "3G" in datos or "3g" in datos.lower()
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
    assert "N1 hogareño — repetidores WiFi domésticos" in by_title
    assert "N1 hogareño — plantillas respuesta conectividad" in by_title
    assert "media distancia" in by_title["N1 hogareño — repetidores WiFi domésticos"].lower()
    assert "30 segundos" in by_title["N1 hogareño — plantillas respuesta conectividad"]
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


def test_playbooks_wifi_repetidor_y_ftth_reinicio():
    from app.domain.flujos_abonado import PLAYBOOKS

    rep = next(p.pregunta for p in PLAYBOOKS["wifi"] if p.id == "repetidor_wifi")
    assert "repetidor" in rep.lower()
    ubic = next(p.pregunta for p in PLAYBOOKS["wifi"] if p.id == "repetidor_ubicacion")
    assert "medio camino" in ubic.lower() or "más cerca" in ubic.lower()
    reinicio_ftth = next(p.pregunta for p in PLAYBOOKS["internet_ftth"] if p.id == "reinicio_ont")
    assert "3" in reinicio_ftth and "30" in reinicio_ftth
    rep_lento = next(p.pregunta for p in PLAYBOOKS["internet_lento"] if p.id == "repetidores_lento")
    assert "repetidor" in rep_lento.lower()


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
    assert "android" in apn_datos.lower()
    assert "iphone" not in apn_datos.lower()
    so = next(p for p in PLAYBOOKS["movil_datos"] if p.id == "so_dispositivo")
    assert "marca" in so.pregunta.lower() or "modelo" in so.pregunta.lower()
    assert "iphone" not in so.pregunta.lower()
    assert "3g" not in datos.lower()
    assert "pack" in datos.lower()
    assert "revisar la línea" in datos.lower() or "revisar la linea" in datos.lower()
    robo = next(p.pregunta for p in PLAYBOOKS["movil"] if p.id == "robo_perdida_hint")
    assert "*910" in robo and "*303" in robo
    assert clasificar_intencion("quiero escuchar el correo de voz *333") == "movil_llamadas"
    assert clasificar_intencion("necesito activar la esim imowi") == "movil"
    assert clasificar_intencion("quiero dar de baja imowi") == "baja_servicio"


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
    assert "ov.batan" in informar or "oficina virtual" in informar
    assert "al instante" in informar or "instante" in informar
    assert "aviso" in informar
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


def test_segunda_insistencia_misma_frase_crea_ticket():
    """Repetir «quiero hablar con un agente» no es reiteración de síntoma: deriva."""
    token = _identified_portal()
    r1 = _portal_msg(token, "quiero hablar con un agente")
    assert not r1.get("ticket_id")
    r2 = _portal_msg(token, "quiero hablar con un agente")
    assert r2.get("ticket_id"), r2.get("respuesta")
    assert r2.get("estado") == "espera_agente"
    assert "escribí *agente*" not in (r1.get("respuesta") or "").lower()


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

    with Session() as db:
        r2 = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto="Pasame con un operador ya, no me anda internet",
            canal="whatsapp",
            usar_llama=False,
        )
    resp2 = (r2.get("respuesta") or "").lower()
    assert not r2.get("ticket_id"), "1ª insistencia con síntoma no abre N2 fibra"
    assert "no figura" in resp2 or "operador" in resp2 or "móvil" in resp2 or "movil" in resp2
    # No repetir literalmente el mismo copy del primer aviso
    assert resp2 != resp

    with Session() as db:
        r3 = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto="Pasame con un operador ya, no me anda internet",
            canal="whatsapp",
            usar_llama=False,
        )
    # 2ª pedido de humano tras el aviso → handoff (no loop)
    assert r3.get("ticket_id") or "agente" in (r3.get("respuesta") or "").lower()
    assert (r3.get("respuesta") or "").lower() != resp2


def test_menu_sintoma_datos_mdp_entra_movil_sin_no_te_entendi():
    """Jorge: «No tengo datos en Mar del Plata» no debe quedar en «No te entendí»."""
    from sqlalchemy import select

    from app.estate import canal_repo as crepo
    from app.estate.database import get_session_factory
    from app.estate.models import Abonado, ConversacionCanal, Organization
    from app.services.canal_abonado import procesar_mensaje_entrante

    tel = "5492235599992"
    frase = "No tengo datos en Mar del Plata"
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
            db, org_id, telefono=tel, texto=frase, canal="whatsapp", usar_llama=False
        )
    assert r0.get("estado") == "bot"
    resp0 = (r0.get("respuesta") or "").lower()
    assert "no te entendí" not in resp0
    # Salta menú o entra a datos móviles
    assert r0.get("intencion") in ("movil", "movil_datos", None) or "dato" in resp0 or "apn" in resp0 or "móvil" in resp0 or "movil" in resp0 or "avion" in resp0 or "avión" in resp0

    # Si quedó en menú (caso borde), la reiteración también debe entenderse
    with Session() as db:
        r1 = procesar_mensaje_entrante(
            db, org_id, telefono=tel, texto=frase, canal="whatsapp", usar_llama=False
        )
    assert "no te entendí" not in (r1.get("respuesta") or "").lower()


def test_si_tengo_tras_reinicio_no_abre_n2_movil():
    """Jorge: tras reinicio/señal, «si tengo» no abre ticket N2 prematuro."""
    from sqlalchemy import select

    from app.domain.flujos_abonado import (
        acepta_derivacion_clara,
        es_afirmacion_estado_movil,
    )
    from app.estate import canal_repo as crepo
    from app.estate.database import get_session_factory
    from app.estate.models import Abonado, ConversacionCanal, Organization
    from app.services.canal_abonado import procesar_mensaje_entrante
    from app.services.diagnostico_n1 import diagnosticar_turno

    assert es_afirmacion_estado_movil("si tengo") is True
    assert acepta_derivacion_clara("si tengo") is False
    assert acepta_derivacion_clara("sí, derivame") is True

    out = diagnosticar_turno(
        intencion="movil_datos",
        checklist=[
            {"id": "datos_activados", "pregunta": "¿Datos prendidos?"},
            {"id": "consumo_paquete", "pregunta": "¿Pack?"},
            {"id": "derivar_datos", "pregunta": "¿Te derivo?"},
        ],
        historial_mensajes=[
            {"autor": "cliente", "texto": "No tengo datos en Mar del Plata"},
            {"autor": "bot", "texto": "Reiniciá el teléfono. ¿Tenés señal de datos?"},
        ],
        mensaje_cliente="si tengo",
        turnos_diagnostico=3,
        pasos_cubiertos=["datos_activados"],
    )
    assert out["accion"] != "escalate", out
    assert out.get("motivo") != "pack_acreditado_sin_datos"

    tel = "5492235599993"
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        assert org
        abo = db.scalar(select(Abonado).where(Abonado.dni == "32123456"))
        assert abo is not None
        abo.servicio = "movil"
        abo.deuda_monto = "0"
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
        crepo.set_contexto(
            conv,
            {
                "saludo": True,
                "intencion": "movil_datos",
                "paso_idx": 6,  # derivar_datos
                "diag_turnos": 3,
                "pasos_cubiertos": [
                    "datos_activados",
                    "consumo_paquete",
                    "so_dispositivo",
                    "apn_datos",
                ],
            },
        )
        db.commit()
        org_id = org.id

    with Session() as db:
        r = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto="si tengo",
            canal="whatsapp",
            usar_llama=False,
        )
    assert not r.get("ticket_id"), r.get("respuesta")
    assert r.get("estado") == "bot"
    resp = (r.get("respuesta") or "").lower()
    assert "generé" not in resp and "genere" not in resp
    assert "ibot-" not in resp
    assert "espera_agente" not in (r.get("estado") or "")


def test_si_gracias_tras_bono_cierra_sin_repetir():
    from app.services.canal_abonado import _cliente_desiste_o_resuelto
    from app.services.diagnostico_n1 import aplicar_guardrails_movil, diagnosticar_turno

    assert _cliente_desiste_o_resuelto("si gracias") is True
    hist = [{"autor": "cliente", "texto": "Se me acabaron los datos del abono"}]
    g = aplicar_guardrails_movil(
        mensaje="x",
        mensaje_cliente="si gracias",
        historial_mensajes=hist,
        pasos_cubiertos=["consumo_paquete"],
        accion="ask",
    )
    assert g["accion"] == "resolved"
    assert "ov.batan" not in (g["mensaje"] or "").lower() or "quedamos" in (
        g["mensaje"] or ""
    ).lower()

    out = diagnosticar_turno(
        intencion="movil_datos",
        checklist=[{"id": "consumo_paquete", "pregunta": "pack?"}],
        historial_mensajes=hist,
        mensaje_cliente="si gracias",
        turnos_diagnostico=2,
        pasos_cubiertos=["consumo_paquete"],
        forzar_agente=False,
    )
    assert out["accion"] == "resolved"
    assert "comprá un bono" not in (out.get("mensaje") or "").lower()


def test_elige_pago_entiende_sigamos():
    from app.services.canal_abonado import _elige_pago_o_tecnico

    assert _elige_pago_o_tecnico("sigamos") == "tecnico"
    assert _elige_pago_o_tecnico("sigamos con el diagnostico") == "tecnico"
    assert _elige_pago_o_tecnico("seguimos") == "tecnico"


def test_datos_agotados_bono_no_ticket_por_modelo():
    from app.services.diagnostico_n1 import (
        aplicar_guardrails_movil,
        datos_agotados_abono,
        es_solo_modelo_celular,
        sanitizar_apn_en_texto,
    )

    hist = [{"autor": "cliente", "texto": "Se me acabaron los datos del abono"}]
    assert datos_agotados_abono("moto g72", hist) is True
    assert es_solo_modelo_celular("moto g72") is True
    g = aplicar_guardrails_movil(
        mensaje="¿Querés que te derive?",
        mensaje_cliente="moto g72",
        historial_mensajes=hist,
        pasos_cubiertos=[],
        accion="escalate",
    )
    assert g["accion"] == "ask"
    assert "ov.batan" in (g["mensaje"] or "").lower()
    assert "ticket" not in (g["mensaje"] or "").lower()
    assert "apn1.catel.org.ar" in sanitizar_apn_en_texto(
        "APN internet.coopbatan.ar"
    )


def test_flujo_acabaron_datos_sigamos_sin_n2():
    """Jorge: se acabaron datos → deuda → sigamos → bono OV; moto no abre ticket."""
    from sqlalchemy import select

    from app.estate import canal_repo as crepo
    from app.estate.database import get_session_factory
    from app.estate.models import Abonado, ConversacionCanal, Organization
    from app.services.canal_abonado import procesar_mensaje_entrante

    tel = "5492235587771"
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        assert org
        abo = db.scalar(select(Abonado).where(Abonado.dni == "32123456"))
        assert abo is not None
        abo.servicio = "movil"
        abo.deuda_monto = "55779.99"
        abo.estado = "activo"
        for c in db.scalars(
            select(ConversacionCanal).where(ConversacionCanal.telefono.contains(tel[-10:]))
        ).all():
            c.estado = "cerrado"
            c.contexto_json = "{}"
            c.ticket_id = ""
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
            db, org_id, telefono=tel, texto="hola", canal="whatsapp", usar_llama=False
        )
    assert not r0.get("ticket_id")

    with Session() as db:
        r1 = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto="Se me acabaron los datos del abono",
            canal="whatsapp",
            usar_llama=False,
        )
    assert r1.get("intencion") == "aviso_deuda"
    assert not r1.get("ticket_id")

    with Session() as db:
        r2 = procesar_mensaje_entrante(
            db, org_id, telefono=tel, texto="sigamos", canal="whatsapp", usar_llama=False
        )
    assert r2.get("intencion") != "aviso_deuda" or "ov.batan" in (
        r2.get("respuesta") or ""
    ).lower()
    assert "no te entendí" not in (r2.get("respuesta") or "").lower()
    assert "decime cuál preferís" not in (r2.get("respuesta") or "").lower()
    assert not r2.get("ticket_id")
    assert "ov.batan" in (r2.get("respuesta") or "").lower()

    with Session() as db:
        r3 = procesar_mensaje_entrante(
            db, org_id, telefono=tel, texto="moto g72", canal="whatsapp", usar_llama=False
        )
    assert not r3.get("ticket_id"), r3.get("respuesta")
    assert "generé el ticket" not in (r3.get("respuesta") or "").lower()
    assert "internet.coopbatan" not in (r3.get("respuesta") or "").lower()


def test_aviso_deuda_informar_pago_no_repite_eleccion():
    """Jorge: aviso deuda → quiere avisar que pagó → N1 informar, no loop pago/técnico."""
    from sqlalchemy import select

    from app.estate import canal_repo as crepo
    from app.estate.database import get_session_factory
    from app.estate.models import Abonado, ConversacionCanal, Organization
    from app.services.canal_abonado import procesar_mensaje_entrante

    tel = "5492235587772"
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        assert org
        abo = db.scalar(select(Abonado).where(Abonado.dni == "32123456"))
        assert abo is not None
        abo.servicio = "movil"
        abo.deuda_monto = "55779.99"
        for c in db.scalars(
            select(ConversacionCanal).where(ConversacionCanal.telefono.contains(tel[-10:]))
        ).all():
            c.estado = "cerrado"
            c.contexto_json = "{}"
            c.ticket_id = ""
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
        procesar_mensaje_entrante(
            db, org_id, telefono=tel, texto="hola", canal="whatsapp", usar_llama=False
        )
        r1 = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto="Se me acabaron los datos del abono",
            canal="whatsapp",
            usar_llama=False,
        )
        assert r1.get("intencion") == "aviso_deuda"
        r2 = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto="Hola quiero avisar que pague recien",
            canal="whatsapp",
            usar_llama=False,
        )
    resp = (r2.get("respuesta") or "").lower()
    assert r2.get("intencion") == "facturacion_informar_pago"
    assert "ov.batan.coop" in resp
    assert "aviso-de-pago" in resp or "aviso de pago" in resp
    assert "no hace falta avisar" not in resp
    assert "decime cuál preferís" not in resp
    assert not r2.get("ticket_id")


def test_visitante_portal_deriva_sin_ticket_n2():
    """Guest: cola baja sin ticket N2; si pregunta cómo pagar, FAQ pública (QR/OV)."""
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
    assert "ov.batan.coop" in resp
    assert "fiserv" in resp or "qr" in resp
    assert "ya está derivado" not in resp and "ya esta derivado" not in resp


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
    assert _extraer_dni("12.345.678") == "12345678"
    assert _extraer_dni("mi dni es 12.345.678") == "12345678"
    assert _es_solo_dni("corte desde el 10/08/2024 y no anda") is False


def test_audio_pendiente_pago_no_sigue_diagnostico_tecnico():
    """Tras PPPoE, audio «todavía no pagué» (mal transcrito) → corte_deuda, no fibra/radio."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.estate.models import Abonado
    from app.services.canal_abonado import _aplicar_diagnostico_ia

    abo = Abonado(
        organizacion_id="x",
        dni="30111222",
        nombre="JORGE TEST",
        estado="activo",
        deuda_monto="0",
        servicio="internet",
    )
    conv = SimpleNamespace(id="c1", canal="whatsapp", ticket_id="", estado="bot")
    ctx = {"intencion": "internet", "pppoe_informado": True, "diag_turnos": 1}
    sent: list[str] = []

    monkeypatch = __import__("pytest").MonkeyPatch()
    monkeypatch.setattr(
        "app.services.canal_abonado.resolve_canal_diagnostico_ia",
        lambda _db: True,
    )
    monkeypatch.setattr(
        "app.services.canal_abonado._enviar_respuesta",
        lambda db, org_id, conv, resp, **_k: sent.append(resp) or resp,
    )
    monkeypatch.setattr(
        "app.services.canal_abonado.crepo.set_contexto",
        lambda _c, _ctx: None,
    )
    try:
        raw = "Lo que pasa es que todo bien nos pague y no sé si si me lo cortaron"
        from app.services.transcription import normalizar_texto_audio_stt

        texto = normalizar_texto_audio_stt(raw)
        out = _aplicar_diagnostico_ia(
            MagicMock(),
            "org",
            conv,
            abo,
            texto,
            canal="whatsapp",
            ctx=ctx,
            intencion="internet",
            usar_llama=True,
        )
    finally:
        monkeypatch.undo()

    assert out is not None
    assert out.get("intencion") == "facturacion"
    low = (sent[0] if sent else "").lower()
    assert "no hace falta" in low or "no tenés deuda" in low
    assert "ov.batan.coop/#/pagar" not in low
    assert "fibra óptica" not in low and "cajita blanca" not in low


def test_wifi_parcial_no_cierra_resuelto():
    token = _identified_portal()
    _portal_msg(token, "El WiFi no llega a la habitación del fondo")
    data = _portal_msg(token, "En el living anda bien, lejos no")
    assert data.get("estado") != "cerrado"
    resp = (data.get("respuesta") or "").lower()
    assert "quedó resuelto" not in resp
    assert "quedo resuelto" not in resp
    assert "genial" not in resp or "lejos" in resp or "wifi" in resp or "router" in resp


def test_confirmacion_mejora_repetidor_no_es_cierre_ni_triaje_fibra():
    """Screenshot: «Eso me va a solucionar el problema» = confirmación, no cierre."""
    import json
    from unittest.mock import patch

    from sqlalchemy import select

    from app.domain.flujos_abonado import (
        indica_resuelto,
        mensaje_confirmacion_mejora_senal_wifi,
        pregunta_confirmacion_mejora_senal_wifi,
    )
    from app.estate import canal_repo as crepo
    from app.estate.database import get_session_factory
    from app.estate.models import Abonado, ConversacionCanal, Organization
    from app.services.canal_abonado import procesar_mensaje_entrante
    from app.services.diagnostico_n1 import diagnosticar_turno

    msg = (
        "Claro, ahora estoy viendo la señal con un poco más de potencia, "
        "porque veo más rayitas. Eso me va a solucionar el problema."
    )
    hist = [
        {"autor": "cliente", "texto": "El WiFi no anda en la cocina"},
        {
            "autor": "bot",
            "texto": (
                "Entiendo, esa rayita indica que la señal que recibe el repetidor "
                "es muy débil. ¿Podrías mover el repetidor más cerca del router?"
            ),
        },
        {
            "autor": "cliente",
            "texto": "Ok, lo moví y ahí mejora la señal del repetidor",
        },
        {
            "autor": "bot",
            "texto": (
                "Buenísimo. Avisame cuando lo pruebes, "
                "¿te anda bien el Wi-Fi ahora en el televisor?"
            ),
        },
    ]
    assert indica_resuelto(msg) is False
    assert pregunta_confirmacion_mejora_senal_wifi(msg, hist, intencion="wifi") is True
    assert "repetidor" in mensaje_confirmacion_mejora_senal_wifi(msg, hist).lower()
    assert "cocina" in mensaje_confirmacion_mejora_senal_wifi(msg, hist).lower()

    def _fake_triaje_fibra(*_a, **_k):
        return json.dumps(
            {
                "accion": "ask",
                "mensaje": (
                    "Para ayudarte con internet, necesito saber qué tipo de conexión tenés: "
                    "¿fibra óptica (cable amarillo a una cajita blanca), radio/antena en el techo, "
                    "o ADSL por línea telefónica?"
                ),
                "paso_cubierto": "tipo_acceso",
                "motivo": "ia",
            },
            ensure_ascii=False,
        )

    with patch("app.llm.chat_completion", side_effect=_fake_triaje_fibra):
        out = diagnosticar_turno(
            intencion="wifi",
            checklist=[{"id": "zona_wifi", "pregunta": "¿WiFi en toda la casa?"}],
            historial_mensajes=hist,
            mensaje_cliente=msg,
            turnos_diagnostico=3,
            pasos_cubiertos=["zona_wifi", "conexion_cableada"],
        )
    assert out["motivo"] == "confirmacion_mejora_senal_wifi"
    assert "fibra" not in (out.get("mensaje") or "").lower()
    assert "adsl" not in (out.get("mensaje") or "").lower()
    assert "repetidor" in (out.get("mensaje") or "").lower()

    tel = "5492235599994"
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        assert org
        abo = db.scalar(select(Abonado).where(Abonado.dni == "30111222"))
        assert abo is not None
        for c in db.scalars(
            select(ConversacionCanal).where(
                ConversacionCanal.telefono.contains(tel[-10:])
            )
        ).all():
            c.estado = "cerrado"
            c.contexto_json = "{}"
            c.ticket_id = ""
            c.agente_id = ""
        db.commit()
        conv = crepo.get_or_create_conversacion(
            db, org.id, telefono=tel, canal="whatsapp", wa_id=tel
        )
        conv.estado = "bot"
        conv.abonado_id = abo.id
        for h in hist:
            direccion = "in" if h["autor"] == "cliente" else "out"
            crepo.add_mensaje(
                db,
                org.id,
                conv.id,
                direccion=direccion,
                autor=h["autor"],
                texto=h["texto"],
            )
        crepo.set_contexto(
            conv,
            {
                "saludo": True,
                "intencion": "wifi",
                "paso_idx": 2,
                "diag_turnos": 3,
                "pasos_cubiertos": ["zona_wifi", "conexion_cableada"],
            },
        )
        db.commit()
        r = procesar_mensaje_entrante(
            db,
            org.id,
            telefono=tel,
            texto=msg,
            canal="whatsapp",
            usar_llama=False,
        )
    resp = (r.get("respuesta") or "").lower()
    assert r.get("estado") != "cerrado"
    assert "fibra" not in resp
    assert "adsl" not in resp
    assert "cajita blanca" not in resp
    assert "antena en el techo" not in resp
    assert "repetidor" in resp or "probá" in resp or "probá conectarte" in resp


def test_radio_por_aire_no_repite_triaje_fibra_adsl():
    """Regresión Jorge: «es por aire» + INALAMBRICO en historial → no repetir triaje."""
    import json
    from unittest.mock import patch

    from app.services.diagnostico_n1 import diagnosticar_turno

    hist = [
        {
            "autor": "bot",
            "texto": (
                "Revisé tu cuenta de ACCESO INTERNET INALAMBRICO: la conexión está activa "
                "(IP 181.41.253.219, hace 6 h). ¿No te anda en ningún dispositivo o solo por Wi‑Fi?"
            ),
        },
        {
            "autor": "cliente",
            "texto": "internet. Estamos desde el sábado con cortes permanentes de señal",
        },
        {"autor": "cliente", "texto": "en todos lados, se cae la señal permanente"},
    ]
    msg = "es por aire"

    def _fake_triaje_repetido(*_a, **_k):
        return json.dumps(
            {
                "accion": "ask",
                "mensaje": (
                    "Para ayudarte con internet, necesito saber qué tipo de conexión tenés: "
                    "¿fibra óptica (cable amarillo a una cajita blanca), radio/antena en el techo, "
                    "o ADSL por línea telefónica?"
                ),
                "paso_cubierto": "tipo_acceso",
                "motivo": "ia",
            },
            ensure_ascii=False,
        )

    with patch("app.llm.chat_completion", side_effect=_fake_triaje_repetido):
        out = diagnosticar_turno(
            intencion="internet_intermitente",
            checklist=[{"id": "frecuencia_cortes", "pregunta": "¿Cada cuánto se corta?"}],
            historial_mensajes=hist,
            mensaje_cliente=msg,
            turnos_diagnostico=4,
            pasos_cubiertos=["alcance_cortes", "medio_conexion"],
        )
    assert out["motivo"] == "bloqueado_triaje_tipo_acceso_repetido"
    low = (out.get("mensaje") or "").lower()
    assert "antena" in low or "inalámbric" in low
    assert "fibra óptica" not in low
    assert "adsl" not in low


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


def test_guardrail_cambio_clave_wifi_no_pide_password_en_chat():
    from app.services.diagnostico_n1 import (
        aplicar_guardrails_cambio_clave_wifi,
        mensaje_guia_cambio_clave_wifi,
        pide_nueva_clave_wifi_en_chat,
    )

    assert pide_nueva_clave_wifi_en_chat(
        "Pasame la nueva clave que querés poner en el WiFi"
    )
    assert pide_nueva_clave_wifi_en_chat("¿Cuál es la clave nueva que querés usar?")
    assert not pide_nueva_clave_wifi_en_chat(
        "En la etiqueta del módem/router están el nombre y la clave de fábrica. "
        "¿Tenés acceso al equipo para cambiarla?"
    )

    g = aplicar_guardrails_cambio_clave_wifi(
        mensaje="Dale, mandame la nueva contraseña y la cambio",
        mensaje_cliente="la clave",
        intencion="cambio_clave_wifi",
    )
    assert g["motivo"] == "bloqueado_pedido_clave_wifi"
    assert "etiqueta" in g["mensaje"].lower() or "módem" in g["mensaje"].lower()
    assert "pasame" not in g["mensaje"].lower()

    g2 = aplicar_guardrails_cambio_clave_wifi(
        mensaje="¿Tenés acceso al equipo?",
        mensaje_cliente="4645555",
        intencion="cambio_clave_wifi",
    )
    assert g2["motivo"] == "bloqueado_clave_wifi_en_chat"
    assert "otro dni" not in g2["mensaje"].lower()
    assert mensaje_guia_cambio_clave_wifi() in g2["mensaje"] or "reconect" in g2[
        "mensaje"
    ].lower()


def test_cambio_clave_wifi_numero_no_es_otro_dni():
    """Regresión: tras cambio_clave_wifi, un número tipo clave no dispara «otro DNI»."""
    from sqlalchemy import select

    from app.estate import canal_repo as crepo
    from app.estate.database import get_session_factory
    from app.estate.models import Abonado, ConversacionCanal, Organization
    from app.services.canal_abonado import procesar_mensaje_entrante

    tel = "5492235599917"
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        assert org
        abo = db.scalar(select(Abonado).where(Abonado.dni == "30111222"))
        assert abo is not None
        abo.servicio = "internet,movil"
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
                "identificado": True,
                "intencion": "cambio_clave_wifi",
                "paso_idx": 0,
                "diag_turnos": 1,
                "pasos_cubiertos": ["cambio_clave_wifi_detalle"],
            },
        )
        db.commit()
        org_id = org.id

    with Session() as db:
        r0 = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto="quiero cambiar la clave del wifi",
            canal="whatsapp",
            usar_llama=False,
        )
    assert r0.get("estado") == "bot"
    assert r0.get("intencion") == "cambio_clave_wifi"
    resp0 = (r0.get("respuesta") or "").lower()
    assert "otro dni" not in resp0
    assert "otra titularidad" not in resp0
    # No pedir que envíen la clave por chat
    assert "pasame la" not in resp0
    assert "nueva clave" not in resp0 or "etiqueta" in resp0 or "módem" in resp0 or "modem" in resp0

    with Session() as db:
        r1 = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto="la clave",
            canal="whatsapp",
            usar_llama=False,
        )
    assert r1.get("estado") == "bot"
    assert "otro dni" not in (r1.get("respuesta") or "").lower()
    assert "otra titularidad" not in (r1.get("respuesta") or "").lower()

    with Session() as db:
        r2 = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto="4645555",
            canal="whatsapp",
            usar_llama=False,
        )
    assert r2.get("estado") == "bot"
    assert r2.get("intencion") == "cambio_clave_wifi"
    assert not r2.get("ticket_id")
    resp2 = (r2.get("respuesta") or "").lower()
    assert "otro dni" not in resp2
    assert "otra titularidad" not in resp2
    assert "padrón" not in resp2 and "padron" not in resp2
    # Guía auto-servicio en el equipo + reconexión
    assert any(
        k in resp2
        for k in ("etiqueta", "módem", "modem", "router", "equipo", "reconect")
    )
    assert "pasame la nueva" not in resp2
    assert "mandame la" not in resp2


def test_cambio_tema_factura_sensa_datos_sin_ticket():
    """Regresión prod: factura → Sensa → datos abono no debe abrir N2 por «confusión»."""
    from sqlalchemy import select

    from app.estate import canal_repo as crepo
    from app.estate.database import get_session_factory
    from app.estate.models import Abonado, ConversacionCanal, Organization
    from app.services.canal_abonado import procesar_mensaje_entrante

    tel = "5492235581043"
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        assert org
        abo = db.scalar(select(Abonado).where(Abonado.dni == "30111222"))
        assert abo is not None
        abo.servicio = "internet,movil,tv"
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
                "identificado": True,
                "saludo": True,
                "intencion": "",
                "paso_idx": 0,
                "diag_turnos": 0,
                "pasos_cubiertos": [],
            },
        )
        db.commit()
        org_id = org.id

    with Session() as db:
        r1 = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto="Necesito la factura del mes pasado",
            canal="whatsapp",
            usar_llama=False,
        )
    assert not r1.get("ticket_id")
    assert "generé el ticket" not in (r1.get("respuesta") or "").lower()
    assert str(r1.get("intencion") or "").startswith("facturacion") or "factura" in (
        r1.get("respuesta") or ""
    ).lower() or "ov.batan" in (r1.get("respuesta") or "").lower()

    with Session() as db:
        r2 = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto="No anda Sensa en la smart tv",
            canal="whatsapp",
            usar_llama=False,
        )
    assert not r2.get("ticket_id")
    assert "generé el ticket" not in (r2.get("respuesta") or "").lower()
    assert r2.get("intencion") == "tv_sensa"
    resp2 = (r2.get("respuesta") or "").lower()
    assert "smart" in resp2 or "decodificador" in resp2 or "sensa" in resp2 or "tv" in resp2

    with Session() as db:
        r3 = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto="Se me acabaron los datos del abono",
            canal="whatsapp",
            usar_llama=False,
        )
    assert not r3.get("ticket_id"), r3.get("respuesta")
    resp3 = (r3.get("respuesta") or "").lower()
    assert "generé el ticket" not in resp3
    assert "hace falta un agente" not in resp3
    assert r3.get("intencion") == "movil_datos"
    assert "ov.batan" in resp3
    assert any(k in resp3 for k in ("bono", "datos del abono", "abono"))


def test_baja_con_deuda_no_empuja_pago_ni_diagnostico():
    """Karina: baja internet+Sensa con deuda → comercial, no QR ni triaje técnico."""
    from sqlalchemy import select

    from app.estate import canal_repo as crepo
    from app.estate.database import get_session_factory
    from app.estate.models import Abonado, ConversacionCanal, Organization
    from app.services.canal_abonado import procesar_mensaje_entrante

    tel = "5492235560100"
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        assert org
        abo = db.scalar(select(Abonado).where(Abonado.dni == "34964560"))
        if abo is None:
            abo = Abonado(
                organizacion_id=org.id,
                dni="34964560",
                telefono_e164=tel,
                nombre="Karina Da Silva",
                servicio="ambos",
                estado="activo",
                deuda_monto="254393.06",
                plan="Ecolan 50Mb + Sensa",
                linea_msisdn="2235560100",
            )
            db.add(abo)
            db.commit()
            db.refresh(abo)
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
        crepo.set_contexto(conv, {"saludo": True, "identificado": True})
        db.commit()
        org_id = org.id

    with Session() as db:
        r = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto="Quiero dar de baja todo el internet la aplicación sensa todo",
            canal="whatsapp",
            usar_llama=False,
        )
    assert r.get("intencion") == "baja_servicio"
    resp = (r.get("respuesta") or "").lower()
    assert "diagnóstico de internet" not in resp and "diagnostico de internet" not in resp
    assert "qr fiserv" not in resp
    assert "baja" in resp
    assert "deuda" in resp or "saldo" in resp

    with Session() as db:
        r2 = procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto="Saque todo xq se fue demaciado mucho para pagar",
            canal="whatsapp",
            usar_llama=False,
        )
    resp2 = (r2.get("respuesta") or "").lower()
    assert "qr fiserv" not in resp2
    assert "no reconocés" not in resp2 and "no reconoces" not in resp2
    assert r2.get("intencion") in ("baja_servicio", "aviso_deuda")
