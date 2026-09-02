"""Loop QA — cliente hogareño de internet (preguntar, escuchar, aprender, repregunta).

Simula un socio de la cooperativa con hechos ocultos: no vuelca el diagnóstico
de entrada; responde según lo que pregunta el bot. Mide tickets N2 evitables
vs. legítimos (óptica / N1 radio agotado).

Uso (in-process, API local TestClient — no pega a producción):

    .venv/bin/python -m qa_bot.cliente_hogareno
    .venv/bin/python -m qa_bot.cliente_hogareno --personas P01,P07
    .venv/bin/python -m qa_bot.cliente_hogareno --lote exhaustivo
    .venv/bin/python -m qa_bot.entrenamiento_exhaustivo
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
    # Facturación (curado Botmaker)
    tema_factura: str = ""  # pagar | informar | reactivar | reclamo
    pago_hace: str = ""  # ej. "20 minutos" | "8 horas"
    medio_pago: str = ""
    reclamo_mes: str = ""
    reclamo_monto: str = ""
    reclamo_persiste: bool = False
    # TV Sensa (curado Botmaker)
    tema_sensa: str = ""  # app | box
    sensa_internet_ok: bool = True
    sensa_dispositivo: str = ""
    sensa_app_abre: bool = False
    sensa_sintoma: str = ""
    sensa_acciones_resuelven: bool = False
    # Móvil IMOWI / agente / comercial (guion entrenamiento)
    tema_movil: str = ""  # datos | bono | a2p | menu_typo
    movil_modelo: str = ""
    movil_so: str = ""  # android | ios
    movil_apn_ok: bool = False
    movil_pack_acreditado: bool = False
    pide_agente_insistente: bool = False
    reply_menu_typo: str = ""
    tema_fijo: bool = False
    tema_comercial: str = ""  # alta | baja | plan
    deuda_impagable: bool = False
    # Continuidad WiFi / aviso deuda (casos reales 2026-09)
    aviso_deuda_elige: str = ""  # tecnico | pago
    reply_deuda_tecnico: str = ""
    dispositivo_wifi: str = ""  # tablet | todos
    reply_dispositivo: str = ""
    no_puerto_ethernet: bool = False


@dataclass
class Persona:
    id: str
    nombre: str
    descripcion: str
    hechos: Hechos
    n2_esperado: str  # nunca | optica | post_n1_radio | legitimo_* | segunda_insistencia
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
    Persona(
        id="P13",
        nombre="Quiere pagar factura",
        descripcion="Medios de pago / QR; confirma acceso. N2 no (Botmaker pagar).",
        n2_esperado="nunca",
        dni="32123456",
        hechos=Hechos(
            tema_factura="pagar",
            apertura="Hola, quiero pagar la factura",
        ),
    ),
    Persona(
        id="P14",
        nombre="Avisa que pagó",
        descripcion="Quiere informar pago; N1 explica auto. N2 no.",
        n2_esperado="nunca",
        dni="32123456",
        hechos=Hechos(
            tema_factura="informar",
            pago_hace="hace una hora",
            medio_pago="Mercado Pago QR",
            apertura="Hola, ya pagué, les aviso el pago",
        ),
    ),
    Persona(
        id="P15",
        nombre="Reactivación reciente",
        descripcion="Pagó hace 20 min; acepta esperar plazo. N2 no.",
        n2_esperado="nunca",
        dni="27333444",
        hechos=Hechos(
            tema_factura="reactivar",
            pago_hace="20 minutos",
            medio_pago="QR Fiserv",
            apertura="Pagué hace 20 minutos y sigue cortado el servicio",
        ),
    ),
    Persona(
        id="P16",
        nombre="Reclamo de monto",
        descripcion="No reconoce importe; diferencia persiste → N2 facturación legítimo.",
        n2_esperado="legitimo_factura",
        max_turnos=12,
        dni="32123456",
        hechos=Hechos(
            tema_factura="reclamo",
            reclamo_mes="marzo",
            reclamo_monto="8500, antes pagaba 4500",
            reclamo_persiste=True,
            apertura="Me cobraron de más este mes, no reconozco el monto",
        ),
    ),
    Persona(
        id="P17",
        nombre="Sensa app se arregla",
        descripcion="App Sensa; internet OK; reinicio/actualizar resuelve. N2 no.",
        n2_esperado="nunca",
        hechos=Hechos(
            tema_sensa="app",
            sensa_internet_ok=True,
            sensa_dispositivo="Smart TV",
            sensa_app_abre=False,
            sensa_sintoma="se queda cargando",
            sensa_acciones_resuelven=True,
            apertura="No me anda la app Sensa en la TV",
        ),
    ),
    Persona(
        id="P18",
        nombre="Sensa error de cuenta",
        descripcion="Internet OK; error de cuenta persiste tras N1 → N2 legítimo.",
        n2_esperado="legitimo_sensa",
        max_turnos=14,
        hechos=Hechos(
            tema_sensa="app",
            sensa_internet_ok=True,
            sensa_dispositivo="Smart TV",
            sensa_app_abre=True,
            sensa_sintoma="error de cuenta",
            sensa_acciones_resuelven=False,
            apertura="Sensa me da error de cuenta y no reproduce nada",
        ),
    ),
    # —— Guion extra (móvil / agente / comercial) ——
    Persona(
        id="P19",
        nombre="Móvil pack acreditado sin datos",
        descripcion="Patricia: Moto/APN OK; pack OK sin datos → N2 provisión (no iPhone/3G).",
        n2_esperado="legitimo_provision_movil",
        max_turnos=12,
        dni="32123456",
        hechos=Hechos(
            tema_movil="datos",
            movil_modelo="Moto g72",
            movil_so="android",
            movil_apn_ok=True,
            movil_pack_acreditado=True,
            apertura="No Tengo datos en Mar del Plata",
        ),
    ),
    Persona(
        id="P20",
        nombre="2ª insistencia mismo pedido de agente",
        descripcion="Repite «quiero hablar con un agente»; 1ª no ticket, 2ª sí.",
        n2_esperado="segunda_insistencia",
        max_turnos=4,
        hechos=Hechos(
            pide_agente_insistente=True,
            apertura="quiero hablar con un agente",
        ),
    ),
    Persona(
        id="P21",
        nombre="Saldo / cuánto debo",
        descripcion="Consulta saldo; N1 informa sin ticket.",
        n2_esperado="nunca",
        dni="32123456",
        hechos=Hechos(
            tema_factura="saldo",
            apertura="Cuánto debo, quiero ver el saldo",
        ),
    ),
    Persona(
        id="P22",
        nombre="Factura más cara / aumento",
        descripcion="Pregunta por aumento; indaga, no solo medios de pago. N2 no al inicio.",
        n2_esperado="nunca",
        dni="32123456",
        hechos=Hechos(
            tema_factura="aumento",
            reclamo_mes="este mes",
            reclamo_monto="vino más cara que el anterior",
            apertura="Me vino más cara la factura, por qué subió?",
        ),
    ),
    Persona(
        id="P23",
        nombre="Se acabaron los datos del abono",
        descripcion="Bono vía ov.batan.coop; no ticket.",
        n2_esperado="nunca",
        dni="32123456",
        hechos=Hechos(
            tema_movil="bono",
            apertura="Se me acabaron los datos del abono",
        ),
    ),
    Persona(
        id="P24",
        nombre="SMS banco no llega (A2P)",
        descripcion="Sugiere otro medio; no promete habilitación; N2 no prematuro.",
        n2_esperado="nunca",
        dni="32123456",
        hechos=Hechos(
            tema_movil="a2p",
            apertura="No me llega el SMS de verificación del banco",
        ),
    ),
    Persona(
        id="P25",
        nombre="Fijo sin tono",
        descripcion="Playbook telefonía fija agotado → N2 legítimo (no prematuro).",
        n2_esperado="post_n1_fija",
        max_turnos=12,
        hechos=Hechos(
            tema_fijo=True,
            tono_fijo=False,
            apertura="No anda el fijo, sin tono",
        ),
    ),
    Persona(
        id="P26",
        nombre="Typo menú móvil ,ovil",
        descripcion="Tras menú, escribe ,ovil; debe tomar móvil sin ticket vacío.",
        n2_esperado="nunca",
        dni="32123456",
        hechos=Hechos(
            tema_movil="menu_typo",
            movil_modelo="Samsung A14",
            movil_so="android",
            apertura="Hola",
            reply_menu_typo=",ovil",
        ),
    ),
    Persona(
        id="P27",
        nombre="Corte por falta de pago cómo pago",
        descripcion="Medios OV/QR; sin CBU inventado; N2 no.",
        n2_esperado="nunca",
        dni="27333444",
        hechos=Hechos(
            tema_factura="pagar",
            apertura="Me cortaron el servicio por falta de pago, como pago?",
        ),
    ),
    Persona(
        id="P28",
        nombre="Quiere contratar fibra",
        descripcion="Alta comercial; no ticket técnico N2.",
        n2_esperado="nunca",
        hechos=Hechos(
            tema_comercial="alta",
            apertura="Quiero contratar internet fibra en Batán",
        ),
    ),
    Persona(
        id="P29",
        nombre="Karina — baja con deuda impagable",
        descripcion="Baja internet+Sensa; no puede pagar; N2 comercial legítimo.",
        n2_esperado="legitimo_comercial",
        dni="27333444",
        max_turnos=8,
        hechos=Hechos(
            tema_comercial="baja",
            deuda_impagable=True,
            apertura="Quiero dar de baja todo el internet la aplicación sensa todo",
        ),
    ),
    Persona(
        id="P30",
        nombre="Mauricio — deuda + internet coloquial",
        descripcion="Aviso de mora; responde «internet»/«beibe» para seguir N1. Sin ticket.",
        n2_esperado="nunca",
        dni="28555666",
        max_turnos=10,
        hechos=Hechos(
            tecnologia="ftth",
            reply_tecnologia="es fibra",
            luces_ont="luces normales",
            pon="verde",
            los="apagada",
            cable_anda=True,
            wifi_zona="lejos",
            aviso_deuda_elige="tecnico",
            reply_deuda_tecnico="internet",
            apertura="no tengo internet",
        ),
    ),
    Persona(
        id="P31",
        nombre="Gabriel — WiFi en la tablet",
        descripcion="Línea OK; solo WiFi en tablet (typo «table»). No cable RJ45 ni re-triaje.",
        n2_esperado="nunca",
        max_turnos=10,
        hechos=Hechos(
            tecnologia="ftth",
            reply_tecnologia="fibra",
            luces_ont="luces normales",
            pon="verde",
            los="apagada",
            cable_anda=None,
            wifi_zona="lejos",
            dispositivo_wifi="tablet",
            reply_dispositivo="en la table",
            no_puerto_ethernet=True,
            apertura="no me anda el wifi en la table",
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

    # —— 2ª insistencia mismo pedido de agente (P20) ——
    if h.pide_agente_insistente:
        return "quiero hablar con un agente"

    # —— Alta / comercial (P28, P29) ——
    if h.tema_comercial:
        if h.tema_comercial == "baja":
            if any(
                k in q
                for k in (
                    "agente",
                    "deriv",
                    "comercial",
                    "te derivo",
                    "pasame con",
                    "querés que te derive",
                    "quieres que te derive",
                )
            ):
                return "Sí, pasame con comercial por favor"
            if h.deuda_impagable and any(
                k in q
                for k in (
                    "deuda",
                    "saldo",
                    "pagar",
                    "cero",
                    "derive",
                    "comercial",
                    "equipo",
                    "desenchuf",
                )
            ):
                return "Saque todo xq se fue demaciado mucho para pagar"
            if any(k in q for k in ("baja", "internet", "sensa", "producto", "total")):
                return "La baja del internet y la aplicación Sensa, todo"
            return "Quiero dar de baja todo el internet la aplicación sensa todo"
        if any(k in q for k in ("agente", "deriv", "ticket", "comercial")):
            if turno >= 2:
                return "Sí, pasame con comercial por favor"
            return "Prefiero info acá primero"
        if any(k in q for k in ("alta", "plan", "barrio", "localidad", "internet", "móvil", "movil")):
            if h.tema_comercial == "alta":
                return "Alta nueva de internet fibra en Batán"
            return "Consulta de plan"
        return "Quiero contratar fibra"

    # —— Móvil IMOWI (P19, P23, P24, P26) ——
    if h.tema_movil:
        if h.reply_menu_typo and any(
            k in q
            for k in (
                "en qué te",
                "en que te",
                "internet",
                "telefonía",
                "telefonia",
                "factura",
                "móvil",
                "movil",
            )
        ):
            return h.reply_menu_typo

        if any(k in q for k in ("agente", "deriv", "ticket", "abrimos")):
            if persona.n2_esperado == "legitimo_provision_movil" and turno >= 3:
                return "Sí, derivame con la línea por favor"
            if h.tema_movil in ("bono", "a2p", "menu_typo"):
                return "No hace falta, gracias"
            return "Prefiero seguir acá"

        if h.tema_movil == "bono":
            if any(k in q for k in ("ov.batan", "bono", "autogestión", "autogestion", "imowi.com")):
                return "Ah perfecto, compro el bono en ov.batan.coop, gracias"
            if any(k in q for k in ("internet", "móvil", "movil", "en qué te", "en que te")):
                return "Se me acabaron los datos del abono móvil"
            return "Necesito cargar datos del abono"

        if h.tema_movil == "a2p":
            if any(k in q for k in ("otro medio", "whatsapp", "mail", "llamad", "banco")):
                return "Probaré por otro medio, gracias"
            if any(k in q for k in ("internet", "móvil", "movil", "en qué te", "en que te")):
                return "No me llega el SMS del banco"
            return "Es el SMS de verificación del banco"

        if any(k in q for k in ("android", "iphone", "modelo", "qué celular", "que celular", "equipo")):
            so = "Android" if h.movil_so == "android" else "iPhone"
            return f"Es un {h.movil_modelo or 'celular'} {so}"

        if any(k in q for k in ("datos móviles", "datos moviles", "modo avión", "modo avion", "prendidos")):
            return "Sí, datos prendidos y sin modo avión"

        if any(k in q for k in ("pack", "bono", "abono", "quedan datos", "consumo")):
            if h.movil_pack_acreditado:
                return "El pack figura acreditado y me quedan datos, pero no navega nada"
            return "Se me acabaron los datos"

        if any(k in q for k in ("apn", "punto de acceso", "catel", "imowi")):
            if h.movil_apn_ok:
                return "Sí, el APN imowi quedó bien configurado y sigue sin datos"
            return "No sé configurar el APN"

        if any(k in q for k in ("wifi", "navega", "probá", "proba", "zona", "viaje")):
            return "Apagué el WiFi y sigo sin datos móviles"

        if any(k in q for k in ("internet", "móvil", "movil", "en qué te", "en que te", "pagar", "sensa")):
            return "Por el móvil, no tengo datos"

        return "Sigue sin datos en el celular"

    # —— Teléfono fijo (P25) ——
    if h.tema_fijo:
        if any(k in q for k in ("agente", "deriv", "ticket", "abrimos")):
            if persona.n2_esperado == "post_n1_fija" and turno >= 5:
                return "Sí, abrí el ticket por favor"
            return "Prefiero seguir acá un poco más"
        if "tono" in q:
            return "No, al descolgar no hay tono" if h.tono_fijo is False else "Sí, hay tono"
        if any(k in q for k in ("todos los teléfonos", "todos los telefonos", "solo en uno")):
            return "En todos los fijos de la casa"
        if any(k in q for k in ("cable", "enchuf", "toma de la pared")):
            return "Sí, el cable está bien enchufado"
        if any(k in q for k in ("otro", "aparato", "misma toma")):
            return "Probé otro teléfono en la misma toma y tampoco"
        if any(k in q for k in ("ruido", "estática", "estatica")):
            return "No, no hay ruido ni estática"
        if any(k in q for k in ("adsl", "splitter", "filtro")):
            return "No, en esa línea no tengo ADSL"
        if any(k in q for k in ("internet", "móvil", "movil", "en qué te", "en que te")):
            return "Es el teléfono fijo de casa"
        return "El fijo sigue sin tono"

    # —— TV Sensa (P17–P18) ——
    if h.tema_sensa:
        if any(k in q for k in ("agente", "deriv", "ticket", "abrimos el ticket", "comercial")):
            if persona.n2_esperado == "legitimo_sensa" and turno >= 3:
                return "Sí, abrí el ticket por favor"
            if h.sensa_acciones_resuelven:
                return "No hace falta, ya mejoró, gracias"
            return "Prefiero seguir un poco más"

        if any(k in q for k in ("app/web", "decodificador", "android tv", "vamos con tv", "es la app")):
            return "Es la app Sensa en la Smart TV" if h.tema_sensa == "app" else "Es el TV Box de la cooperativa"

        if any(k in q for k in ("tenés internet", "tenes internet", "internet funcionando")):
            return "Sí, internet anda bien en la casa" if h.sensa_internet_ok else "No, tampoco hay internet"

        if any(k in q for k in ("desde qué equipo", "desde que equipo", "smart tv", "celular", "tv box")):
            return f"Desde {h.sensa_dispositivo or 'la Smart TV'}"

        if any(k in q for k in ("página de internet", "pagina de internet", "abrís alguna", "abris alguna")):
            return "Sí, navego bien en esa TV" if h.sensa_internet_ok else "No navega"

        if any(k in q for k in ("app o la web", "abre bien", "ni llega")):
            return "Abre pero falla al ver" if h.sensa_app_abre else "Ni llega a entrar bien a la app"

        if any(k in q for k in ("reproduce", "cargando", "error de cuenta", "calidad")):
            return h.sensa_sintoma or "No reproduce"

        if any(k in q for k in ("reiniciar", "actualizar sensa", "mejoró", "mejoro", "probá", "proba")):
            if h.sensa_acciones_resuelven:
                return "Sí, mejoró: ya reproduce bien, gracias"
            return "Hice todo eso y sigue igual, error de cuenta"

        return "Es un problema con Sensa en la TV"

    # —— Facturación (P13–P16) ——
    if h.tema_factura:
        if any(k in q for k in ("agente", "deriv", "ticket", "facturación", "facturacion")):
            if persona.n2_esperado == "legitimo_factura" and turno >= 2:
                return "Sí, derivame con facturación por favor"
            if h.tema_factura == "reactivar":
                return "No, espero un rato más, gracias"
            if h.tema_factura in ("pagar", "informar", "saldo", "aumento"):
                return "No hace falta, gracias"
            return "Prefiero seguir acá"

        if h.tema_factura == "pagar":
            if any(k in q for k in ("entrar", "medio de pago", "pudiste", "qr", "pagar", "ov.batan")):
                return "Sí, ya entré al QR / ov.batan, gracias"
            if any(k in q for k in ("qué necesitás", "que necesitas", "pagar, descargar", "reclamar")):
                return "Quiero pagar la factura"
            return "Solo necesito pagar con el QR"

        if h.tema_factura == "informar":
            if any(k in q for k in ("dni", "socio", "medio", "fecha")):
                return f"DNI {persona.dni}, pagué {h.pago_hace} por {h.medio_pago}"
            if any(k in q for k in ("necesari", "automátic", "automatic", "avisar", "ov.batan")):
                return "Ah perfecto, no hace falta avisar entonces, gracias"
            if any(k in q for k in ("deriv", "figura", "plazo")):
                return "Entendido, espero la imputación, gracias"
            return "Solo quería avisar que ya pagué"

        if h.tema_factura == "reactivar":
            if any(k in q for k in ("hace cuánto", "hace cuanto", "medio", "pagaste")):
                return f"Hace {h.pago_hace}, por {h.medio_pago}"
            if any(k in q for k in ("figura", "acredit", "sigue cortado", "reactiv")):
                return "No sé si figura todavía; pagué hace poco y sigo sin servicio"
            if any(k in q for k in ("dni", "socio")):
                return f"Mi DNI es {persona.dni}"
            return "Pagué recién y todavía no vuelve el servicio"

        if h.tema_factura == "reclamo":
            if any(k in q for k in ("mes", "monto", "cuánto", "cuanto", "importe")):
                return f"Es de {h.reclamo_mes}, veo {h.reclamo_monto}"
            if any(k in q for k in ("plan", "servicio", "tarifa", "ajuste")):
                return "No cambié de plan ni sumé nada"
            if any(k in q for k in ("dni", "socio")):
                return f"DNI {persona.dni}"
            if any(k in q for k in ("diferencia", "sigue", "derivo")):
                return "Sí, la diferencia sigue; derivame con facturación"
            return "No reconozco ese cobro"

        if h.tema_factura == "saldo":
            if any(k in q for k in ("saldo", "deuda", "debe", "pendiente", "monto")):
                return "Dale, con eso me alcanza, gracias"
            if any(k in q for k in ("dni", "socio")):
                return f"Mi DNI es {persona.dni}"
            return "Solo quiero saber cuánto debo"

        if h.tema_factura == "aumento":
            if any(k in q for k in ("aumento", "subió", "subio", "ajuste", "plan", "por qué", "por que")):
                return "Quiero entender por qué subió respecto al mes pasado"
            if any(k in q for k in ("dni", "socio")):
                return f"DNI {persona.dni}"
            return "Me vino más cara la factura"

    if persona.id == "P08" and turno >= 1:
        return "Sigue igual, no tengo internet"

    if persona.id == "P07" and turno == 1:
        return "Es que no me anda internet"

    if persona.id == "P12" and turno == 1 and any(
        k in q for k in ("deuda", "saldo", "pagar", "pendiente")
    ):
        return "No, lo pago mañana, sigamos con el problema de internet"

    # —— P30: aviso deuda → seguir diagnóstico (no pagar) ——
    if h.aviso_deuda_elige == "tecnico":
        if any(
            k in q
            for k in (
                "pagar",
                "deuda",
                "saldo",
                "diagnóstico",
                "diagnostico",
                "preferís",
                "preferis",
                "qr",
            )
        ) and not any(k in q for k in ("wifi", "reinici", "cable", "equipo", "habitacion")):
            return h.reply_deuda_tecnico or "internet"

    # —— P31: tablet sin RJ45 (typo «table») ——
    if h.no_puerto_ethernet or h.dispositivo_wifi == "tablet":
        if "no se conectan por cable" in q:
            return "no tengo pc, solo la tablet. me acerco al router, gracias"
        if any(
            k in q
            for k in (
                "solo el wifi",
                "es solo el wifi",
                "no te carga",
                "anda lento",
            )
        ):
            return "es solo el wifi"
        if (
            ("adsl" in q and ("fibra" in q or "antena" in q or "cajita" in q))
            or "tipo de acceso" in q
            or "qué tipo" in q
            or "que tipo" in q
        ):
            return h.reply_tecnologia or "fibra"
        if any(
            k in q
            for k in (
                "cable de red",
                "conectando la tablet",
                "conectar la tablet",
                "adaptador",
            )
        ):
            return "como conecto la tablet por cable de red?"
        if any(
            k in q
            for k in (
                "otro dispositivo",
                "otros dispositivo",
                "todos los equipos",
                "todos los dispositivos",
                "solo a uno",
                "solo en uno",
                "solo en este",
                "un dispositivo",
                "uno en particular",
                "celular o una notebook",
                "tablet",
            )
        ):
            return h.reply_dispositivo or "en la table"
        if any(
            k in q
            for k in (
                "otras habitaciones",
                "solo ahí",
                "solo ahi",
            )
        ):
            return "a veces"
        if any(
            k in q
            for k in (
                "parte de tu casa",
                "más débil",
                "mas debil",
                "lejos del router",
            )
        ):
            return "baño"
        if "al lado" in q or "cerca del router" in q:
            return "estoy al lado"
        if any(k in q for k in ("olvidar la red", "olvidar", "contraseña", "clave")):
            return "ya lo hice"
        if "2.4" in q or "5 ghz" in q or "5ghz" in q:
            return "ambas"
        if "mensaje de error" in q or "desconecta" in q:
            return "me dice conectado sin internet"

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

    # ADSL (no confundir con el triaje fibra/radio/ADSL)
    _triaje_acceso = "adsl" in q and (
        "fibra" in q or "antena" in q or "cajita" in q
    )
    if (
        not _triaje_acceso
        and (
            h.tecnologia == "adsl"
            or any(k in q for k in ("microfiltro", "splitter", "dsl", "sync"))
        )
    ):
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
        if h.no_puerto_ethernet:
            return "como conecto la tablet por cable de red?"
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
        if persona.id == "P03" or h.dispositivo_wifi == "tablet":
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
        if h.reply_dispositivo:
            return h.reply_dispositivo
        return "En todos los equipos"

    if any(k in q for k in ("agente", "deriv", "ticket", "visita", "técnico", "tecnico")):
        if persona.n2_esperado in (
            "optica",
            "post_n1_radio",
            "post_n1_fija",
            "legitimo_factura",
            "legitimo_sensa",
            "legitimo_provision_movil",
        ) and turno >= 3:
            return "Sí, derivame por favor"
        return "Prefiero seguir intentando acá"

    if any(k in q for k in ("internet", "móvil", "movil", "factura", "en qué te", "en que te", "pagar", "sensa")):
        if h.tema_sensa:
            return "Por la TV Sensa"
        if h.tema_movil:
            return "Por el móvil"
        if h.tema_fijo:
            return "Por el teléfono fijo"
        if h.tema_comercial:
            return "Quiero contratar un plan"
        if h.tema_factura == "pagar":
            return "Por la factura, quiero pagar"
        if h.tema_factura == "saldo":
            return "Quiero consultar el saldo"
        if h.tema_factura == "aumento":
            return "Por el aumento de la factura"
        if h.tema_factura:
            return "Es un tema de facturación"
        if h.deuda_manana and any(k in q for k in ("pagar", "deuda", "saldo")):
            return "Lo pago mañana, sigamos con internet"
        if h.quiere_clave:
            return "Por el WiFi, quiero cambiar la clave"
        return "Por internet de casa"

    # Fallback: no repetir “sigue igual” (eso dispara N2 por frustración).
    if h.tema_sensa:
        return "Sigue el problema con Sensa"
    if h.tema_movil:
        return "Sigue sin datos en el celular"
    if h.tema_fijo:
        return "El fijo sigue sin tono"
    if h.tema_comercial:
        return "Quiero contratar fibra"
    if h.tema_factura == "pagar":
        return "Quiero pagar con el QR de la factura"
    if h.tema_factura == "informar":
        return "Ya pagué, solo avisaba"
    if h.tema_factura == "reactivar":
        return f"Pagué hace {h.pago_hace or 'poco'} y sigue cortado"
    if h.tema_factura == "reclamo":
        return "No reconozco el monto de la factura"
    if h.tema_factura == "saldo":
        return "Quiero saber el saldo"
    if h.tema_factura == "aumento":
        return "Me vino más cara la factura"
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
        if h.no_puerto_ethernet:
            return h.reply_dispositivo or "en la table"
        if h.wifi_zona == "lejos":
            return "Por cable anda, el WiFi no llega al fondo"
        if h.n_equipos:
            return f"Hay {h.n_equipos} equipos y es más a la noche"
        return h.reply_tecnologia or "Es fibra, cajita blanca"
    return "Es de casa, internet fijo"


def _asegurar_padron_persona(persona: Persona) -> None:
    """El sqlite de test puede divergir del seed; P30 necesita internet + mora."""
    if persona.id != "P30":
        return
    from sqlalchemy import select

    from app.estate.database import get_session_factory
    from app.estate.models import Abonado, Organization

    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        if not org:
            return
        abo = db.scalar(select(Abonado).where(Abonado.dni == persona.dni))
        campos = dict(
            servicio="internet",
            estado="activo",
            deuda_monto="4500",
        )
        if abo is None:
            db.add(Abonado(organizacion_id=org.id, dni=persona.dni, **campos))
        else:
            for k, v in campos.items():
                setattr(abo, k, v)
        db.commit()


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
            "hechos",
            "comprension_turno",
            "aviso_deuda_ofrecido",
            "intencion_tecnica_pendiente",
            "aviso_sin_internet",
            "temas_pendientes",
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
        if persona.id == "P30":
            if "no figura internet fijo" in bot_blob:
                fallas.append("P30: padrón sin internet fijo (DNI incorrecto)")
            if "diagnóstico" not in bot_blob and "diagnostico" not in bot_blob:
                fallas.append("P30: no ofreció aviso deuda (pagar vs diagnóstico)")
            eligio_tecnico = False
            reasks = 0
            for t in turnos:
                u = (t.usuario or "").lower().strip()
                if u in ("internet", "beibe") or u == (
                    persona.hechos.reply_deuda_tecnico or "internet"
                ):
                    eligio_tecnico = True
                    continue
                if eligio_tecnico:
                    r = (t.respuesta or "").lower()
                    if "pagar" in r and (
                        "diagnóstico" in r or "diagnostico" in r
                    ):
                        reasks += 1
            if reasks >= 2:
                fallas.append("P30: loop aviso deuda tras elegir técnico")
        if persona.id == "P31":
            wifi_en_curso = False
            for t in turnos:
                r = (t.respuesta or "").lower()
                if any(
                    k in r
                    for k in (
                        "dispositivos",
                        "habitacion",
                        "olvidar la red",
                        "2.4",
                        "solo el wifi",
                        "cable al router",
                        "tablets y celulares",
                    )
                ):
                    wifi_en_curso = True
                if (
                    ("conectando la tablet" in r or "conectar la tablet" in r)
                    and "cable" in r
                ):
                    fallas.append("P31: pidió cable ethernet a la tablet")
                    break
                if not wifi_en_curso:
                    continue
                if "tipo de conexión" in r or "tipo de conexion" in r:
                    fallas.append("P31: re-trió tipo de acceso mid-WiFi")
                    break
                if "cajita blanca" in r and "adsl" in r and "antena" in r:
                    fallas.append("P31: re-trió tipo de acceso mid-WiFi")
                    break
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
    elif persona.n2_esperado == "post_n1_fija":
        if ticket and turno_ticket is not None and turno_ticket < 3:
            n2_evitable = True
            fallas.append("P25: N2 antes de agotar N1 telefonía fija")
        elif ticket:
            n2_legitimo = True
        elif len(turnos) >= persona.max_turnos:
            fallas.append("P25: no ofreció handoff tras agotar N1 fijo")
    elif persona.n2_esperado == "legitimo_factura":
        if ticket:
            n2_legitimo = True
            if turno_ticket is not None and turno_ticket == 0:
                n2_evitable = True
                n2_legitimo = False
                fallas.append("N2 prematuro en reclamo de factura")
        elif len(turnos) >= persona.max_turnos:
            fallas.append("Reclamo de monto: no ofreció handoff facturación")
    elif persona.n2_esperado == "legitimo_sensa":
        if ticket:
            n2_legitimo = True
            if turno_ticket is not None and turno_ticket == 0:
                n2_evitable = True
                n2_legitimo = False
                fallas.append("N2 prematuro en Sensa")
        elif len(turnos) >= persona.max_turnos:
            fallas.append("Sensa: no ofreció handoff tras agotar N1")
    elif persona.n2_esperado == "legitimo_provision_movil":
        if ticket:
            n2_legitimo = True
            if turno_ticket is not None and turno_ticket == 0:
                n2_evitable = True
                n2_legitimo = False
                fallas.append("N2 prematuro en móvil/provisión")
        elif len(turnos) >= persona.max_turnos:
            fallas.append("Móvil pack OK sin datos: no ofreció handoff provisión")
        # Guardrails: no inventar iPhone/3G en Android con pack acreditado
        if any(k in bot_blob for k in ("iphone", "3g", "modo 3g")):
            fallas.append("P19: inventó iPhone/3G (guardrail móvil)")
            if ticket:
                n2_evitable = True
                n2_legitimo = False
    elif persona.n2_esperado == "legitimo_comercial":
        if persona.id == "P29":
            if "ov.batan.coop/#/pagar" in bot_blob or "qr fiserv" in bot_blob:
                fallas.append("P29: ofreció pago a quien no puede pagar")
            if "diagnóstico de internet" in bot_blob or "diagnostico de internet" in bot_blob:
                fallas.append("P29: rutó a diagnóstico técnico en lugar de baja")
            if "no reconocés" in bot_blob or "no reconoces" in bot_blob:
                fallas.append("P29: confundió con reclamo de factura")
        if ticket:
            n2_legitimo = True
            if turno_ticket is not None and turno_ticket == 0:
                n2_evitable = True
                n2_legitimo = False
                fallas.append("N2 prematuro en baja comercial")
        elif len(turnos) >= persona.max_turnos:
            fallas.append("P29: no ofreció handoff comercial tras baja+deuda")
    elif persona.n2_esperado == "segunda_insistencia":
        if ticket and turno_ticket is not None and turno_ticket == 0:
            n2_evitable = True
            fallas.append("P20: ticket en la 1ª petición de agente (debe ser 2ª)")
        elif ticket and turno_ticket is not None and turno_ticket >= 1:
            n2_legitimo = True
        elif not ticket and len(turnos) >= 2:
            fallas.append("P20: 2ª insistencia de agente no creó ticket")

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
    if persona.n2_esperado == "legitimo_factura" and ticket and not n2_evitable:
        ok = True
        fallas = [f for f in fallas if "no ofreció handoff" not in f]
    if persona.n2_esperado == "legitimo_sensa" and ticket and not n2_evitable:
        ok = True
        fallas = [f for f in fallas if "no ofreció handoff" not in f]
    if persona.n2_esperado == "legitimo_provision_movil" and ticket and not n2_evitable:
        ok = True
        fallas = [f for f in fallas if "no ofreció handoff" not in f]
    if persona.n2_esperado == "post_n1_fija" and ticket and not n2_evitable:
        ok = True
        fallas = [f for f in fallas if "no ofreció handoff" not in f]
    if persona.n2_esperado == "legitimo_comercial" and ticket and not n2_evitable:
        ok = True
        fallas = [f for f in fallas if "no ofreció handoff" not in f]
    if persona.n2_esperado == "segunda_insistencia" and ticket and not n2_evitable:
        ok = True
        fallas = [f for f in fallas if "no creó ticket" not in f]

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
        # BillTrack mock puede pisar servicio→móvil; reponer internet+mora de P30.
        _asegurar_padron_persona(persona)
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
    # Igual que tests/conftest: sin BillTrack externo (evita ruido y desvíos a facturación).
    os.environ.pop("BILLTRACK_DATABASE_URL", None)

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
    from qa_bot.lotes import LOTES

    parser = argparse.ArgumentParser(description="Loop QA cliente hogareño (API local)")
    parser.add_argument("--personas", default="", help="IDs P01,P02,… (vacío = todas)")
    parser.add_argument(
        "--lote",
        default="",
        help="Lote nombrado: base|guion|exhaustivo|internet|factura|movil|agente|sensa",
    )
    args = parser.parse_args(argv)
    ids = [s.strip() for s in args.personas.split(",") if s.strip()] or None
    if args.lote:
        if args.lote not in LOTES:
            parser.error(f"lote desconocido: {args.lote}. Opciones: {', '.join(sorted(LOTES))}")
        ids = LOTES[args.lote]
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
