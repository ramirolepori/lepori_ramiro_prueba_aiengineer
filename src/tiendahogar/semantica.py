"""Capa semántica del guardrail: reconoce paráfrasis y faltas de ortografía comparando la pregunta con frases
de ejemplo ("anclas") de cada categoría. No usa un LLM generativo: el mismo texto y el mismo modelo dan siempre
el mismo resultado.

Dos implementaciones con la misma interfaz `puntuar(texto) -> {categoria: similitud}`:
- `PuntajeEmbeddings`: similitud coseno de embeddings (endpoint `/v1/embeddings`, el de Ollama y OpenAI).
- `PuntajeNgramas`: similitud de n-gramas de caracteres con TF-IDF, solo librería estándar. Funciona sin red y
  tolera tildes, mayúsculas y faltas de ortografía.

La decisión se toma por margen: una categoría se activa si su similitud supera a la de las frases permitidas
("permitida") por al menos `margen`. Comparar contra lo permitido, en lugar de usar un umbral absoluto, hace al
método portable entre modelos de embeddings con escalas de similitud distintas.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Protocol

from .config import Config
from .embeddings import ClienteEmbeddings, punto
from .llm import ErrorLLM

CATEGORIAS = ("reembolso_mayor_500", "queja_trato", "disputa_facturacion", "tema_legal")
INTENCIONES = ("consulta_pedido",)      # intenciones que no son de riesgo pero se reconocen por significado
ANCLAS_POR_DEFECTO = Path(__file__).resolve().parent / "data" / "anclas.json"

# Calibrados con el conjunto de desarrollo (ver SUBMISSION.md y `python -m tiendahogar.evaluacion`)
MARGEN_EMBEDDINGS = 0.07
MARGEN_NGRAMAS = 0.0
MIN_NGRAMAS = 0.30          # los n-gramas no tienen la separación de los embeddings: además del margen, piso absoluto


def cargar_anclas(ruta: Path | None = None) -> dict[str, list[str]]:
    return json.loads(Path(ruta or ANCLAS_POR_DEFECTO).read_text(encoding="utf-8"))["categorias"]


# --- Segmentación ----------------------------------------------------------------------------------------

_CORTES = re.compile(
    r"[?!;¿¡\n]+|(?<!\d)\.|\.(?!\d)|,?\s+(?:y además|además|por cierto|mientras tanto|pero|aunque|también)\s+|,\s*y\s+|\s+y\s+",
    re.IGNORECASE,
)


def segmentar(texto: str) -> list[str]:
    """Texto completo más cada oración o cláusula (mínimo 8 caracteres), para que la parte permitida de una
    pregunta mixta no diluya a la parte que hay que derivar."""
    partes = [p.strip(" ,:") for p in _CORTES.split(texto)]
    unidades = [texto.strip()] + [p for p in partes if len(p) >= 8 and p != texto.strip()]
    return list(dict.fromkeys(unidades))


# --- Puntajes --------------------------------------------------------------------------------------------

class Puntaje(Protocol):
    def puntuar(self, textos: list[str]) -> list[dict[str, float]]: ...


class PuntajeEmbeddings:
    def __init__(self, config: Config, anclas: dict[str, list[str]] | None = None,
                 cliente: ClienteEmbeddings | None = None):
        self._cliente = cliente or ClienteEmbeddings(config)
        self._anclas = anclas or cargar_anclas()
        self._vec_anclas: dict[str, list[list[float]]] | None = None
        self._memo: dict[str, dict[str, float]] = {}      # el guardrail y la intención puntúan las mismas oraciones

    def puntuar(self, textos: list[str]) -> list[dict[str, float]]:
        if self._vec_anclas is None:
            planas = [t for v in self._anclas.values() for t in v]
            vec = dict(zip(planas, self._cliente.embeber_fijos(planas)))
            self._vec_anclas = {k: [vec[t] for t in v] for k, v in self._anclas.items()}
        nuevos = [t for t in dict.fromkeys(textos) if t not in self._memo]
        if nuevos:
            for t, v in zip(nuevos, self._cliente.embeber(nuevos)):
                self._memo[t] = {k: max(punto(v, a) for a in anclas) for k, anclas in self._vec_anclas.items()}
        return [self._memo[t] for t in textos]


def _sin_tildes(t: str) -> str:
    s = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _ngramas(texto: str, ns: tuple[int, ...] = (3, 4, 5)) -> Counter[str]:
    t = " " + re.sub(r"[^a-z0-9$ ]", " ", _sin_tildes(texto)) + " "
    c: Counter[str] = Counter()
    for n in ns:
        for i in range(len(t) - n + 1):
            c[t[i:i + n]] += 1
    return c


class PuntajeNgramas:
    def __init__(self, anclas: dict[str, list[str]] | None = None):
        self._anclas = anclas or cargar_anclas()
        docs = {k: [_ngramas(t) for t in v] for k, v in self._anclas.items()}
        df: Counter[str] = Counter()
        for lista in docs.values():
            for d in lista:
                df.update(set(d))
        self._n = sum(len(v) for v in docs.values())
        self._idf = {g: math.log((1 + self._n) / (1 + n)) + 1 for g, n in df.items()}
        self._vec = {k: [self._vectorizar(d) for d in v] for k, v in docs.items()}
        self._memo: dict[str, dict[str, float]] = {}

    def _vectorizar(self, c: Counter[str]) -> dict[str, float]:
        v = {g: (1 + math.log(f)) * self._idf.get(g, math.log(1 + self._n) + 1) for g, f in c.items()}
        norma = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {g: x / norma for g, x in v.items()}

    @staticmethod
    def _coseno(a: dict[str, float], b: dict[str, float]) -> float:
        if len(a) > len(b):
            a, b = b, a
        return sum(x * b.get(g, 0.0) for g, x in a.items())

    def puntuar(self, textos: list[str]) -> list[dict[str, float]]:
        out = []
        for t in textos:
            if t not in self._memo:
                v = self._vectorizar(_ngramas(t))
                self._memo[t] = {k: max(self._coseno(v, a) for a in vs) for k, vs in self._vec.items()}
            out.append(self._memo[t])
        return out


# --- Clasificador ----------------------------------------------------------------------------------------

class ClasificadorSemantico:
    """Devuelve las categorías de riesgo que reconoce en un texto. Si los embeddings fallan (sin red, modelo
    caído), usa los n-gramas para esa consulta y lo deja anotado en `ultimo_respaldo`."""

    def __init__(self, principal: Puntaje | None, respaldo: Puntaje | None = None,
                 margen: float | None = None, margen_respaldo: float = MARGEN_NGRAMAS,
                 piso_respaldo: float = MIN_NGRAMAS):
        if principal is None and respaldo is None:
            raise ValueError("hace falta al menos un puntaje")
        self.principal, self.respaldo = principal, respaldo
        self.margen = MARGEN_EMBEDDINGS if margen is None else margen
        self.margen_respaldo, self.piso_respaldo = margen_respaldo, piso_respaldo
        self.ultimo_respaldo = False
        self.nombre = type(principal or respaldo).__name__

    def _decidir(self, puntajes: list[dict[str, float]], margen: float, piso: float,
                 categorias: tuple[str, ...]) -> dict[str, float]:
        """Por categoría: el mejor margen (similitud con la categoría menos similitud con lo permitido).

        Para las categorías de riesgo, "permitido" incluye las consultas de pedido: preguntar por el estado de un
        pedido nunca es un reclamo."""
        mejores: dict[str, float] = {}
        for p in puntajes:
            for k in categorias:
                permitido = p.get("permitida", 0.0)
                if k in CATEGORIAS:
                    permitido = max(permitido, p.get(INTENCIONES[0], 0.0))
                m = p[k] - permitido
                if p[k] >= piso and m >= margen and m > mejores.get(k, -1.0):
                    mejores[k] = m
        return mejores

    def detectar(self, texto: str, categorias: tuple[str, ...] = CATEGORIAS) -> dict[str, float]:
        unidades = segmentar(texto)
        self.ultimo_respaldo = False
        if self.principal is not None:
            try:
                return self._decidir(self.principal.puntuar(unidades), self.margen, 0.0, categorias)
            except ErrorLLM:
                if self.respaldo is None:
                    raise
                self.ultimo_respaldo = True
        return self._decidir(self.respaldo.puntuar(unidades), self.margen_respaldo, self.piso_respaldo, categorias)


def crear_clasificador(config: Config | None = None, cliente: ClienteEmbeddings | None = None
                       ) -> ClasificadorSemantico:
    """Embeddings si hay EMBEDDING_MODEL configurado (con n-gramas de respaldo); si no, solo n-gramas."""
    config = config or Config()
    respaldo = PuntajeNgramas()
    if config.embedding_model and config.proveedor == "openai":
        return ClasificadorSemantico(PuntajeEmbeddings(config, cliente=cliente), respaldo)
    return ClasificadorSemantico(None, respaldo)
