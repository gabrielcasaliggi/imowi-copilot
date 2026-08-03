"""Matriz conversacional N1 — Cooperativa Batán / Ecolan (portal invitado)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Turno:
    usuario: str
    # Expectativas blandas para scoring (keywords / comportamientos)
    espera_autodiagnostico: bool = False
    espera_resolucion_directa: bool = False
    no_debe_ticket_prematuro: bool = True
    # Si True, en este turno SÍ es aceptable ofrecer/abrir ticket
    ticket_aceptable: bool = False


@dataclass
class Escenario:
    id: str
    nombre: str
    categoria: str
    descripcion: str
    turnos: list[Turno]
    # Criterio de éxito N1 del escenario completo
    resolucion_n1_esperada: bool = True
    notas: str = ""
    tags: list[str] = field(default_factory=list)


ESCENARIOS: list[Escenario] = [
    Escenario(
        id="E01",
        nombre="Sin internet — fibra FTTH",
        categoria="internet_ftth",
        descripcion="Abonado sin servicio; debería triar tipo de acceso y guiar luces/reinicio ONT.",
        resolucion_n1_esperada=True,
        tags=["tecnico", "fibra"],
        turnos=[
            Turno(
                "Hola, no tengo internet en casa",
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
            Turno(
                "Tengo fibra, la cajita blanca",
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
            Turno(
                "Sí, tiene luces encendidas",
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
            Turno(
                "La PON está verde y la LOS apagada",
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
        ],
    ),
    Escenario(
        id="E02",
        nombre="Internet lento en horario pico",
        categoria="internet_lento",
        descripcion="Debe pedir contexto (dispositivos/horario) y sugerir reinicio/test, no ticket inmediato.",
        resolucion_n1_esperada=True,
        tags=["tecnico", "performance"],
        turnos=[
            Turno(
                "Internet anda re lento desde ayer a la tarde",
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
            Turno(
                "Hay como 8 equipos conectados",
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
            Turno(
                "Es más a la noche",
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
        ],
    ),
    Escenario(
        id="E03",
        nombre="WiFi no llega al fondo de la casa",
        categoria="wifi",
        descripcion="Autodiagnóstico de cobertura WiFi / reinicio router.",
        resolucion_n1_esperada=True,
        tags=["tecnico", "wifi"],
        turnos=[
            Turno(
                "El WiFi no llega a la habitación del fondo",
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
            Turno(
                "En el living anda bien, lejos no",
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
            Turno(
                "Sí, reinicié el router y sigue igual de lejos",
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
        ],
    ),
    Escenario(
        id="E04",
        nombre="Corte por deuda / pago QR",
        categoria="corte_deuda",
        descripcion="Debe orientar a pago con QR Fiserv sin escalar de entrada.",
        resolucion_n1_esperada=True,
        tags=["facturacion", "pagos"],
        turnos=[
            Turno(
                "Me cortaron el servicio por falta de pago, ¿cómo pago?",
                espera_resolucion_directa=True,
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
            Turno(
                "Mi DNI es 30111222",
                espera_resolucion_directa=True,
                no_debe_ticket_prematuro=True,
            ),
        ],
    ),
    Escenario(
        id="E05",
        nombre="Consulta de factura / saldo",
        categoria="facturacion",
        descripcion="En modo invitado debe pedir identificación o explicar límite; no ticket inmediato.",
        resolucion_n1_esperada=True,
        tags=["facturacion"],
        turnos=[
            Turno(
                "Quiero saber cuánto debo de la factura de este mes",
                espera_resolucion_directa=True,
                no_debe_ticket_prematuro=True,
            ),
            Turno(
                "No tengo el QR a mano, ¿me lo pueden mandar?",
                no_debe_ticket_prematuro=True,
            ),
        ],
    ),
    Escenario(
        id="E06",
        nombre="Móvil IMOWI sin datos",
        categoria="movil_datos",
        descripcion="Guía APN / reinicio / datos móviles antes de derivar.",
        resolucion_n1_esperada=True,
        tags=["movil"],
        turnos=[
            Turno(
                "Mi celular IMOWI no tiene datos, WhatsApp no carga con datos móviles",
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
            Turno(
                "Datos estánidos y modo avión apagado",
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
            Turno(
                "Reinicié el teléfono y sigue sin datos",
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
        ],
    ),
    Escenario(
        id="E07",
        nombre="Sin señal móvil",
        categoria="movil",
        descripcion="Autodiagnóstico de señal antes de ticket.",
        resolucion_n1_esperada=True,
        tags=["movil"],
        turnos=[
            Turno(
                "No tengo señal en el celular, no puedo llamar ni nada",
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
            Turno(
                "Probé modo avión y reiniciar, sigue sin barras",
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
        ],
    ),
    Escenario(
        id="E08",
        nombre="Pedido prematuro de operador humano",
        categoria="general",
        descripcion="Usuario pide humano de entrada; bot debería intentar N1 o menú antes de ticket.",
        resolucion_n1_esperada=True,
        tags=["handoff", "anti-ticket"],
        turnos=[
            Turno(
                "Quiero hablar con una persona, pasame con un operador",
                no_debe_ticket_prematuro=True,
            ),
            Turno(
                "Es que no me anda internet",
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
        ],
    ),
    Escenario(
        id="E09",
        nombre="Alta / cambio de plan",
        categoria="alta_plan",
        descripcion="Consulta comercial: puede derivar, pero primero aclarar tipo/zona.",
        resolucion_n1_esperada=False,
        notas="Esperado handoff comercial tras recopilar datos mínimos.",
        tags=["comercial"],
        turnos=[
            Turno(
                "Quiero contratar internet fibra en Batán",
                no_debe_ticket_prematuro=True,
            ),
            Turno(
                "Es alta nueva, barrio Centro",
                ticket_aceptable=True,
            ),
        ],
    ),
    Escenario(
        id="E10",
        nombre="Internet radio/antena caído",
        categoria="internet_radio",
        descripcion="Playbook PoE / reinicio antena.",
        resolucion_n1_esperada=True,
        tags=["tecnico", "wireless"],
        turnos=[
            Turno(
                "Se me cayó internet, tengo antena en el techo",
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
            Turno(
                "La fuente PoE tiene lucecita prendida",
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
            Turno(
                "Reinicié antena y router y no volvió",
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
        ],
    ),
    Escenario(
        id="E11",
        nombre="Persistencia post-N1 → ticket legítimo",
        categoria="internet_ftth",
        descripcion="Tras agotar pasos N1, ofrecer ticket es correcto.",
        resolucion_n1_esperada=False,
        notas="Ticket aceptable al final del playbook.",
        tags=["escalamiento-legitimo"],
        turnos=[
            Turno("No tengo internet, es fibra", espera_autodiagnostico=True),
            Turno("Sí tiene luces", espera_autodiagnostico=True),
            Turno("PON verde, LOS apagada", espera_autodiagnostico=True),
            Turno("Reinicié ONT y router 30 segundos y no volvió", espera_autodiagnostico=True),
            Turno("El cable amarillo está bien", espera_autodiagnostico=True),
            Turno(
                "Falla también por cable, no es solo WiFi. Sigue sin internet",
                ticket_aceptable=True,
            ),
            Turno(
                "Sí, abrí el ticket por favor",
                ticket_aceptable=True,
                no_debe_ticket_prematuro=False,
            ),
        ],
    ),
    Escenario(
        id="E12",
        nombre="Comprensión — typos y lenguaje coloquial",
        categoria="internet",
        descripcion="Debe entender mensaje mal escrito sin entrar en bucle.",
        resolucion_n1_esperada=True,
        tags=["nlp", "robustez"],
        turnos=[
            Turno(
                "ola no anda el interntt, no me carga nadaa",
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
            Turno(
                "es fibraa la cajita blanca",
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
        ],
    ),
    Escenario(
        id="E13",
        nombre="Bucle — mensaje repetido idéntico",
        categoria="internet",
        descripcion="Repetir el mismo mensaje no debería reiniciar el flujo en bucle infinito.",
        resolucion_n1_esperada=True,
        tags=["bucle", "robustez"],
        turnos=[
            Turno("No tengo internet", espera_autodiagnostico=True),
            Turno("No tengo internet", espera_autodiagnostico=True),
            Turno("No tengo internet", espera_autodiagnostico=True),
        ],
    ),
    Escenario(
        id="E14",
        nombre="Ecolan B2B / Data Center",
        categoria="ecolan_b2b",
        descripcion="Debe clasificar B2B y orientar/derivar a especialista.",
        resolucion_n1_esperada=False,
        tags=["b2b"],
        turnos=[
            Turno(
                "Hola, tenemos una VM en el data center de Ecolan que no responde",
                no_debe_ticket_prematuro=True,
            ),
            Turno(
                "Está caída ahora, impacto productivo",
                ticket_aceptable=True,
            ),
        ],
    ),
    Escenario(
        id="E15",
        nombre="Teléfono fijo sin tono",
        categoria="telefono_fija",
        descripcion="Chequeos básicos de tono/cable antes de derivar.",
        resolucion_n1_esperada=True,
        tags=["fija"],
        turnos=[
            Turno(
                "El teléfono fijo no tiene tono",
                espera_autodiagnostico=True,
                no_debe_ticket_prematuro=True,
            ),
            Turno(
                "El cable está bien enchufado y sigue sin tono",
                ticket_aceptable=True,
            ),
        ],
    ),
]
