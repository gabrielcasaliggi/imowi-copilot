"""
Motor RAG simplificado: parseo de Markdown + búsqueda por palabras clave.
Pensado para Llama local sin base vectorial.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from app.config import KNOWLEDGE_MIN_SCORE, KNOWLEDGE_TOP_K

# ─── Estado global (cargado en startup) ───
_bloques: list["BloqueConocimiento"] = []
_indice_invertido: dict[str, set[int]] = {}
_cargado: bool = False
_ruta_archivo: Path | None = None


@dataclass
class BloqueConocimiento:
    id: str
    titulo: str
    contenido: str
    texto_busqueda: str
    tokens: set[str] = field(default_factory=set)


@dataclass
class ResultadoBusqueda:
    encontrado: bool
    bloque: BloqueConocimiento | None = None
    puntaje: float = 0.0
    modo: str = "escalamiento"  # "resolucion" | "escalamiento"


STOPWORDS = frozenset(
    """
    el la los las un una unos unas de del al a y en que es por para con su sus
    se lo le da do eso esta este estos esas como mas pero sin sobre entre hasta
    hay ser fue son era eran muy tambien ya solo cada cuando donde quien cual
    """.split()
)


def _normalizar_texto(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    return re.sub(r"\s+", " ", t).strip()


def tokenizar(texto: str) -> set[str]:
    tokens = set()
    for palabra in _normalizar_texto(texto).split():
        if len(palabra) > 2 and palabra not in STOPWORDS:
            tokens.add(palabra)
    return tokens


def _extraer_subseccion(contenido: str, nombre: str) -> str:
    patron = rf"###\s*{re.escape(nombre)}\s*\n(.*?)(?=###|\Z)"
    m = re.search(patron, contenido, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _construir_texto_busqueda(contenido: str) -> str:
    problema = _extraer_subseccion(contenido, "Problema")
    preguntas = _extraer_subseccion(contenido, "Preguntas / Verificaciones")
    resolucion = _extraer_subseccion(contenido, "Resolucion") or _extraer_subseccion(
        contenido, "Resolución"
    )
    partes = [p for p in (problema, preguntas, resolucion) if p and p != "."]
    return " ".join(partes) if partes else contenido[:1500]


def parsear_markdown(contenido: str) -> list[BloqueConocimiento]:
    """Segmenta por encabezados ## (cada KB es un bloque)."""
    bloques: list[BloqueConocimiento] = []
    partes = re.split(r"(?=^##\s+)", contenido, flags=re.MULTILINE)

    for parte in partes:
        parte = parte.strip()
        if not parte or not parte.startswith("##"):
            continue

        lineas = parte.split("\n", 1)
        titulo_raw = lineas[0].lstrip("#").strip()
        cuerpo = lineas[1].strip() if len(lineas) > 1 else ""

        if len(cuerpo) < 20:
            continue

        bloque_id = titulo_raw.replace(" ", "-")[:80]
        texto_busqueda = _construir_texto_busqueda(cuerpo)
        if len(_normalizar_texto(texto_busqueda)) < 15:
            continue

        bloques.append(
            BloqueConocimiento(
                id=bloque_id,
                titulo=titulo_raw,
                contenido=cuerpo,
                texto_busqueda=texto_busqueda,
                tokens=tokenizar(f"{titulo_raw} {texto_busqueda}"),
            )
        )

    return bloques


def _construir_indice_invertido(bloques: list[BloqueConocimiento]) -> dict[str, set[int]]:
    indice: dict[str, set[int]] = {}
    for i, bloque in enumerate(bloques):
        for token in bloque.tokens:
            indice.setdefault(token, set()).add(i)
    return indice


def resolver_ruta_base_conocimiento(raiz: Path | None = None) -> Path:
    raiz = raiz or Path(__file__).resolve().parent.parent
    candidatos = (
        "base_conocimiento.md",
        "Base_de_Conocimiento_Tickets.md",
        "base_conocimiento_tickets.md",
    )
    for nombre in candidatos:
        ruta = raiz / nombre
        if ruta.is_file():
            return ruta
    raise FileNotFoundError(
        f"No se encontró base de conocimiento en {raiz}. "
        f"Colocá base_conocimiento.md o Base_de_Conocimiento_Tickets.md"
    )


def cargar_base_conocimiento(raiz: Path | None = None) -> dict:
    """Invocar en startup de la aplicación."""
    global _bloques, _indice_invertido, _cargado, _ruta_archivo

    _ruta_archivo = resolver_ruta_base_conocimiento(raiz)
    contenido = _ruta_archivo.read_text(encoding="utf-8", errors="replace")
    _bloques = parsear_markdown(contenido)
    _indice_invertido = _construir_indice_invertido(_bloques)
    _cargado = True

    return {
        "archivo": str(_ruta_archivo),
        "bloques": len(_bloques),
        "tokens_indice": len(_indice_invertido),
    }


def esta_cargado() -> bool:
    return _cargado


def estadisticas() -> dict:
    return {
        "cargado": _cargado,
        "archivo": str(_ruta_archivo) if _ruta_archivo else None,
        "total_bloques": len(_bloques),
    }


def _puntaje_bloque(query_tokens: set[str], bloque: BloqueConocimiento) -> float:
    if not query_tokens or not bloque.tokens:
        return 0.0

    interseccion = query_tokens & bloque.tokens
    if not interseccion:
        return 0.0

    # Cobertura de la consulta + bonus por densidad en texto de problema
    cobertura = len(interseccion) / len(query_tokens)
    densidad = len(interseccion) / max(len(bloque.tokens), 1)
    texto_norm = _normalizar_texto(bloque.texto_busqueda)

    bonus_frase = 0.0
    query_texto = " ".join(sorted(query_tokens))
    if len(query_texto) > 8 and query_texto[:40] in texto_norm:
        bonus_frase = 0.25

    return min(1.0, cobertura * 0.65 + densidad * 0.2 + bonus_frase)


def buscar_contexto(
    consulta: str,
    *,
    min_score: float | None = None,
    top_k: int | None = None,
) -> ResultadoBusqueda:
    """
    Busca el bloque más relevante comparando títulos y contenido.
    """
    if not _cargado or not _bloques:
        return ResultadoBusqueda(encontrado=False, modo="escalamiento")

    min_score = min_score if min_score is not None else KNOWLEDGE_MIN_SCORE
    top_k = top_k or KNOWLEDGE_TOP_K
    query_tokens = tokenizar(consulta)

    if not query_tokens:
        return ResultadoBusqueda(encontrado=False, modo="escalamiento")

    # Candidatos vía índice invertido (acelera con miles de bloques)
    candidatos_idx: set[int] = set()
    for token in query_tokens:
        candidatos_idx.update(_indice_invertido.get(token, ()))

    if not candidatos_idx:
        candidatos_idx = set(range(min(len(_bloques), 500)))

    puntajes: list[tuple[float, int]] = []
    for idx in candidatos_idx:
        if idx >= len(_bloques):
            continue
        p = _puntaje_bloque(query_tokens, _bloques[idx])
        if p > 0:
            puntajes.append((p, idx))

    if not puntajes:
        return ResultadoBusqueda(encontrado=False, modo="escalamiento")

    puntajes.sort(reverse=True, key=lambda x: x[0])
    mejor_puntaje, mejor_idx = puntajes[0]

    mejor_bloque = _bloques[mejor_idx]
    interseccion = query_tokens & mejor_bloque.tokens

    # Evitar falsos positivos: exigir score mínimo y al menos 2 términos coincidentes
    if mejor_puntaje < min_score or len(interseccion) < 2:
        return ResultadoBusqueda(encontrado=False, puntaje=mejor_puntaje, modo="escalamiento")

    bloque = mejor_bloque
    return ResultadoBusqueda(
        encontrado=True,
        bloque=bloque,
        puntaje=mejor_puntaje,
        modo="resolucion",
    )


def formatear_contexto_para_prompt(resultado: ResultadoBusqueda, max_chars: int = 6000) -> str:
    if not resultado.encontrado or not resultado.bloque:
        return ""

    b = resultado.bloque
    preguntas = _extraer_subseccion(b.contenido, "Preguntas / Verificaciones")
    resolucion = _extraer_subseccion(b.contenido, "Resolucion") or _extraer_subseccion(
        b.contenido, "Resolución"
    )
    problema_kb = _extraer_subseccion(b.contenido, "Problema")

    encabezado = (
        f"═══ CASO SIMILAR EN KB ({b.titulo}) — similitud {resultado.puntaje:.0%} — MODO RESOLUCIÓN ═══\n"
        "Hay un procedimiento de un caso parecido. Tu prioridad es RESOLVER con el operador usando estos pasos,\n"
        "ANTES de generar ticket al NOC. Solo escalá si los pasos no aplican, fallan o el operador lo pide.\n"
        "PROHIBIDO copiar datos ajenos (modelo, línea, proveedor). Los datos del operador en el chat mandan.\n\n"
    )
    partes_cuerpo = [f"### {b.titulo}\n"]
    if problema_kb:
        partes_cuerpo.append(f"#### Problema de referencia (solo contexto)\n{problema_kb}\n")
    if preguntas:
        partes_cuerpo.append(f"#### Pasos de verificación (aplicar al caso actual)\n{preguntas}\n")
    if resolucion:
        partes_cuerpo.append(f"#### Pasos de resolución (guiar al operador)\n{resolucion}\n")
    if len(partes_cuerpo) == 1:
        partes_cuerpo.append(b.contenido)

    texto = encabezado + "\n".join(partes_cuerpo)
    if len(texto) > max_chars:
        texto = texto[: max_chars - 80] + "\n\n[... contenido truncado por límite de contexto ...]"
    return texto


def formatear_modo_escalamiento() -> str:
    return """
═══ MODO FILTRO E HIGIENE — SIN COINCIDENCIA EN BASE DE CONOCIMIENTO ═══
No se encontró un procedimiento aplicable en el historial de tickets cargado.
DEBÉS:
1. Avisar con empatía que el caso se escalará al NOC de imowi (no podés resolverlo con la KB).
2. Exigir estrictamente los datos obligatorios que falten: Línea, Dispositivo, Descripción de falla
   (y Cooperativa si no la tenés).
3. Cuando los datos estén completos: generá ticket al NOC y cerrá la conversación.
NO digas que "no tenés información" sin ofrecer el escalamiento.
NO intentes resolver con KB (no hay procedimiento cargado).
"""


def listar_muestra_modulos(limite: int = 20) -> list[dict[str, str]]:
    return [
        {"id": b.id, "nombre": b.titulo}
        for b in _bloques[:limite]
    ]
