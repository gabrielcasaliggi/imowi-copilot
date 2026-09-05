"""Lectura forzada E1: OLT/WIS al agotar 3 turnos sin resolución de acceso."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.bcm.contract import EstadoOnuBcm
from app.services.turno_e1 import ejecutar_lectura_forzada_e1
from app.uisp.contract import EstadoCpeUisp


def test_ejecutar_escala_si_olt_fuera_de_parametro(monkeypatch):
    onu = EstadoOnuBcm(
        numero_cliente="99",
        encontrado=True,
        online=True,
        rx_dbm=-29.5,
        calidad_optica="mala",
        olt_nombre="OLT-Test",
    )
    monkeypatch.setattr(
        "app.services.conexion_bcm.resolve_bcm_client", lambda db=None: object()
    )
    monkeypatch.setattr(
        "app.services.conexion_bcm.consultar_onu_bcm_mejor_esfuerzo",
        lambda *a, **k: onu,
    )
    ctx: dict = {"tecnologia_acceso": "internet_ftth"}
    abo = SimpleNamespace(dni="30111222", client_number="99")
    out = ejecutar_lectura_forzada_e1(MagicMock(), abo, ctx, "internet_ftth")
    assert out.accion == "escalate"
    assert out.veredicto == "acceso_malo"
    assert "visita" in out.mensaje.lower()
    assert ctx.get("bcm_rama") == "potencia_mala"


def test_ejecutar_sigue_en_casa_si_olt_ok(monkeypatch):
    onu = EstadoOnuBcm(
        numero_cliente="99",
        encontrado=True,
        online=True,
        rx_dbm=-18.0,
        calidad_optica="buena",
    )
    monkeypatch.setattr(
        "app.services.conexion_bcm.resolve_bcm_client", lambda db=None: object()
    )
    monkeypatch.setattr(
        "app.services.conexion_bcm.consultar_onu_bcm_mejor_esfuerzo",
        lambda *a, **k: onu,
    )
    ctx: dict = {"tecnologia_acceso": "internet_ftth"}
    out = ejecutar_lectura_forzada_e1(MagicMock(), SimpleNamespace(dni="1"), ctx, "internet_ftth")
    assert out.accion == "ask"
    assert out.veredicto == "acceso_ok"
    assert ctx.get("wifi_rama_activada") is True
    msg = out.mensaje.lower().replace("\u2011", "-").replace("\u2013", "-")
    assert "wifi" in msg.replace("-", "") or "wi-fi" in msg


def test_ejecutar_escala_si_wis_offline(monkeypatch):
    cpe = EstadoCpeUisp(
        login="casaBAI",
        encontrado=True,
        online=False,
        signal_dbm=None,
    )
    monkeypatch.setattr(
        "app.services.conexion_uisp.resolve_uisp_client", lambda db=None: object()
    )
    monkeypatch.setattr(
        "app.services.conexion_uisp.consultar_cpe_uisp", lambda *a, **k: cpe
    )
    ctx: dict = {"tecnologia_acceso": "internet_radio", "pppoe_login": "casaBAI"}
    out = ejecutar_lectura_forzada_e1(MagicMock(), SimpleNamespace(dni="1"), ctx, "internet_radio")
    assert out.accion == "escalate"
    assert out.veredicto == "acceso_malo"
    assert "antena" in out.mensaje.lower()


def test_ejecutar_skip_si_no_hay_cliente(monkeypatch):
    monkeypatch.setattr(
        "app.services.conexion_bcm.resolve_bcm_client", lambda db=None: None
    )
    ctx: dict = {"tecnologia_acceso": "internet_ftth"}
    out = ejecutar_lectura_forzada_e1(MagicMock(), SimpleNamespace(dni="1"), ctx, "internet_ftth")
    assert out.accion == "skip"
    assert out.veredicto == "sin_dato"


def test_controlador_e1_deriva_con_olt_mala(monkeypatch):
    from app.services.canal_diagnostico_ia import _aplicar_diagnostico_ia

    onu = EstadoOnuBcm(
        numero_cliente="99",
        encontrado=True,
        online=True,
        rx_dbm=-29.5,
        calidad_optica="mala",
        olt_nombre="OLT-Test",
    )
    monkeypatch.setattr(
        "app.services.conexion_bcm.resolve_bcm_client", lambda db=None: object()
    )
    monkeypatch.setattr(
        "app.services.conexion_bcm.consultar_onu_bcm_mejor_esfuerzo",
        lambda *a, **k: onu,
    )
    sent: list[str] = []
    monkeypatch.setattr(
        "app.services.canal_abonado._enviar_respuesta",
        lambda *_a, **_k: sent.append(_a[3] if len(_a) > 3 else _k.get("texto", "")),
    )
    monkeypatch.setattr(
        "app.services.canal_abonado._crear_ticket_n2",
        lambda *_a, **_k: "TK-E1-OLT",
    )
    monkeypatch.setattr(
        "app.services.canal_abonado.crepo.set_contexto",
        lambda *_a, **_k: None,
    )
    db = MagicMock()
    conv = SimpleNamespace(id="c-e1", estado="bot", ticket_id="")
    ctx = {
        "diag_turnos": 3,
        "tecnologia_acceso": "internet_ftth",
        "pasos_cubiertos": [],
    }
    abo = SimpleNamespace(dni="30111222", client_number="99", nombre="Test")
    out = _aplicar_diagnostico_ia(
        db,
        "org-test",
        conv,  # type: ignore[arg-type]
        abo,  # type: ignore[arg-type]
        "sigue sin internet",
        canal="whatsapp",
        ctx=ctx,
        intencion="internet_ftth",
        usar_llama=False,
    )
    assert out is not None
    assert out.get("ticket_id") == "TK-E1-OLT"
    assert out.get("lectura_forzada_e1") is True
    assert out.get("lectura_forzada_e1_veredicto") == "acceso_malo"
    assert ctx.get("lectura_forzada_e1") is True
    assert sent
    assert "visita" in sent[0].lower() or "agente" in sent[0].lower()
