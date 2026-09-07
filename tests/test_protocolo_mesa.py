"""Protocolo de mesa: oficio del técnico + voz al abonado."""

from __future__ import annotations

from types import SimpleNamespace

from app.radius.contract import EstadoConexionPPPoE, ServicioConectividad
from app.services.eco_voice import sanitizar_voz_abonado, system_prompt_eco_n1
from app.services.protocolo_mesa import clasificar_cuenta, rama_comercial
from app.uisp.contract import EstadoCpeUisp


def test_habilitado_no_es_comercial():
    svc = ServicioConectividad(
        login="palaciosvaleBAI",
        state="Habilitado",
        product="Internet acceso Bai Hogar 15MB",
        service_on=True,
    )
    abo = SimpleNamespace(estado="activo", servicio="internet")
    assert clasificar_cuenta(abo, svc) == "activa"
    assert rama_comercial(abo, svc) is False


def test_historico_baja_es_comercial():
    svc = ServicioConectividad(login="x", state="Baja", service_on=False)
    abo = SimpleNamespace(estado="activo", servicio="internet")
    assert clasificar_cuenta(abo, svc) == "baja"
    assert rama_comercial(abo, svc) is True


def test_voz_nunca_dice_padron_ni_herramientas():
    sucio = (
        "En el padrón BillTrack el login no está en UISP ni BCM. "
        "Radius no respondió."
    )
    limpio = sanitizar_voz_abonado(sucio)
    assert "padrón" not in limpio.lower()
    assert "padron" not in limpio.lower()
    assert "billtrack" not in limpio.lower()
    assert "uisp" not in limpio.lower()
    assert "bcm" not in limpio
    assert "radius" not in limpio.lower()
    assert "sistema" in limpio.lower() or "red" in limpio.lower()


def test_prompt_n1_incluye_protocolo_de_mesa():
    p = system_prompt_eco_n1(
        intencion="internet",
        turnos=0,
        min_turnos_antes_escalar=4,
    )
    assert "Protocolo de mesa" in p
    assert "padrón" in p.lower()  # la prohibición nombra la palabra
    assert "Nunca digas" in p or "nunca digas" in p.lower()


def test_palacios_no_abre_uisp_si_fuera_baja():
    """Contrato: baja real no consulta planta. Palacios es Habilitado, sí consulta."""
    hab = ServicioConectividad(
        login="palaciosvaleBAI",
        state="Habilitado",
        service_type_code="INTBA",
        service_on=True,
    )
    baja = ServicioConectividad(login="viejo10", state="Baja", service_on=False)
    abo = SimpleNamespace(estado="activo")
    assert rama_comercial(abo, hab) is False
    assert rama_comercial(abo, baja) is True
    cpe = EstadoCpeUisp(login="palaciosvaleBAI", encontrado=False)
    from app.services.protocolo_mesa import decidir_mensaje_mesa

    msg = decidir_mensaje_mesa(
        EstadoConexionPPPoE(servicio=hab, error="timeout"),
        abonado=abo,
        cpe=cpe,
        es_radio=True,
    )
    assert msg
    assert "enlazada" in msg.lower()
    assert "inyecto" in msg.lower() or "poe" in msg.lower()
