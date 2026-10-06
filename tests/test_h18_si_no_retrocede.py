"""H18: el mensaje de «un solo dispositivo» / «sin cable en celular» no se re-emite si ya salió en los últimos 6 turnos."""

from __future__ import annotations

from app.domain.flujos_abonado import MSG_WIFI_UN_DISPOSITIVO_MOVIL, ya_emitido_reciente


def _hist(*bot):
    return [{"rol": "bot", "texto": t} for t in bot]


def test_detecta_el_mensaje_ya_emitido():
    assert ya_emitido_reciente(MSG_WIFI_UN_DISPOSITIVO_MOVIL, _hist("hola", MSG_WIFI_UN_DISPOSITIVO_MOVIL))


def test_fuera_de_la_ventana_de_6_turnos_se_puede_repetir():
    assert not ya_emitido_reciente(MSG_WIFI_UN_DISPOSITIVO_MOVIL, _hist(MSG_WIFI_UN_DISPOSITIVO_MOVIL, *["x"] * 6))


def test_un_mensaje_del_cliente_no_cuenta():
    assert not ya_emitido_reciente("hola", [{"rol": "cliente", "texto": "hola"}])
