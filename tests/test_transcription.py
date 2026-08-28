"""Tests de transcripción de audio (Whisper local)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_transcribir_audio_deshabilitado(monkeypatch):
    monkeypatch.setattr("app.services.transcription.WHISPER_ENABLED", False)
    from app.services.transcription import transcribir_audio

    assert transcribir_audio(b"fake") == ""


def test_transcribir_audio_ok(monkeypatch):
    monkeypatch.setattr("app.services.transcription.WHISPER_ENABLED", True)
    monkeypatch.setattr("app.services.transcription.WHISPER_URL", "http://whisper.test")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"text":"hola se me corto internet"}'
    mock_resp.json.return_value = {"text": "hola se me corto internet"}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return mock_resp

    monkeypatch.setattr("app.services.transcription.httpx.Client", _Client)
    from app.services.transcription import transcribir_audio

    assert "internet" in transcribir_audio(b"ogg-bytes")


def test_texto_desde_audio_whatsapp_none_si_no_audio():
    from app.services.transcription import texto_desde_audio_whatsapp

    assert texto_desde_audio_whatsapp({"type": "text", "text": {"body": "hola"}}) is None


def test_texto_desde_audio_whatsapp_transcribe(monkeypatch):
    monkeypatch.setattr("app.services.transcription.WHISPER_ENABLED", True)
    monkeypatch.setattr(
        "app.services.transcription.transcribir_audio",
        lambda *_a, **_k: "se me cortó internet",
    )
    monkeypatch.setattr(
        "app.services.whatsapp_client.descargar_media",
        lambda _id: b"fake-ogg",
    )
    from app.services.transcription import texto_desde_audio_whatsapp

    out = texto_desde_audio_whatsapp(
        {"type": "audio", "audio": {"id": "media-1", "mime_type": "audio/ogg"}}
    )
    assert out == "se me cortó internet"


def test_texto_desde_audio_whatsapp_pasa_prompt(monkeypatch):
    monkeypatch.setattr("app.services.transcription.WHISPER_ENABLED", True)
    captured: dict = {}

    def _fake_transcribir(*_a, **kwargs):
        captured.update(kwargs)
        return "mi dni es 12345678"

    monkeypatch.setattr(
        "app.services.transcription.transcribir_audio",
        _fake_transcribir,
    )
    monkeypatch.setattr(
        "app.services.whatsapp_client.descargar_media",
        lambda _id: b"fake-ogg",
    )
    from app.services.transcription import WHISPER_PROMPT_DNI, texto_desde_audio_whatsapp

    out = texto_desde_audio_whatsapp(
        {"type": "audio", "audio": {"id": "media-1", "mime_type": "audio/ogg"}},
        prompt=WHISPER_PROMPT_DNI,
    )
    assert out == "mi dni es 12345678"
    assert captured.get("prompt") == WHISPER_PROMPT_DNI


def test_texto_desde_audio_telegram_voice(monkeypatch):
    monkeypatch.setattr("app.services.transcription.WHISPER_ENABLED", True)
    monkeypatch.setattr(
        "app.services.transcription.transcribir_audio",
        lambda *_a, **_k: "necesito ayuda con el wifi",
    )
    monkeypatch.setattr(
        "app.services.telegram_client.descargar_archivo",
        lambda _id: b"fake-opus",
    )
    from app.services.transcription import texto_desde_audio_telegram

    out = texto_desde_audio_telegram(
        {
            "message_id": 1,
            "chat": {"id": 99},
            "voice": {"file_id": "AgAD", "mime_type": "audio/ogg"},
        }
    )
    assert "wifi" in (out or "")


def test_whatsapp_webhook_audio_inyecta_texto(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.whatsapp.resolve_whatsapp",
        lambda _db=None: {
            "token": "",
            "phone_number_id": "",
            "verify_token": "ops-hub-wa-verify",
            "app_secret": "",
            "default_org_slug": "coop-batan",
        },
    )
    monkeypatch.setattr("app.api.v1.whatsapp.es_produccion", lambda: False)
    monkeypatch.setattr(
        "app.services.transcription.texto_desde_audio_whatsapp",
        lambda _msg, **_k: "hola soy la vecina y se me cortó internet",
    )
    called = {}

    def _fake_procesar(db, org_id, **kwargs):
        called.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr("app.api.v1.whatsapp.procesar_mensaje_entrante", _fake_procesar)

    body = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messages": [
                                {
                                    "from": "5492231112233",
                                    "id": "wamid.AUDIO1",
                                    "type": "audio",
                                    "audio": {"id": "media-x"},
                                }
                            ]
                        },
                    }
                ]
            }
        ],
    }
    r = client.post(
        "/api/v1/whatsapp/webhook",
        content=json.dumps(body),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200
    assert called.get("texto", "").startswith("hola soy la vecina")
    assert called.get("canal") == "whatsapp"


def test_whatsapp_webhook_audio_fallback(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.whatsapp.resolve_whatsapp",
        lambda _db=None: {
            "token": "",
            "phone_number_id": "",
            "verify_token": "ops-hub-wa-verify",
            "app_secret": "",
            "default_org_slug": "coop-batan",
        },
    )
    monkeypatch.setattr("app.api.v1.whatsapp.es_produccion", lambda: False)
    monkeypatch.setattr(
        "app.services.transcription.texto_desde_audio_whatsapp",
        lambda _msg, **_k: "",
    )
    sent = {}

    def _fake_enviar(to, texto):
        sent["to"] = to
        sent["texto"] = texto
        return {"ok": True, "simulated": True}

    monkeypatch.setattr("app.services.whatsapp_client.enviar_texto", _fake_enviar)
    monkeypatch.setattr(
        "app.api.v1.whatsapp.procesar_mensaje_entrante",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no LLM")),
    )

    body = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messages": [
                                {
                                    "from": "5492231112233",
                                    "id": "wamid.AUDIO2",
                                    "type": "audio",
                                    "audio": {"id": "media-y"},
                                }
                            ]
                        },
                    }
                ]
            }
        ],
    }
    r = client.post(
        "/api/v1/whatsapp/webhook",
        content=json.dumps(body),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200
    assert "audio" in (sent.get("texto") or "").lower() or "escrib" in (
        sent.get("texto") or ""
    ).lower()


def test_telegram_webhook_voice_inyecta_texto(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.telegram.resolve_telegram",
        lambda _db=None: {
            "bot_token": "",
            "webhook_secret": "",
            "default_org_slug": "coop-batan",
        },
    )
    monkeypatch.setattr("app.api.v1.telegram.es_produccion", lambda: False)
    monkeypatch.setattr(
        "app.services.transcription.texto_desde_audio_telegram",
        lambda _msg: "se me cortó internet recién",
    )
    called = {}

    def _fake_procesar(db, org_id, **kwargs):
        called.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr("app.api.v1.telegram.procesar_mensaje_entrante", _fake_procesar)

    body = {
        "update_id": 9,
        "message": {
            "message_id": 77,
            "chat": {"id": 888001},
            "voice": {"file_id": "voice-1", "duration": 3},
        },
    }
    r = client.post(
        "/api/v1/telegram/webhook",
        content=json.dumps(body),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200
    assert "internet" in called.get("texto", "")
    assert called.get("canal") == "telegram"


def test_extraer_texto_mensaje_wa_audio_placeholder():
    """Sin STT en extractor puro, audio sigue siendo placeholder."""
    from app.api.v1.whatsapp import _extraer_texto_mensaje

    assert _extraer_texto_mensaje({"type": "audio", "audio": {"id": "x"}}) == "[audio]"
