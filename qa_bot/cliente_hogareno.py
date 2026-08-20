"""Loop QA — cliente hogareño de internet (preguntar, escuchar, aprender, repregunta).

Simula un socio de la cooperativa con hechos ocultos: no vuelca el diagnóstico
de entrada; responde según lo que pregunta el bot. Mide tickets N2 evitables
vs. legítimos (óptica / N1 radio agotado).

Uso (in-process, API local TestClient — no pega a producción):

    .venv/bin/python -m qa_bot.cliente_hogareno
    .venv/bin/python -m qa_bot.cliente_hogareno --personas P01,P07
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


@dataclass
class Hechos:
    """Estado oculto del hogar. El socio solo lo dice si el bot pregunta."""

    tecnologia: str = ""  # ftth | radio | adsl
    reply_tecnologia: str = ""
    luces_ont: str = ""
    pon: str = ""  # verde | unknown
    los: str = ""  # apagada | roja
    reinicio_hecho: bool = False
    reinicio_resuelve: bool = False  # tras reinicio el servicio vuelve / se estabiliza
    cable_anda: bool | None = None
    wifi_zona: str = ""  # lejos | toda | ok
    n_equipos: int = 0
    horario: str = ""
    fast_com: str = ""
    poe_luz: bool | None = None
    vecinos_ok: bool | None = None
    apertura: str = ""
    tono: str = "vecino"  # vecino | malhumorado | typo | mayor
    # ADSL
    tono_fijo: bool | None = None
    filtro_ok: bool | None = None
    dsl_fija_tras_reinicio: bool | None = None
    # Clave WiFi
    quiere_clave: bool = False
    tiene_etiqueta: bool = False
    # Adulto mayor / WhatsApp
    sintoma_whatsapp: bool = False
    deuda_manana: bool = False
    # Intermitencia
    frecuencia_cortes: str = ""


@dataclass
class Persona:
    id: str
    nombre: str
    descripcion: str
    hechos: Hechos
    n2_esperado: str  # nunca | optica | post_n1_radio
    max_turnos: int = 10
    dni: str = "30111222"


@dataclass
class TurnoLoop:
    usuario: str
    respuesta: str
    estado: str = ""
    ticket_id: str = ""
    intencion: str = ""


@dataclass
class ResultadoPersona:
    persona_id: str
    nombre: str
    n2_esperado: str
    ticket_creado: bool
    ticket_id: str
    estado_final: str
    intencion_final: str
    turnos: int
    n2_evitable: bool
    n2_legitimo: bool
    ok: bool
    fallas: list[str] = field(default_factory=list)
    transcript: list[dict] = field(default_factory=list)


PERSONAS: list[Persona] = [
    Persona(
        id="P01",
        nombre="Fibra se me cortó",
        descripcion="ONT PON verde / LOS apagada; no reinició. N2 no.",
        n2_esperado="nunca",
        hechos=Hechos(
            tecnologia="ftth",
            reply_tecnologia="Tengo fibra, la cajita blanca",
            luces_ont="tiene luces",
            pon="verde",
            los="apagada",
            reinicio_hecho=False,
            cable_anda=None,
            apertura="Hola, se me cortó el internet en casa",
        ),
    ),
    Persona(
        id="P02",
        nombre="LOS roja",
        descripcion="Fibra dañada / LOS encendida. N2 visita óptica. No WiFi.",
        n2_esperado="optica",
        hechos=Hechos(
            tecnologia="ftth",
            reply_tecnologia="Es fibra, cajita blanca",
            luces_ont="hay una luz roja",
            pon="no se",
            los="roja",
            reinicio_hecho=True,
            cable_anda=False,
            apertura="No tengo internet, es fibra",
        ),
    ),
    Persona(
        id="P03",
        nombre="Solo WiFi",
        descripcion="Por cable anda; living OK, fondo no. N2 no.",
        n2_esperado="nunca",
        hechos=Hechos(
            tecnologia="ftth",
            reply_tecnologia="Fibra, sí",
            luces_ont="luces normales",
            pon="verde",
            los="apagada",
            reinicio_hecho=True,
            cable_anda=True,
            wifi_zona="lejos",
            apertura="El WiFi no llega a la habitación del fondo",
        ),
    ),
    Persona(
        id="P04",
        nombre="Lento en pico",
        descripcion="8 equipos, de noche, fast.com por cable OK. N2 no.",
        n2_esperado="nunca",
        hechos=Hechos(
            tecnologia="ftth",
            reply_tecnologia="Fibra",
            n_equipos=8,
            horario="a la noche",
            fast_com="da bien por cable, tipo 45 mega",
            cable_anda=True,
            wifi_zona="ok",
            apertura="Internet anda re lento desde ayer a la tarde",
        ),
    ),
    Persona(
        id="P05",
        nombre="Radio techo",
        descripcion="PoE OK, reinicio no alcanza. Ticket aceptable al agotar N1.",
        n2_esperado="post_n1_radio",
        max_turnos=12,
        hechos=Hechos(
            tecnologia="radio",
            reply_tecnologia="Tengo antena en el techo",
            poe_luz=True,
            reinicio_hecho=True,
            vecinos_ok=True,
            cable_anda=False,
            apertura="Se me cayó internet, tengo antena en el techo",
        ),
    ),
    Persona(
        id="P06",
        nombre="Typo coloquial",
        descripcion="interntt + fibra. No ticket prematuro.",
        n2_esperado="nunca",
        hechos=Hechos(
            tecnologia="ftth",
            reply_tecnologia="es fibraa la cajita blanca",
            luces_ont="si tiene luces",
            pon="verde",
            los="apagada",
            tono="typo",
            apertura="ola no anda el interntt, no me carga nadaa",
        ),
    ),
    Persona(
        id="P07",
        nombre="Pide humano de entrada",
        descripcion="Primero operador; el síntoma es internet. Menú/N1 antes de ticket.",
        n2_esperado="nunca",
        hechos=Hechos(
            tecnologia="ftth",
            reply_tecnologia="fibra",
            luces_ont="luces prendidas",
            pon="verde",
            los="apagada",
            apertura="Quiero hablar con una persona, pasame con un operador",
        ),
    ),
    Persona(
        id="P08",
        nombre="Reitera sigue igual",
        descripcion="Tras 1 solo paso, reitera. Reformular, no N2.",
        n2_esperado="nunca",
        max_turnos=4,
        hechos=Hechos(
            tecnologia="ftth",
            reply_tecnologia="fibra",
            apertura="No tengo internet",
        ),
    ),
    Persona(
        id="P09",
        nombre="Intermitencia estabiliza",
        descripcion="Cortes periódicos; cable OK; reinicio estabiliza. N2 no.",
        n2_esperado="nunca",
        hechos=Hechos(
            tecnologia="ftth",
            reply_tecnologia="Fibra",
            cable_anda=True,
            reinicio_resuelve=True,
            frecuencia_cortes="cada tanto, vuelve en unos minutos",
            apertura="Se me corta el internet a cada rato y después vuelve",
        ),
    ),
    Persona(
        id="P10",
        nombre="ADSL sync vuelve",
        descripcion="ADSL; microfiltro + reinicio → DSL fija. N2 no.",
        n2_esperado="nunca",
        hechos=Hechos(
            tecnologia="adsl",
            reply_tecnologia="Es por el teléfono, ADSL",
            tono_fijo=True,
            filtro_ok=True,
            reinicio_resuelve=True,
            dsl_fija_tras_reinicio=True,
            apertura="Se me cayó el internet, tengo ADSL por la línea del teléfono",
        ),
    ),
    Persona(
        id="P11",
        nombre="Cambio clave WiFi",
        descripcion="Quiere cambiar contraseña; tiene etiqueta; conecta. N2 no.",
        n2_esperado="nunca",
        hechos=Hechos(
            tecnologia="ftth",
            quiere_clave=True,
            tiene_etiqueta=True,
            apertura="Quiero cambiar la clave del WiFi",
        ),
    ),
    Persona(
        id="P12",
        nombre="Adulto mayor WhatsApp",
        descripcion="Línea OK; falla llamada WhatsApp; reinicio resuelve. N2 no.",
        n2_esperado="nunca",
        hechos=Hechos(
            tecnologia="ftth",
            reply_tecnologia="Fibra",
            tono="mayor",
            sintoma_whatsapp=True,
            deuda_manana=True,
            reinicio_resuelve=True,
            cable_anda=True,
            apertura="Hola, no me anda internet, soy mayor y no entiendo mucho",
        ),
    ),
]


def responder_como_cliente(
    pregunta_bot: str,
    persona: Persona,
    *,
    turno: int,
    ya_dijo_apertura: bool,
    ticket_ya: bool,
) -> str | None:
    """Genera el siguiente mensaje del socio. None = no hay más que decir."""
    if ticket_ya:
        return None
    if not ya_dijo_apertura:
        return persona.hechos.apertura

    h = persona.hechos
    q = (pregunta_bot or "").lower()

    if persona.id == "P08" and turno >= 1:
        return "Sigue igual, no tengo internet"

    if persona.id == "P07" and turno == 1:
        return "Es que no me anda internet"

    if persona.id == "P12" and turno == 1 and any(
        k in q for k in ("deuda", "saldo", "pagar", "pendiente")
    ):
        return "No, lo pago mañana, sigamos con el problema de internet"

    if h.sintoma_whatsapp and any(
        k in q for k in ("aparato", "dispositivo", "celular", "computadora", "tablet")
    ):
        return "En el celular, cuando lo llamo a mi hijo por WhatsApp"

    if h.sintoma_whatsapp and any(k in q for k in ("whatsapp", "wasap", "llamada", "falla")):
        return "Cuando lo llamo a veces no funciona el WhatsApp"

    if h.quiere_clave:
        if any(k in q for k in ("contraseña", "clave", "nombre de la red", "ssid", "las dos")):
            return "La contraseña del WiFi"
        if any(k in q for k in ("etiqueta", "acceso al equipo", "fábrica", "fabrica")):
            return "Sí, tengo la etiqueta abajo del router"
        if any(k in q for k in ("reconect", "probar", "dispositivo", "listo")):
            return "Listo, ya conecté el celular con la clave nueva y navega"
        if any(k in q for k in ("conectó", "conecto", "navega", "valid")):
            return "Sí, ya anda"

    # ADSL
    if h.tecnologia == "adsl" or any(k in q for k in ("adsl", "microfiltro", "splitter", "dsl", "sync", "tono")):
        if "tono" in q:
            return "Sí, el fijo tiene tono" if h.tono_fijo else "No tiene tono"
        if any(k in q for k in ("filtro", "splitter", "microfiltro")):
            return "Sí, el filtro está puesto" if h.filtro_ok else "No sé del filtro"
        if any(k in q for k in ("dsl", "sync", "parpade")):
            if h.dsl_fija_tras_reinicio and h.reinicio_hecho:
                return "Quedó fija la lucecita DSL y ya navego"
            return "Sigue parpadeando"
        if any(k in q for k in ("toma principal", "calle")):
            return "Sí, lo probé en la toma de la calle"

    # Intermitencia
    if any(k in q for k in ("cada cuánto", "cada cuanto", "frecuencia", "cuánto tarda", "cuanto tarda")):
        return h.frecuencia_cortes or "Cada tanto, unos minutos"

    if any(k in q for k in ("se corta por", "por wifi", "por cable", "los dos")):
        if h.cable_anda is True:
            return "Por los dos a veces, pero más por WiFi"
        return "Por los dos"

    if any(k in q for k in ("estable", "mantuvo", "mejoró", "mejoro")):
        if h.reinicio_resuelve and h.reinicio_hecho:
            return "Sí, se mantuvo estable"
        return "Sigue cortándose"

    # Luces / PON / LOS (antes de "fibra/cajita": el paso FTTH menciona esos términos)
    if any(k in q for k in (" los", "los ", "pon", "luces", "luz roja", "alarma")):
        if h.frecuencia_cortes and "cambia" in q:
            return "No, las luces no cambian cuando se corta"
        if h.los == "roja":
            return "La LOS está en rojo, hay una lucecita roja"
        if h.pon == "verde" and h.los == "apagada":
            return "La PON está verde y la LOS apagada"
        if h.luces_ont:
            return f"Sí, {h.luces_ont}"
        return "Tiene luces, no sé cuáles"

    if any(k in q for k in ("reinici", "desenchuf", "30 segundo", "30s", "30 segundos")):
        if h.reinicio_hecho and h.reinicio_resuelve:
            return "Ya reinicié y ahora anda bien"
        if h.reinicio_hecho:
            return "Ya reinicié 30 segundos y sigue igual"
        h.reinicio_hecho = True
        if h.los == "roja":
            return "Reinicié y la lucecita roja sigue"
        if h.reinicio_resuelve:
            if h.sintoma_whatsapp:
                return "Listo, reinicié. Ahora le voy a llamar por WhatsApp a ver"
            if h.tecnologia == "adsl":
                return "Listo, reinicié el módem. La luz DSL quedó fija y ya navego"
            if h.frecuencia_cortes:
                return "Listo, reinicié. Por ahora se mantuvo estable"
            return "Listo, reinicié y ya anda"
        return "Listo, reinicié. Sigue sin internet"

    if h.sintoma_whatsapp and any(k in q for k in ("probaste", "llamar", "contestó", "contesto", "mejor")):
        return "Sí me contestó, ya anda"

    if any(k in q for k in ("volvió", "volvio", "ya navega", "páginas", "paginas")):
        if h.reinicio_resuelve and h.reinicio_hecho:
            return "Sí, ya navega"
        if h.los == "roja":
            return "No, y sigue la luz roja"
        if h.cable_anda is True and h.wifi_zona == "lejos":
            return "Por cable navega, el wifi lejos no"
        return "Todavía no navega"

    if any(k in q for k in ("cable", "utp", "amarillo", "navega por cable", "firmes")):
        if h.cable_anda is True:
            return "Por cable al router anda bien, el problema es el WiFi"
        if h.cable_anda is False:
            return "Tampoco anda por cable"
        return "No probé por cable todavía"

    if "wifi" in q or "wi-fi" in q or "fondo" in q or "lejos" in q or "zona" in q:
        if h.wifi_zona == "lejos":
            return "En el living anda bien, lejos no"
        if h.cable_anda is True:
            return "Es solo el WiFi, por cable va"
        return "El WiFi a veces falla"

    # Tipo de acceso: solo el triaje (fibra vs radio vs ADSL), no el copy FTTH.
    if (
        ("adsl" in q and ("fibra" in q or "antena" in q or "cajita" in q))
        or "tipo de acceso" in q
        or "qué tipo" in q
        or "que tipo" in q
    ):
        return h.reply_tecnologia or "no sé"

    if any(k in q for k in ("cuántos", "cuantos", "equipos", "dispositivos")):
        n = h.n_equipos or 3
        return f"Hay como {n} equipos conectados"

    if any(k in q for k in ("horario", "tarde", "noche", "todo el día", "todo el dia")):
        return h.horario or "más a la noche"

    if any(k in q for k in ("fast.com", "test", "velocidad", "mega")):
        return h.fast_com or "no hice el test"

    if any(k in q for k in ("poe", "inyector", "fuente")):
        if h.poe_luz:
            return "La fuente PoE tiene lucecita prendida"
        return "No veo la fuentecita"

    if "vecino" in q or "torre" in q:
        if h.vecinos_ok:
            return "Los vecinos dicen que a ellos les anda"
        return "no sé"

    if any(k in q for k in ("nada", "lento", "corta", "síntoma", "sintoma", "carga")):
        if persona.id == "P04":
            return "Anda lento, no es que esté cortado"
        if persona.id == "P03":
            return "Es solo el WiFi"
        if persona.id == "P09":
            return "Se corta y vuelve, no es que esté muerto del todo"
        if h.sintoma_whatsapp:
            return "Es cuando llamo por WhatsApp"
        if h.quiere_clave:
            return "Quiero cambiar la contraseña del WiFi"
        return "No me carga nada"

    if "todos los dispositivos" in q or "solo en uno" in q or "un dispositivo" in q:
        if h.sintoma_whatsapp:
            return "Me pasa en el celular"
        return "En todos los equipos"

    if any(k in q for k in ("agente", "deriv", "ticket", "visita", "técnico", "tecnico")):
        if persona.n2_esperado in ("optica", "post_n1_radio") and turno >= 3:
            return "Sí, derivame por favor"
        return "Prefiero seguir intentando acá"

    if any(k in q for k in ("internet", "móvil", "movil", "factura", "en qué te", "en que te", "pagar")):
        if h.deuda_manana and any(k in q for k in ("pagar", "deuda", "saldo")):
            return "Lo pago mañana, sigamos con internet"
        if h.quiere_clave:
            return "Por el WiFi, quiero cambiar la clave"
        return "Por internet de casa"

    # Fallback: no repetir “sigue igual” (eso dispara N2 por frustración).
    if h.quiere_clave:
        return "Quiero cambiar la clave del WiFi"
    if h.sintoma_whatsapp:
        return "Es el WhatsApp en el celular"
    if h.tecnologia == "adsl":
        return h.reply_tecnologia or "Es ADSL por el teléfono"
    if h.frecuencia_cortes:
        return "Se corta a cada rato y después vuelve"
    if h.tecnologia == "radio":
        return "Reinicié antena y router y no volvió"
    if h.los == "roja":
        return "La LOS está en rojo"
    if h.tecnologia == "ftth":
        if h.wifi_zona == "lejos":
            return "Por cable anda, el WiFi no llega al fondo"
        if h.n_equipos:
            return f"Hay {h.n_equipos} equipos y es más a la noche"
        return h.reply_tecnologia or "Es fibra, cajita blanca"
    return "Es de casa, internet fijo"


def _identificar_portal(client: Any, dni: str = "30111222") -> str:
    start = client.post(
        "/api/v1/portal/auth/start",
        json={"dni": dni, "org_slug": "coop-batan"},
    )
    start.raise_for_status()
    body = start.json()
    otp = body.get("debug_otp")
    if not otp:
        raise RuntimeError("Sin debug_otp: el loop hogareño requiere APP_ENV=development")
    verify = client.post(
        "/api/v1/portal/auth/verify",
        json={
            "challenge_id": body["challenge_id"],
            "otp": otp,
            "org_slug": "coop-batan",
        },
    )
    verify.raise_for_status()
    data = verify.json()
    conv_id = data["conversacion"]["id"]
    _reset_hilo_n1(conv_id)
    return data["portal_token"]


def _reset_hilo_n1(conv_id: str) -> None:
    from app.estate import canal_repo as crepo
    from app.estate.database import get_session_factory
    from app.estate.models import ConversacionCanal

    Session = get_session_factory()
    with Session() as db:
        c = db.get(ConversacionCanal, conv_id)
        if not c:
            return
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
            "pasos_cubiertos",
            "wifi_rama_activada",
            "pppoe_rama",
            "menu_paso",
            "ultima_queja",
            "reiteracion_queja",
        ):
            ctx.pop(k, None)
        ctx["identificado"] = True
        ctx["saludo"] = True
        crepo.set_contexto(c, ctx)
        db.commit()


def _enviar(client: Any, token: str, texto: str) -> dict[str, Any]:
    r = client.post(
        "/api/v1/portal/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"texto": texto},
    )
    r.raise_for_status()
    return r.json()


def _ticket_en_payload(payload: dict[str, Any], _bot: str = "") -> str:
    """Ticket real (id) o cola de espera — no copy que mencione *agente*."""
    tid = str(payload.get("ticket_id") or "").strip()
    if tid:
        return tid
    estado = str(payload.get("estado") or "")
    modo = str(payload.get("modo") or "")
    if estado in ("espera_agente", "con_agente") or modo == "espera_agente":
        return "cola"
    return ""


def evaluar_resultado(
    persona: Persona,
    turnos: list[TurnoLoop],
) -> ResultadoPersona:
    ticket_id = next((t.ticket_id for t in turnos if t.ticket_id), "")
    ticket = bool(ticket_id)
    estado = turnos[-1].estado if turnos else ""
    intent = ""
    for t in reversed(turnos):
        if t.intencion:
            intent = t.intencion
            break
    fallas: list[str] = []
    n2_evitable = False
    n2_legitimo = False

    bot_blob = " ".join(t.respuesta for t in turnos).lower()
    turno_ticket = next((i for i, t in enumerate(turnos) if t.ticket_id), None)

    if persona.n2_esperado == "nunca":
        if ticket:
            n2_evitable = True
            fallas.append("N2 evitable: esta persona debía resolverse en N1")
        if persona.id == "P03" and any(
            k in bot_blob for k in ("visita", "ticket")
        ) and "wifi" not in bot_blob:
            fallas.append("P03: derivó sin playbook WiFi")
        if persona.id == "P02":
            pass
    elif persona.n2_esperado == "optica":
        if not ticket:
            # Puede ser OK si aún está preguntando luces; falla si habló de wifi post-LOS
            if "wifi" in bot_blob and "los" in bot_blob:
                fallas.append("P02: preguntó WiFi con LOS roja")
            if turno_ticket is None and len(turnos) >= persona.max_turnos:
                fallas.append("P02: no ofreció visita óptica al agotar turnos")
        else:
            n2_legitimo = True
            if "wifi" in bot_blob and any(
                k in bot_blob for k in ("los está en rojo", "los esta en rojo", "luz roja")
            ):
                # WiFi after LOS is a failure even with ticket
                if "fondo" in bot_blob or "2.4" in bot_blob:
                    fallas.append("P02: playbook WiFi post-LOS")
        if ticket and turno_ticket is not None and turno_ticket == 0:
            n2_evitable = True
            n2_legitimo = False
            fallas.append("N2 prematuro en el primer turno")
    elif persona.n2_esperado == "post_n1_radio":
        if ticket and turno_ticket is not None and turno_ticket < 2:
            n2_evitable = True
            fallas.append("P05: N2 antes de agotar N1 radio")
        elif ticket:
            n2_legitimo = True
        # no ticket al final no es falla dura: el bot puede seguir preguntando

    if persona.id == "P07" and ticket and (turno_ticket or 0) == 0:
        n2_evitable = True
        fallas.append("P07: ticket al pedir humano sin síntoma")

    if persona.id == "P08" and ticket:
        n2_evitable = True
        fallas.append("P08: reiteración temprana no debe abrir N2")

    ok = not n2_evitable and not fallas
    if persona.n2_esperado == "optica" and ticket and not n2_evitable:
        ok = True
        fallas = [f for f in fallas if "no ofreció visita" not in f]

    transcript = []
    for t in turnos:
        transcript.append({"rol": "usuario", "texto": t.usuario})
        transcript.append({"rol": "bot", "texto": t.respuesta, "estado": t.estado})

    return ResultadoPersona(
        persona_id=persona.id,
        nombre=persona.nombre,
        n2_esperado=persona.n2_esperado,
        ticket_creado=ticket,
        ticket_id=ticket_id,
        estado_final=estado,
        intencion_final=intent,
        turnos=len(turnos),
        n2_evitable=n2_evitable,
        n2_legitimo=n2_legitimo,
        ok=ok,
        fallas=fallas,
        transcript=transcript,
    )


def run_persona(client: Any, persona: Persona, *, usar_llama: bool = False) -> ResultadoPersona:
    from app.domain.flujos_abonado import PLAYBOOKS

    with (
        patch("app.api.v1.portal.resolve_canal_usar_llama", return_value=usar_llama),
        patch("app.services.canal_abonado.playbooks_as_pasos", return_value=PLAYBOOKS),
    ):
        token = _identificar_portal(client, persona.dni)
        turnos: list[TurnoLoop] = []
        last_bot = ""
        dijo_apertura = False
        ticket = ""

        for i in range(persona.max_turnos):
            msg = responder_como_cliente(
                last_bot,
                persona,
                turno=i,
                ya_dijo_apertura=dijo_apertura,
                ticket_ya=bool(ticket),
            )
            if not msg:
                break
            dijo_apertura = True
            payload = _enviar(client, token, msg)
            bot = str(payload.get("respuesta") or payload.get("reply") or "").strip()
            ticket = ticket or _ticket_en_payload(payload, bot)
            t = TurnoLoop(
                usuario=msg,
                respuesta=bot,
                estado=str(payload.get("estado") or ""),
                ticket_id=ticket,
                intencion=str(payload.get("intencion") or ""),
            )
            turnos.append(t)
            last_bot = bot
            if t.ticket_id:
                break
            if t.estado in ("espera_agente", "con_agente", "cerrado"):
                break
        return evaluar_resultado(persona, turnos)


def run_loop(
    *,
    ids: list[str] | None = None,
    client: Any | None = None,
) -> list[ResultadoPersona]:
    selected = PERSONAS
    if ids:
        wanted = set(ids)
        selected = [p for p in PERSONAS if p.id in wanted]
    own_client = client is None
    if own_client:
        os.environ.setdefault("APP_ENV", "development")
        os.environ.setdefault("DISABLE_DEMO_USERS", "false")
        from fastapi.testclient import TestClient

        from main import app

        client = TestClient(app)
    results: list[ResultadoPersona] = []
    try:
        for p in selected:
            print(f"[HOGAR] {p.id} — {p.nombre}…", flush=True)
            r = run_persona(client, p)
            results.append(r)
            flag = "OK" if r.ok else "FAIL"
            print(
                f"  {flag} n2={r.ticket_creado} evitable={r.n2_evitable} "
                f"legitimo={r.n2_legitimo} intent={r.intencion_final} "
                f"fallas={r.fallas}",
                flush=True,
            )
    finally:
        if own_client and hasattr(client, "close"):
            try:
                client.close()
            except Exception:
                pass
    return results


def resumen(results: list[ResultadoPersona]) -> dict[str, Any]:
    total = len(results) or 1
    return {
        "personas": len(results),
        "ok": sum(1 for r in results if r.ok),
        "n2_evitables": sum(1 for r in results if r.n2_evitable),
        "n2_legitimos": sum(1 for r in results if r.n2_legitimo),
        "tasa_ok": round(sum(1 for r in results if r.ok) / total, 3),
        "detalle": [asdict(r) for r in results],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Loop QA cliente hogareño (API local)")
    parser.add_argument("--personas", default="", help="IDs P01,P02,… (vacío = todas)")
    args = parser.parse_args(argv)
    ids = [s.strip() for s in args.personas.split(",") if s.strip()] or None
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    results = run_loop(ids=ids)
    payload = resumen(results)
    out = ARTIFACTS / "resultados_hogareno.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nJSON: {out}", flush=True)
    print(
        f"ok={payload['ok']}/{payload['personas']} "
        f"n2_evitables={payload['n2_evitables']} n2_legitimos={payload['n2_legitimos']}",
        flush=True,
    )
    return 0 if payload["n2_evitables"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
