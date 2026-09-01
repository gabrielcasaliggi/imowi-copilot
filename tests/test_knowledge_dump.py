"""El dump markdown es opcional y no se indexa dos veces."""

from __future__ import annotations

import pytest

import app.knowledge_rag as kr

_MD = """## WiFi lento en el hogar

El abonado reporta navegación lenta en la red WiFi del CPE. Verificar canal,
interferencia y que el equipo esté en línea antes de escalar a N2.
"""


@pytest.fixture(autouse=True)
def _restore_kb():
    old = (kr._bloques, kr._indice_invertido, kr._cargado, kr._fuentes)
    yield
    kr._bloques, kr._indice_invertido, kr._cargado, kr._fuentes = old


_MD = """## WiFi lento en el hogar

El abonado reporta navegación lenta en la red WiFi del CPE. Verificar canal,
interferencia y que el equipo esté en línea antes de escalar a N2.
"""


def test_sin_dump_carga_vacia(tmp_path, monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_FILE", raising=False)
    info = kr.cargar_base_conocimiento(tmp_path)
    assert info["bloques"] == 0
    assert info["archivo"] == "(sin dump markdown)"
    assert kr.resolver_fuentes_conocimiento(tmp_path) == []


def test_dump_en_data_no_en_git(tmp_path, monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_FILE", raising=False)
    data = tmp_path / "data"
    data.mkdir()
    (data / "base_conocimiento.md").write_text(_MD, encoding="utf-8")
    fuentes = kr.resolver_fuentes_conocimiento(tmp_path)
    assert fuentes == [data / "base_conocimiento.md"]
    info = kr.cargar_base_conocimiento(tmp_path)
    assert info["bloques"] == 1


def test_knowledge_file_env(tmp_path, monkeypatch):
    extra = tmp_path / "kb.md"
    extra.write_text(_MD, encoding="utf-8")
    monkeypatch.setenv("KNOWLEDGE_FILE", str(extra))
    assert kr.resolver_fuentes_conocimiento(tmp_path) == [extra]


def test_raiz_no_indexa_dos_nombres(tmp_path, monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_FILE", raising=False)
    (tmp_path / "base_conocimiento.md").write_text(_MD, encoding="utf-8")
    (tmp_path / "Base_de_Conocimiento_Tickets.md").write_text(_MD, encoding="utf-8")
    fuentes = kr.resolver_fuentes_conocimiento(tmp_path)
    assert len(fuentes) == 1
    assert fuentes[0].name == "base_conocimiento.md"
