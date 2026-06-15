"""
Motor RAG simplificado: parseo de Markdown + búsqueda por palabras clave.
Solo fragmentos relevantes al mensaje del operador van al LLM (evita error 413).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from app.config import (
    KNOWLEDGE_MAX_FRAGMENT_CHARS,
    KNOWLEDGE_MIN_SCORE,
    KNOWLEDGE_TOP_K,
)

# ─── Estado global (cargado en startup) ───
_bloques: list["BloqueConocimiento"] = []
_indice_invertido: dict[str, set[int]] = {}
_cargado: bool = False
_fuentes: list[Path] = []


@dataclass
class BloqueConocimiento:
    id: str
    titulo: str
    contenido: str
    texto_busqueda: str
    fuente: str = ""
    tokens: set[str] = field(default_factory=set)


@dataclass
class ResultadoBusqueda:
    encontrado: bool
    bloque: BloqueConocimiento | None = None
    puntaje: float = 0.0
    modo: str = "escalamiento"  # "resolucion" | "escalamiento"
    terminos_coincidentes: list[str] = field(default_factory=list)


STOPWORDS = frozenset(
    """
    el la los las un una unos unas de del al a y en que es por para con su sus
    se lo le da do eso esta este estos esas como mas pero sin sobre entre hasta
    hay ser fue son era eran muy tambien ya solo cada cuando donde quien cual
    """.split()
)

TERMINOS_TECNICOS = frozenset(
    """
    esim esims roaming apn lte 5g imsi sms a2p jsc noc imowi sim iphone android
    datos llamadas cobertura volte imei eid movistar personal claro catel
    """.split()
)

CARPETAS_CONOCIMIENTO = ("contratos", "knowledge", "base_conocimiento")
ARCHIVOS_CONOCIMIENTO = (
    "base_conocimiento.md",
    "Base_de_Conocimiento_Tickets.md",
    "base_conocimiento_tickets.md",
)


def _normalizar_texto(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    return re.sub(r"\s+", " ", t).strip()


def _extraer_terminos_compuestos(texto: str) -> set[str]:
    """Captura términos técnicos antes de tokenizar (eSIM, Roaming, APN, etc.)."""
    encontrados: set[str] = set()
    texto_norm = _normalizar_texto(texto)
    for termino in TERMINOS_TECNICOS:
        if re.search(rf"\b{re.escape(termino)}\b", texto_norm):
            encontrados.add(termino)
    return encontrados


def tokenizar(texto: str) -> set[str]:
    tokens = _extraer_terminos_compuestos(texto)
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


def _extraer_fragmentos_relevantes(
    texto: str,
    query_tokens: set[str],
    max_chars: int,
) -> str:
    """Dentro de un bloque KB, conserva solo párrafos que coinciden con la consulta."""
    if not texto:
        return ""
    if not query_tokens:
        return texto[:max_chars]

    segmentos = [s.strip() for s in re.split(r"\s*\|\s*|\n\n+", texto) if s.strip()]
    if len(segmentos) <= 1:
        norm = _normalizar_texto(texto)
        if any(len(t) >= 4 and t in norm for t in query_tokens):
            return texto[:max_chars]
        return texto[:max_chars]

    puntajes: list[tuple[float, str]] = []
    for segmento in segmentos:
        if len(segmento) < 15:
            continue
        seg_tokens = tokenizar(segmento)
        overlap = query_tokens & seg_tokens
        norm_seg = _normalizar_texto(segmento)
        if not overlap:
            for termino in query_tokens:
                if len(termino) >= 4 and termino in norm_seg:
                    overlap = {termino}
                    break
        if not overlap:
            continue
        score = len(overlap) / max(len(query_tokens), 1)
        if any(t in TERMINOS_TECNICOS for t in overlap):
            score += 0.15
        puntajes.append((score, segmento))

    if not puntajes:
        return texto[:max_chars]

    puntajes.sort(reverse=True, key=lambda item: item[0])
    seleccionados: list[str] = []
    total = 0
    for _, segmento in puntajes:
        if total + len(segmento) > max_chars:
            restante = max_chars - total
            if restante > 80:
                seleccionados.append(segmento[:restante].rstrip() + "...")
            break
        seleccionados.append(segmento)
        total += len(segmento) + 3

    return " | ".join(seleccionados)


def parsear_markdown(contenido: str, fuente: str = "") -> list[BloqueConocimiento]:
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
                fuente=fuente,
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
    for nombre in ARCHIVOS_CONOCIMIENTO:
        ruta = raiz / nombre
        if ruta.is_file():
            return ruta
    raise FileNotFoundError(
        f"No se encontró base de conocimiento en {raiz}. "
        f"Colocá base_conocimiento.md, una carpeta contratos/ con .md, "
        f"o Base_de_Conocimiento_Tickets.md"
    )


def resolver_fuentes_conocimiento(raiz: Path | None = None) -> list[Path]:
    """Archivo único .md o todos los .md dentro de contratos/ / knowledge/."""
    raiz = raiz or Path(__file__).resolve().parent.parent
    for carpeta in CARPETAS_CONOCIMIENTO:
        dir_path = raiz / carpeta
        if dir_path.is_dir():
            archivos = sorted(p for p in dir_path.rglob("*.md") if p.is_file())
            if archivos:
                return archivos
    return [resolver_ruta_base_conocimiento(raiz)]


def cargar_base_conocimiento(raiz: Path | None = None) -> dict:
    """Indexa la KB en memoria. No envía el archivo completo al LLM."""
    global _bloques, _indice_invertido, _cargado, _fuentes

    _fuentes = resolver_fuentes_conocimiento(raiz)
    _bloques = []
    for ruta in _fuentes:
        contenido = ruta.read_text(encoding="utf-8", errors="replace")
        _bloques.extend(parsear_markdown(contenido, fuente=str(ruta.name)))

    _indice_invertido = _construir_indice_invertido(_bloques)
    _cargado = True

    return {
        "modo": "keyword_rag",
        "fuentes": [str(p) for p in _fuentes],
        "archivo": str(_fuentes[0]) if len(_fuentes) == 1 else f"{len(_fuentes)} archivos",
        "bloques": len(_bloques),
        "tokens_indice": len(_indice_invertido),
    }


def esta_cargado() -> bool:
    return _cargado


def estadisticas() -> dict:
    return {
        "cargado": _cargado,
        "modo": "keyword_rag",
        "fuentes": [str(p) for p in _fuentes],
        "archivo": str(_fuentes[0]) if _fuentes else None,
        "total_bloques": len(_bloques),
    }


def _puntaje_bloque(query_tokens: set[str], bloque: BloqueConocimiento) -> float:
    if not query_tokens or not bloque.tokens:
        return 0.0

    interseccion = query_tokens & bloque.tokens
    if not interseccion:
        texto_norm = _normalizar_texto(bloque.texto_busqueda)
        for termino in query_tokens:
            if len(termino) >= 4 and termino in texto_norm:
                interseccion = {termino}
                break

    if not interseccion:
        return 0.0

    cobertura = len(interseccion) / len(query_tokens)
    densidad = len(interseccion) / max(len(bloque.tokens), 1)
    bonus_tecnico = 0.12 if interseccion & TERMINOS_TECNICOS else 0.0
    bonus_frase = 0.0
    query_texto = " ".join(sorted(query_tokens))
    texto_norm = _normalizar_texto(bloque.texto_busqueda)
    if len(query_texto) > 8 and query_texto[:40] in texto_norm:
        bonus_frase = 0.2

    return min(1.0, cobertura * 0.65 + densidad * 0.2 + bonus_frase + bonus_tecnico)


def _interseccion_minima(query_tokens: set[str], interseccion: set[str]) -> int:
    if interseccion & TERMINOS_TECNICOS:
        return 1
    if len(query_tokens) == 1:
        unico = next(iter(query_tokens))
        if len(unico) >= 4 or unico in TERMINOS_TECNICOS:
            return 1
    return 2


def buscar_contexto(
    consulta: str,
    *,
    min_score: float | None = None,
    top_k: int | None = None,
) -> ResultadoBusqueda:
    """Busca bloques relevantes por palabras clave (no carga la KB completa)."""
    if not _cargado or not _bloques:
        return ResultadoBusqueda(encontrado=False, modo="escalamiento")

    min_score = min_score if min_score is not None else KNOWLEDGE_MIN_SCORE
    top_k = top_k or KNOWLEDGE_TOP_K
    query_tokens = tokenizar(consulta)

    if not query_tokens:
        return ResultadoBusqueda(encontrado=False, modo="escalamiento")

    candidatos_idx: set[int] = set()
    for token in query_tokens:
        candidatos_idx.update(_indice_invertido.get(token, ()))

    if not candidatos_idx:
        norm_consulta = _normalizar_texto(consulta)
        for token in query_tokens:
            if len(token) < 4:
                continue
            for idx_token, indices in _indice_invertido.items():
                if token in idx_token or idx_token in token:
                    candidatos_idx.update(indices)

    if not candidatos_idx:
        candidatos_idx = set(range(min(len(_bloques), 300)))

    puntajes: list[tuple[float, int]] = []
    for idx in candidatos_idx:
        if idx >= len(_bloques):
            continue
        puntaje = _puntaje_bloque(query_tokens, _bloques[idx])
        if puntaje > 0:
            puntajes.append((puntaje, idx))

    if not puntajes:
        return ResultadoBusqueda(encontrado=False, modo="escalamiento")

    puntajes.sort(reverse=True, key=lambda item: item[0])
    mejor_puntaje, mejor_idx = puntajes[0]
    mejor_bloque = _bloques[mejor_idx]
    interseccion = query_tokens & mejor_bloque.tokens
    if not interseccion:
        texto_norm = _normalizar_texto(mejor_bloque.texto_busqueda)
        interseccion = {t for t in query_tokens if len(t) >= 4 and t in texto_norm}

    min_inter = _interseccion_minima(query_tokens, interseccion)
    if mejor_puntaje < min_score or len(interseccion) < min_inter:
        return ResultadoBusqueda(
            encontrado=False,
            puntaje=mejor_puntaje,
            modo="escalamiento",
            terminos_coincidentes=sorted(interseccion),
        )

    return ResultadoBusqueda(
        encontrado=True,
        bloque=mejor_bloque,
        puntaje=mejor_puntaje,
        modo="resolucion",
        terminos_coincidentes=sorted(interseccion),
    )


def formatear_contexto_para_prompt(
    resultado: ResultadoBusqueda,
    consulta: str = "",
    max_chars: int | None = None,
) -> str:
    """Inyecta solo el fragmento KB seleccionado (no el archivo completo)."""
    if not resultado.encontrado or not resultado.bloque:
        return ""

    max_chars = max_chars or KNOWLEDGE_MAX_FRAGMENT_CHARS
    query_tokens = tokenizar(consulta) or set(resultado.terminos_coincidentes)
    b = resultado.bloque

    preguntas = _extraer_subseccion(b.contenido, "Preguntas / Verificaciones")
    resolucion = _extraer_subseccion(b.contenido, "Resolucion") or _extraer_subseccion(
        b.contenido, "Resolución"
    )
    problema_kb = _extraer_subseccion(b.contenido, "Problema")

    encabezado = (
        f"═══ FRAGMENTO KB ({b.titulo}) — match {resultado.puntaje:.0%} — "
        f"términos: {', '.join(resultado.terminos_coincidentes[:6]) or 'n/d'} ═══\n"
        "Usá SOLO este extracto como referencia de pasos. No copies datos ajenos del caso histórico.\n\n"
    )
    presupuesto = max(400, max_chars - len(encabezado) - 120)
    tercio = max(200, presupuesto // 3)

    partes_cuerpo = [f"### {b.titulo}\n"]
    if problema_kb:
        frag = _extraer_fragmentos_relevantes(problema_kb, query_tokens, tercio)
        if frag:
            partes_cuerpo.append(f"#### Problema (extracto)\n{frag}\n")
    if preguntas:
        frag = _extraer_fragmentos_relevantes(preguntas, query_tokens, tercio)
        if frag:
            partes_cuerpo.append(f"#### Verificación (extracto)\n{frag}\n")
    if resolucion:
        frag = _extraer_fragmentos_relevantes(resolucion, query_tokens, tercio)
        if frag:
            partes_cuerpo.append(f"#### Resolución (extracto)\n{frag}\n")

    if len(partes_cuerpo) == 1:
        partes_cuerpo.append(
            _extraer_fragmentos_relevantes(b.contenido, query_tokens, presupuesto)
        )

    texto = encabezado + "\n".join(partes_cuerpo)
    if len(texto) > max_chars:
        texto = texto[: max_chars - 80] + "\n\n[... fragmento KB truncado por límite 413 ...]"
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
    return [{"id": b.id, "nombre": b.titulo} for b in _bloques[:limite]]
