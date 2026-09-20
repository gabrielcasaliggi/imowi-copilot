"""Regresiones de continuidad conversacional (auditoría Eko T70 / T46).

Principio: hechos y pasos_cubiertos son conocimiento adquirido.
paso_idx es solo un cursor; nunca debe invalidar un hecho ya conocido.
"""

from __future__ import annotations

from sqlalchemy import select

from app.domain.flujos_abonado import MSG_WIFI_SIN_CABLE_MOVIL, PLAYBOOKS
from app.estate import canal_repo as crepo
from app.estate.database import get_session_factory
from app.estate.models import Abonado, ConversacionCanal, Organization
from app.services.canal_abonado import procesar_mensaje_entrante
from app.services.platform_settings import playbooks_as_pasos

_DNI = "30111222"
_CANAL = "whatsapp"
_MSG_TABLET_CABLE = "como conecto la tablet por cable de red?"
_MSG_COMERCIAL = "Sí, pasame con comercial por favor"
_REITERACION = "para seguir, necesito ese dato"
_PREGUNTA_REINICIO = "¿reiniciaste el router"


def _wifi_paso_idx(paso_id: str) -> int:
    ids = [p.id for p in PLAYBOOKS["wifi"]]
    return ids.index(paso_id)


def _pasos_runtime(nombre: str):
    Session = get_session_factory()
    with Session() as db:
        pb = playbooks_as_pasos(db)
    return list(pb.get(nombre) or PLAYBOOKS.get(nombre) or [])


def _idx_paso(pasos, paso_id: str) -> int:
    return [p.id for p in pasos].index(paso_id)


def _abrir_hilo(tel: str, *, ctx: dict | None = None, historial_bot: str = "") -> str:
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        assert org
        abo = db.scalar(select(Abonado).where(Abonado.dni == _DNI))
        assert abo is not None
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
            db, org.id, telefono=tel, canal=_CANAL, wa_id=tel
        )
        conv.estado = "bot"
        conv.abonado_id = abo.id
        conv.ticket_id = ""
        base = {
            "saludo": True,
            "identificado": True,
            "dni": _DNI,
        }
        if ctx:
            base.update(ctx)
        crepo.set_contexto(conv, base)
        if historial_bot:
            crepo.add_mensaje(
                db,
                org.id,
                conv.id,
                direccion="out",
                autor="bot",
                texto=historial_bot,
            )
        db.commit()
        return org.id


def _msg(org_id: str, tel: str, texto: str) -> dict:
    Session = get_session_factory()
    with Session() as db:
        return procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto=texto,
            canal=_CANAL,
            usar_llama=False,
        )


def _ctx(conv_id: str) -> dict:
    Session = get_session_factory()
    with Session() as db:
        conv = db.get(ConversacionCanal, conv_id)
        assert conv is not None
        return crepo.get_contexto(conv)


def test_t70_tablet_consulta_cable_no_avanza_a_reinicio():
    """T70: how-to de cable con tablet conocida no dispara reinicio_router_wifi.

    hechos ya cubren el dispositivo; paso_idx no puede sobreescribirlos.
    """
    tel = "5492235598701"
    paso_cable_ap = _wifi_paso_idx("repetidor_cable_ap")
    org_id = _abrir_hilo(
        tel,
        ctx={
            "intencion": "wifi",
            "paso_idx": paso_cable_ap,
            "diag_turnos": 6,
            "pasos_cubiertos": [
                "conexion_cableada",
                "otros_dispositivos_wifi",
                "zona_wifi",
            ],
            "hechos": {
                "dispositivo_afectado": "tablet",
                "dispositivo_sin_ethernet": True,
                "alcance_wifi": "uno",
                "zona_wifi": "baño",
            },
        },
        historial_bot=(
            "Si podés, conectar el repetidor al router con cable de red "
            "(modo Punto de Acceso) da mejor velocidad que repetir por WiFi. "
            "¿Lo probaste?"
        ),
    )
    r = _msg(org_id, tel, _MSG_TABLET_CABLE)
    resp = (r.get("respuesta") or "").lower()
    ctx = _ctx(r["conversacion_id"])
    hechos = ctx.get("hechos") or {}

    assert (r.get("intencion") or ctx.get("intencion")) == "wifi"
    assert _PREGUNTA_REINICIO not in resp
    assert "reiniciaste el router" not in resp
    assert int(ctx.get("paso_idx") or 0) != _wifi_paso_idx("reinicio_router_wifi")
    assert hechos.get("dispositivo_afectado") == "tablet"
    assert hechos.get("dispositivo_sin_ethernet") is True
    assert "conexion_cableada" in (ctx.get("pasos_cubiertos") or [])
    assert "otros_dispositivos_wifi" in (ctx.get("pasos_cubiertos") or [])
    assert "zona_wifi" in (ctx.get("pasos_cubiertos") or [])
    assert r.get("respuesta") == MSG_WIFI_SIN_CABLE_MOVIL
    assert ctx.get("ultima_diag_motivo") == "bloqueado_cable_en_dispositivo_movil"


def test_t70_tablet_conocida_luego_consulta_cable():
    """Tras 'en la table', el how-to de cable no pierde el hecho ni salta de paso."""
    tel = "5492235598702"
    org_id = _abrir_hilo(tel, ctx={"intencion": "general", "paso_idx": 0})
    r1 = _msg(org_id, tel, "no me anda el wifi en la table")
    ctx1 = _ctx(r1["conversacion_id"])
    hechos1 = ctx1.get("hechos") or {}
    assert hechos1.get("dispositivo_afectado") == "tablet"
    assert hechos1.get("dispositivo_sin_ethernet") is True
    paso_antes = int(ctx1.get("paso_idx") or 0)

    r2 = _msg(org_id, tel, _MSG_TABLET_CABLE)
    resp2 = (r2.get("respuesta") or "").lower()
    ctx2 = _ctx(r2["conversacion_id"])
    hechos2 = ctx2.get("hechos") or {}

    assert r2.get("intencion") == "wifi" or ctx2.get("intencion") == "wifi"
    assert hechos2.get("dispositivo_afectado") == "tablet"
    assert hechos2.get("dispositivo_sin_ethernet") is True
    assert _PREGUNTA_REINICIO not in resp2
    assert "reiniciaste el router" not in resp2
    assert "no se conectan por cable" in resp2
    assert int(ctx2.get("paso_idx") or 0) == paso_antes
    assert ctx2.get("ultima_diag_motivo") == "bloqueado_cable_en_dispositivo_movil"


def test_t46_comercial_repetido_es_idempotente():
    """Repetir 'pasame con comercial' no resetea a general ni dispara reiteracion_temprana."""
    tel = "5492235598703"
    paso_derivar = [p.id for p in PLAYBOOKS["alta_plan"]].index("derivar_comercial")
    org_id = _abrir_hilo(
        tel,
        ctx={
            "intencion": "alta_plan",
            "paso_idx": paso_derivar,
            "diag_turnos": 2,
            "pasos_cubiertos": ["tipo_alta", "zona_comercial"],
        },
        historial_bot="Te paso con comercial. ¿Te derivo?",
    )
    cubiertos_antes = ["tipo_alta", "zona_comercial"]

    r1 = _msg(org_id, tel, _MSG_COMERCIAL)
    ctx1 = _ctx(r1["conversacion_id"])
    assert "comercial" in (r1.get("respuesta") or "").lower()
    assert _REITERACION not in (r1.get("respuesta") or "").lower()

    r2 = _msg(org_id, tel, _MSG_COMERCIAL)
    resp2 = (r2.get("respuesta") or "").lower()
    ctx2 = _ctx(r2["conversacion_id"])

    assert ctx2.get("intencion") != "general"
    assert ctx2.get("intencion") == "alta_plan"
    assert list(ctx2.get("pasos_cubiertos") or []) == cubiertos_antes or set(
        ctx2.get("pasos_cubiertos") or []
    ) >= set(cubiertos_antes)
    assert int(ctx2.get("paso_idx") or 0) != 0
    assert _REITERACION not in resp2
    assert "¿en qué te ayudo" not in resp2
    assert "comercial" in resp2
    assert ctx1.get("contacto_comercial_ofrecido") or ctx2.get("contacto_comercial_ofrecido")


def test_t44_t46_cierre_comercial_persistente():
    """Aceptación comercial → estado persistente → repetición no cae a general+paso 0."""
    tel = "5492235598704"
    org_id = _abrir_hilo(tel, ctx={"intencion": "general", "paso_idx": 0})

    r0 = _msg(org_id, tel, "Quiero contratar internet fibra en Batán")
    assert r0.get("intencion") == "alta_plan" or _ctx(r0["conversacion_id"]).get(
        "intencion"
    ) == "alta_plan"

    _msg(org_id, tel, "Alta nueva de internet fibra en Batán")
    _msg(org_id, tel, "Alta nueva de internet fibra en Batán")

    r_ok = _msg(org_id, tel, _MSG_COMERCIAL)
    ctx_ok = _ctx(r_ok["conversacion_id"])
    paso_tras_aceptar = int(ctx_ok.get("paso_idx") or 0)
    cubiertos_tras_aceptar = list(ctx_ok.get("pasos_cubiertos") or [])
    assert "comercial" in (r_ok.get("respuesta") or "").lower()
    assert ctx_ok.get("intencion") != "general"
    assert _REITERACION not in (r_ok.get("respuesta") or "").lower()

    r_rep = _msg(org_id, tel, _MSG_COMERCIAL)
    ctx_rep = _ctx(r_rep["conversacion_id"])
    resp_rep = (r_rep.get("respuesta") or "").lower()

    assert ctx_rep.get("intencion") != "general"
    assert int(ctx_rep.get("paso_idx") or 0) != 0
    assert int(ctx_rep.get("paso_idx") or 0) == paso_tras_aceptar
    if cubiertos_tras_aceptar:
        assert list(ctx_rep.get("pasos_cubiertos") or []) == cubiertos_tras_aceptar
    assert _REITERACION not in resp_rep
    assert "¿en qué te ayudo" not in resp_rep
    assert "comercial" in resp_rep
    assert ctx_rep.get("contacto_comercial_ofrecido") is True


def test_pasos_cubiertos_omite_repregunta_wifi():
    """El cursor secuencial no debe volver a preguntar ids ya cubiertos."""
    tel = "5492235598711"
    pasos = _pasos_runtime("wifi")
    assert len(pasos) >= 3
    cubiertos = [pasos[0].id, pasos[1].id]
    org_id = _abrir_hilo(
        tel,
        ctx={
            "intencion": "wifi",
            "paso_idx": 0,
            "pasos_cubiertos": cubiertos,
        },
        historial_bot=pasos[0].pregunta,
    )
    r = _msg(org_id, tel, "baño")
    ctx = _ctx(r["conversacion_id"])
    cub = set(ctx.get("pasos_cubiertos") or [])
    cub_esperado = set(cubiertos) | {"zona_wifi"}
    for pid in cubiertos:
        assert pid in cub
    pendiente = next(i for i, p in enumerate(pasos) if p.id not in cub_esperado)
    assert int(ctx.get("paso_idx") or 0) == pendiente
    resp = (r.get("respuesta") or "").lower()
    frag_sig = (pasos[pendiente].pregunta or "").lower().split("?")[0][:24].strip()
    assert frag_sig in resp or "2.4" in resp or "5 ghz" in resp or "5ghz" in resp


def test_alcance_uno_tablet_no_rama_incompatible():
    """Replay H2: tablet + alcance uno no pide Ethernet ni extensor de toda la casa."""
    tel = "5492235598712"
    pasos = _pasos_runtime("wifi")
    org_id = _abrir_hilo(
        tel,
        ctx={"intencion": "wifi", "paso_idx": 0},
        historial_bot=pasos[0].pregunta if pasos else "¿El WiFi falla en toda la casa o solo lejos del router?",
    )
    r1 = _msg(org_id, tel, "en la table")
    ctx1 = _ctx(r1["conversacion_id"])
    hechos1 = ctx1.get("hechos") or {}
    resp1 = (r1.get("respuesta") or "").lower()
    assert hechos1.get("dispositivo_afectado") == "tablet"
    assert hechos1.get("alcance_wifi") == "uno"
    assert hechos1.get("dispositivo_sin_ethernet") is True
    assert "extensor" not in resp1
    assert "access point" not in resp1

    r2 = _msg(org_id, tel, "por los dos")
    ctx2 = _ctx(r2["conversacion_id"])
    hechos2 = ctx2.get("hechos") or {}
    resp2 = (r2.get("respuesta") or "").lower()
    assert hechos2.get("dispositivo_afectado") == "tablet"
    assert hechos2.get("alcance_wifi") == "uno"
    assert "conectando la tablet" not in resp2
    assert "cable de red" not in resp2 or "no se conectan por cable" in resp2
    assert "extensor" not in resp2
    assert "access point" not in resp2

    r3 = _msg(org_id, tel, "en la table")
    ctx3 = _ctx(r3["conversacion_id"])
    resp3 = (r3.get("respuesta") or "").lower()
    hechos3 = ctx3.get("hechos") or {}
    assert hechos3.get("dispositivo_afectado") == "tablet"
    assert hechos3.get("alcance_wifi") == "uno"
    assert "extensor" not in resp3
    assert "¿tenés repetidor" not in resp3


def test_howto_apn_no_avanza_playbook_movil():
    tel = "5492235598713"
    pasos = _pasos_runtime("movil_datos")
    paso_apn = _idx_paso(pasos, "apn_datos")
    cubiertos = [p.id for p in pasos[:paso_apn]]
    org_id = _abrir_hilo(
        tel,
        ctx={
            "intencion": "movil_datos",
            "paso_idx": paso_apn,
            "pasos_cubiertos": cubiertos,
        },
        historial_bot=pasos[paso_apn].pregunta,
    )
    r = _msg(org_id, tel, "¿Cómo configuro el APN?")
    resp = (r.get("respuesta") or "").lower()
    ctx = _ctx(r["conversacion_id"])
    assert ctx.get("intencion") == "movil_datos"
    assert int(ctx.get("paso_idx") or 0) == paso_apn
    assert "zona habitual" not in resp
    assert "apagá el wifi" not in resp and "apaga el wifi" not in resp
    assert "apn" in resp


def test_howto_fastcom_no_avanza_internet_lento():
    tel = "5492235598714"
    pasos = _pasos_runtime("internet_lento")
    paso = _idx_paso(pasos, "test_velocidad")
    cubiertos = [p.id for p in pasos[:paso]]
    org_id = _abrir_hilo(
        tel,
        ctx={
            "intencion": "internet_lento",
            "paso_idx": paso,
            "pasos_cubiertos": cubiertos,
        },
        historial_bot=pasos[paso].pregunta,
    )
    r = _msg(org_id, tel, "¿Cómo hago el test en fast.com?")
    resp = (r.get("respuesta") or "").lower()
    ctx = _ctx(r["conversacion_id"])
    assert ctx.get("intencion") == "internet_lento"
    assert int(ctx.get("paso_idx") or 0) == paso
    assert "cuánto te dio" not in resp
    assert "cuanto te dio" not in resp
    assert "70%" not in resp
    assert "windows" not in resp
    assert "actualización descargándose" not in resp
    assert "actualizacion descargandose" not in resp


def test_howto_sensa_no_avanza_playbook():
    tel = "5492235598715"
    pasos = _pasos_runtime("tv_sensa")
    paso = _idx_paso(pasos, "acciones_sensa")
    cubiertos = [p.id for p in pasos[:paso]]
    org_id = _abrir_hilo(
        tel,
        ctx={
            "intencion": "tv_sensa",
            "paso_idx": paso,
            "pasos_cubiertos": cubiertos,
        },
        historial_bot=pasos[paso].pregunta,
    )
    r = _msg(org_id, tel, "¿Cómo actualizo Sensa?")
    resp = (r.get("respuesta") or "").lower()
    ctx = _ctx(r["conversacion_id"])
    assert ctx.get("intencion") == "tv_sensa"
    assert int(ctx.get("paso_idx") or 0) == paso
    assert "abrimos el ticket" not in resp
    assert "¿querés que te derive" not in resp


def test_pon_los_refine_ftth_no_repregunta_luces():
    """H4: PON/LOS ya dicho sobrevive internet → internet_ftth y no reitera."""
    tel = "5492235598716"
    org_id = _abrir_hilo(
        tel,
        ctx={
            "intencion": "internet",
            "paso_idx": 0,
            "pasos_cubiertos": ["sintoma_internet", "alcance_internet"],
        },
        historial_bot=(
            "¿Tenés fibra (cajita blanca), antena en el techo, o internet por teléfono (ADSL)?"
        ),
    )
    r1 = _msg(org_id, tel, "La PON está verde y la LOS apagada")
    ctx1 = _ctx(r1["conversacion_id"])
    resp1 = (r1.get("respuesta") or "").lower()
    cub1 = list(ctx1.get("pasos_cubiertos") or [])
    assert ctx1.get("intencion") == "internet_ftth"
    assert any(pid in cub1 for pid in ("energia_ont", "luces_los", "luces_ont"))
    assert "luz pon" not in resp1
    assert "cajita blanca tiene luces" not in resp1
    assert _REITERACION not in resp1

    r2 = _msg(org_id, tel, "La PON está verde y la LOS apagada")
    ctx2 = _ctx(r2["conversacion_id"])
    resp2 = (r2.get("respuesta") or "").lower()
    cub2 = list(ctx2.get("pasos_cubiertos") or [])
    assert ctx2.get("intencion") == "internet_ftth"
    assert _REITERACION not in resp2
    assert "luz pon" not in resp2
    assert "cajita blanca tiene luces" not in resp2
    assert any(pid in cub2 for pid in ("energia_ont", "luces_los", "luces_ont"))


def test_reiteracion_real_sigue_pidiendo_dato_faltante():
    """Reiterar el síntoma sin responder el paso no debe saltarse el dato."""
    tel = "5492235598717"
    pasos = _pasos_runtime("wifi")
    org_id = _abrir_hilo(
        tel,
        ctx={
            "intencion": "wifi",
            "paso_idx": 0,
            "ultima_queja": "internet anda mal",
        },
        historial_bot=pasos[0].pregunta if pasos else (
            "¿El WiFi falla en toda la casa o solo lejos del router?"
        ),
    )
    r = _msg(org_id, tel, "Internet anda mal")
    resp = (r.get("respuesta") or "").lower()
    ctx = _ctx(r["conversacion_id"])
    assert ctx.get("intencion") == "wifi"
    assert int(ctx.get("paso_idx") or 0) == 0
    assert "toda la casa" in resp or "lejos del router" in resp
    assert "reiniciaste el router" not in resp


def test_factura_por_que_subio_no_es_pago():
    """H5: pregunta causal con saldo 0 / suspendido no es 'quiero pagar'."""
    tel = "5492235598718"
    Session = get_session_factory()
    with Session() as db:
        abo = db.scalar(select(Abonado).where(Abonado.dni == _DNI))
        assert abo is not None
        prev_estado, prev_deuda = abo.estado, abo.deuda_monto
        abo.estado = "suspendido"
        abo.deuda_monto = "0"
        db.commit()
    try:
        org_id = _abrir_hilo(tel, ctx={"paso_idx": 0})
        r = _msg(org_id, tel, "Me vino más cara la factura, por qué subió?")
        resp = (r.get("respuesta") or "").lower()
        ctx = _ctx(r["conversacion_id"])
        assert "/#/pagar" not in resp
        assert "qr fiserv" not in resp
        assert "abonar tu factura" not in resp
        assert ctx.get("intencion") in ("facturacion_reclamo", "facturacion")
        assert "mes" in resp or "monto" in resp
    finally:
        with Session() as db:
            abo = db.scalar(select(Abonado).where(Abonado.dni == _DNI))
            if abo is not None:
                abo.estado = prev_estado
                abo.deuda_monto = prev_deuda
                db.commit()


def test_siguiente_paso_pendiente_omite_cubiertos():
    from app.domain.flujos_abonado import siguiente_paso_pendiente

    pasos = PLAYBOOKS["wifi"]
    nxt = siguiente_paso_pendiente(
        pasos, 0, ["conexion_cableada", "otros_dispositivos_wifi"]
    )
    assert pasos[nxt].id == "repetidor_wifi"


def test_es_pregunta_howto_o_causal_patrones():
    from app.domain.flujos_abonado import es_pregunta_howto_o_causal

    assert es_pregunta_howto_o_causal("¿Cómo configuro el APN?") is True
    assert es_pregunta_howto_o_causal("¿Cómo hago el test en fast.com?") is True
    assert es_pregunta_howto_o_causal("¿Cómo actualizo Sensa?") is True
    assert es_pregunta_howto_o_causal("Me vino más cara la factura, por qué subió?") is True
    assert es_pregunta_howto_o_causal("Internet anda mal") is False
    assert es_pregunta_howto_o_causal("en la table") is False
    assert es_pregunta_howto_o_causal("sí") is False
    assert es_pregunta_howto_o_causal(
        "Claro, ahora estoy viendo la señal con un poco más de potencia, "
        "porque veo más rayitas. Eso me va a solucionar el problema."
    ) is False
