"""Tests del filtro previo conversacional."""

from app.services.prefilter import analizar_relevancia


def test_saludo_responde_cortes_sin_rechazo():
    r = analizar_relevancia("buenos días")
    assert r["relevante"] is False
    assert r["motivo"] == "saludo"
    assert "Buen día" in r["respuesta_corta"]
    assert "No detecté" not in r["respuesta_corta"]


def test_mensaje_ambiguo_pide_contexto_con_buen_tono():
    r = analizar_relevancia("consulta")
    assert r["relevante"] is False
    assert "necesito un poco más de contexto" in r["respuesta_corta"]
