"""Replay N1 con planta mock: enlace OK → Wi‑Fi; ONU offline → PON."""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app
from qa_bot.corpus_botmaker import CasoBotmaker
from qa_bot.eval_masivo import replay_caso

client = TestClient(app)

_CASO = CasoBotmaker(
    id="eval-planta-apertura",
    categoria="internet",
    apertura="Hola no tengo internet",
    turnos_usuario=["Hola no tengo internet"],
    n_user=1,
    fuente="test",
)


def _bot_t1(r) -> str:
    assert not r.error, r.error
    assert r.turnos, r
    return (r.turnos[0].get("bot") or "").lower().replace("‑", "-").replace("–", "-")


def test_replay_enlace_ok_pregunta_wifi_no_luces():
    r = replay_caso(client, _CASO, max_turnos=1, planta="enlace_ok")
    bot = _bot_t1(r)
    assert "ont" in bot or "potencia" in bot, bot
    assert "wifi" in bot or "wi-fi" in bot
    assert "dispositivo" in bot or "cable" in bot
    assert "lucecita" not in bot
    assert "pon" not in bot
    assert "los)" not in bot
    assert "cajita" not in bot


def test_replay_onu_offline_pregunta_luces_no_wifi():
    r = replay_caso(client, _CASO, max_turnos=1, planta="onu_offline")
    bot = _bot_t1(r)
    assert "ont" in bot, bot
    assert "pon" in bot or "lucecita" in bot
    assert "wifi" not in bot
    assert "wi-fi" not in bot
    assert "dispositivo" not in bot
