"""H28: ningún secreto sale en los logs (credenciales BCM en la query que httpx loguea, tokens, contraseñas)."""

from __future__ import annotations

import logging

import httpx
import pytest

from app.bcm.client import BcmClient
from app.log_redaction import (
    instalar_redaccion_logs,
    redactar,
    redactar_breadcrumb_sentry,
    redactar_evento_sentry,
)

SECRETO = "FAKE-SECRET-123"
TOKEN = "FAKE-TOKEN-4567890123"  # ≥16 caracteres: lo que BCM acepta como token opaco


def _sin_secretos(caplog, *secretos: str) -> None:
    for rec in caplog.records:
        texto = " ".join([rec.getMessage(), rec.exc_text or "", rec.stack_info or ""])
        for s in secretos:
            assert s not in texto, (rec.name, texto)
    for s in secretos:
        assert s not in caplog.text


@pytest.fixture
def logs(caplog):
    instalar_redaccion_logs()
    # Aun con httpx en DEBUG (peor caso: alguien vuelve a subir el nivel) el filtro tiene que tapar el secreto.
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="httpx")
    caplog.set_level(logging.DEBUG, logger="operations_hub")
    return caplog


def _bcm(handler) -> BcmClient:
    cli = BcmClient(
        base_url="https://bcm.example.test/api/v1", user="usuario-app", app_pass=SECRETO
    )
    cli._client = lambda: httpx.Client(transport=httpx.MockTransport(handler))  # type: ignore[method-assign]
    return cli


def test_bcm_auth_y_consulta_no_dejan_credenciales_en_logs(logs):
    enviados: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        enviados.append(str(req.url))
        if req.url.path.endswith("/auth/obtenerToken"):
            return httpx.Response(200, json={"token": TOKEN})
        return httpx.Response(200, json={"numero": "123"})

    cli = _bcm(handler)
    cli.buscar_onu_por_cliente("123")
    # El contrato con BCM no cambia: las credenciales siguen viajando (solo se tapan en los logs).
    assert any(SECRETO in u for u in enviados) and any(TOKEN in u for u in enviados)
    httpx_recs = [r for r in logs.records if r.name == "httpx"]
    assert httpx_recs and all("***" in r.getMessage() for r in httpx_recs)
    _sin_secretos(logs, SECRETO, TOKEN)


def test_bcm_errores_con_params_y_excepciones_no_dejan_credenciales(logs):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/auth/obtenerToken"):
            return httpx.Response(200, json={"token": TOKEN})
        if "modificarWifi" in req.url.path:
            return httpx.Response(500, text=f"error con {req.url}")
        raise httpx.ConnectError(f"no conecta: {req.url}", request=req)

    cli = _bcm(handler)
    cli.modificar_wifi_password_por_serial(
        "SERIAL1", "wifi-" + SECRETO, "2"
    )  # log params=… de la respuesta no 2xx
    estado = cli.buscar_onu_por_cliente("123")  # logger.exception con la URL en la excepción
    assert SECRETO not in estado.error and TOKEN not in estado.error
    assert any(r.exc_text for r in logs.records)
    _sin_secretos(logs, SECRETO, TOKEN)


def test_bcm_auth_fallida_no_loguea_el_cuerpo_con_secretos(logs):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=f"usuario=usuario-app&contrasenaapp={SECRETO}")

    with pytest.raises(RuntimeError):
        _bcm(handler).authenticate()
    _sin_secretos(logs, SECRETO)


@pytest.mark.parametrize(
    "texto",
    [
        f"GET https://bcm/api/auth/obtenerToken?usuario=u&contrasenaapp={SECRETO}",
        f"GET https://bcm/api/cliente?usuario=u&token={SECRETO}&numero=1",
        f"https://x/y?ContrasenaApp={SECRETO}",
        f"PASSWORD={SECRETO}",
        f"passwd={SECRETO}; otra=1",
        f"clave={SECRETO}",
        f"api_key={SECRETO}",
        f"apiKey: {SECRETO}",
        f"key={SECRETO}",
        f"client_secret={SECRETO}",
        f"x-auth-token: {SECRETO}",
        f"access_token={SECRETO}",
        f"Authorization: Bearer {SECRETO}",
        f"authorization: Basic {SECRETO}",
        f'{{"password": "{SECRETO}", "user": "u"}}',
        f"{{'token': '{SECRETO}', 'numero': '1'}}",
        f"postgresql://ops:{SECRETO}@db:5432/estate",
        f"https://api.telegram.org/bot123456:{SECRETO}/sendMessage",
        f"https://ov/link?celular={SECRETO}&path=/pagar",
        f"contrase%C3%B1a={SECRETO}",
        "jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJGQUtFIn0.FAKEFAKEFAKEFAKE",
    ],
)
def test_redactar_formatos(texto):
    out = redactar(texto)
    assert SECRETO not in out and "FAKEFAKE" not in out and "***" in out, out


@pytest.mark.parametrize(
    "texto",
    [
        "llm_ok model=x latency_ms=12 tokens=345",
        "total_tokens=345 prompt_tokens=10",
        "BCM auth: la respuesta no trajo token (HTTP 200; claves=token,data)",
        "OV /ov/link no OK status_http=500 cel_len=10",
        "numero=123 wifi=2 status=500",
        "eko_journey {'event': 'journey.started', 'step': 'diagnostic'}",
    ],
)
def test_redactar_no_toca_lo_que_no_es_secreto(texto):
    assert redactar(texto) == texto


def test_filtro_cubre_args_y_trazas(logs):
    log = logging.getLogger("operations_hub")
    log.info("params=%s", {"usuario": "u", "token": SECRETO})
    try:
        raise RuntimeError(f"falló https://bcm/x?contrasenaapp={SECRETO}")
    except RuntimeError:
        log.exception("BCM falló")
    log.warning("pila", stack_info=True, extra={"x": 1})
    logging.getLogger("otro.modulo").error("Authorization: Bearer %s", SECRETO)
    _sin_secretos(logs, SECRETO)
    assert (
        "'usuario': 'u'" in logs.text and "BCM falló" in logs.text and "RuntimeError" in logs.text
    )


def test_args_en_tupla_se_conservan_para_formatters_que_los_desempaquetan(logs):
    # Formato del access log de uvicorn: AccessFormatter desempaqueta record.args en 5 posiciones.
    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d', "10.0.0.1", "GET", f"/api/v1/x?token={SECRETO}&a=1", "1.1", 200
    )
    rec = [r for r in logs.records if r.name == "uvicorn.access"][-1]
    assert isinstance(rec.args, tuple) and len(rec.args) == 5 and rec.args[4] == 200
    assert rec.getMessage() == '10.0.0.1 - "GET /api/v1/x?token=***&a=1 HTTP/1.1" 200'
    _sin_secretos(logs, SECRETO)


def test_instalar_es_idempotente_y_baja_httpx():
    instalar_redaccion_logs()
    factory = logging.getLogRecordFactory()
    instalar_redaccion_logs()
    assert logging.getLogRecordFactory() is factory
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def test_logs_de_journey_siguen_igual(logs):
    from app.services.eko_journey_observability import emit_journey_event

    emit_journey_event(
        "journey.started",
        journey="internet_sin_conectividad",
        step="diagnostic",
        correlation_id="c-123",
        channel="portal",
    )
    recs = [r.getMessage() for r in logs.records if r.getMessage().startswith("eko_journey ")]
    assert recs, logs.text
    msg = recs[-1]
    for frag in (
        "'event': 'journey.started'",
        "'journey': 'internet_sin_conectividad'",
        "'step': 'diagnostic'",
        "'correlation_id': 'c-123'",
        "'channel': 'portal'",
    ):
        assert frag in msg, msg
    assert "***" not in msg


def test_sentry_breadcrumb_y_evento_sin_secretos():
    crumb = redactar_breadcrumb_sentry(
        {
            "type": "http",
            "data": {
                "url": f"https://bcm/x?token={SECRETO}",
                "http.query": f"usuario=u&contrasenaapp={SECRETO}",
            },
        }
    )
    ev = redactar_evento_sentry(
        {
            "exception": {
                "values": [{"type": "ConnectError", "value": f"https://bcm/x?token={SECRETO}"}]
            },
            "logentry": {"message": f"token={SECRETO}"},
        }
    )
    assert SECRETO not in repr(crumb) and SECRETO not in repr(ev)
    assert crumb["data"]["http.query"] == "usuario=u&contrasenaapp=***"
