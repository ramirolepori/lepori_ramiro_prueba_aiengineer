"""RAG mínimo sobre los 5 documentos de TiendaHogar, solo con librería estándar.

Cada documento mide menos de 400 caracteres, así que el chunking es un documento = un fragmento
(partirlos separaría frases que se necesitan juntas). `dividir` queda para cuando el corpus crezca.
La recuperación es BM25 con normalización de tildes, plural simple y una tabla corta de conceptos
(por ejemplo "devolver" y "devolución" apuntan al mismo término), porque BM25 puro no ve sinónimos.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

DOCS_POR_DEFECTO = Path(__file__).resolve().parent / "data" / "docs"

STOPWORDS = {
    "a", "al", "ante", "con", "como", "cual", "cuales", "cuando", "de", "del", "el", "ella", "en", "es", "esta",
    "este", "esto", "la", "las", "lo", "los", "me", "mi", "mis", "no", "o", "para", "por", "que", "se", "si",
    "su", "sus", "un", "una", "unas", "uno", "unos", "y", "ya", "hay", "son", "ser", "debe", "puede", "pueden",
    "quiero", "quisiera", "necesito", "puedo", "tengo", "tienen", "hola", "buenas", "gracias", "favor", "saber",
    "cuanto", "cuantos", "cuanta", "cuantas", "donde", "quien", "hacer", "mas", "muy", "tiempo", "tarda",
}

# palabra normalizada -> término canónico que se agrega a la consulta y a los fragmentos
CONCEPTOS = {
    "garantia": ["garantia", "defecto", "defectuoso", "defectuosa", "fabrica", "falla", "fallo", "roto",
                 "rota", "descompuso", "descompuesto", "reparar", "reparacion", "arreglar", "cubre"],
    "devolucion": ["devolver", "devolucion", "devuelvo", "devuelve", "devuelto", "regresar", "retornar",
                   "cambiar", "cambio"],
    "envio": ["envio", "enviar", "envian", "envia", "entrega", "entregar", "llega", "llegar", "despacho",
              "demora", "demorar"],
    "reembolso": ["reembolso", "reembolsar", "reembolsan", "reintegro", "dinero", "plata", "reembolsa"],
    "liquidacion": ["liquidacion", "oferta", "personalizado", "personalizada", "descuento", "rebaja"],
}
_A_CONCEPTO = {palabra: c for c, palabras in CONCEPTOS.items() for palabra in palabras}


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes."""
    s = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _raiz(t: str) -> str:
    if len(t) > 4 and t.endswith("es"):
        return t[:-2]
    if len(t) > 3 and t.endswith("s"):
        return t[:-1]
    return t


def tokenizar(texto: str) -> list[str]:
    tokens: list[str] = []
    for t in re.findall(r"[a-z0-9]+", normalizar(texto)):
        if t in STOPWORDS or len(t) < 2:
            continue
        r = _raiz(t)
        tokens.append(r)
        concepto = _A_CONCEPTO.get(r) or _A_CONCEPTO.get(t)
        if concepto and concepto != r:
            tokens.append(concepto)
    return tokens


@dataclass(frozen=True)
class Fragmento:
    id: str          # "<documento>#<n>"
    documento: str   # nombre del archivo sin extensión
    texto: str


def dividir(texto: str, documento: str, tam: int = 600, solape: int = 100) -> list[Fragmento]:
    """Parte por párrafos y agrupa hasta ~`tam` caracteres. Con tam=600 cada documento de TiendaHogar queda entero."""
    parrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]
    grupos: list[str] = []
    actual = ""
    for p in parrafos:
        if actual and len(actual) + len(p) + 2 > tam:
            grupos.append(actual)
            actual = actual[-solape:] + "\n\n" + p if solape else p
        else:
            actual = f"{actual}\n\n{p}" if actual else p
    if actual:
        grupos.append(actual)
    return [Fragmento(f"{documento}#{i}", documento, g) for i, g in enumerate(grupos)]


@dataclass(frozen=True)
class Resultado:
    fragmento: Fragmento
    puntaje: float       # BM25
    cobertura: float     # fracción del peso de la consulta que el fragmento cubre (0 a 1)


class IndiceBM25:
    """Índice BM25 con umbral de relevancia.

    Un fragmento se devuelve si su puntaje BM25 es >= `min_puntaje` y >= `rel_top` veces el del mejor.
    Si ninguno pasa, `buscar` devuelve [] y el agente dice que no sabe. El umbral absoluto se calibró con
    preguntas dentro y fuera de alcance (tests/test_rag.py); con un corpus mayor conviene un umbral por
    similitud de embeddings.
    """

    def __init__(self, fragmentos: list[Fragmento], k1: float = 1.5, b: float = 0.75,
                 min_puntaje: float = 1.5, rel_top: float = 0.5):
        self.fragmentos = fragmentos
        self._k1, self._b = k1, b
        self.min_puntaje, self.rel_top = min_puntaje, rel_top
        self._tf = [Counter(tokenizar(f.texto)) for f in fragmentos]
        self._largos = [sum(c.values()) for c in self._tf]
        self._prom = (sum(self._largos) / len(self._largos)) if self._largos else 0.0
        df: Counter[str] = Counter()
        for c in self._tf:
            df.update(c.keys())
        n = len(fragmentos)
        self._n = n
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        self._idf_desconocido = math.log(1 + (n + 0.5) / 0.5)

    def _peso(self, t: str) -> float:
        return self._idf.get(t, self._idf_desconocido)

    def buscar(self, consulta: str, k: int = 3) -> list[Resultado]:
        q = list(dict.fromkeys(tokenizar(consulta)))
        if not q:
            return []
        total = sum(self._peso(t) for t in q)
        res: list[Resultado] = []
        for i, f in enumerate(self.fragmentos):
            tf, largo = self._tf[i], self._largos[i]
            s = cubierto = 0.0
            coincidencias = []
            for t in q:
                if t not in tf:
                    continue
                coincidencias.append(t)
                num = tf[t] * (self._k1 + 1)
                den = tf[t] + self._k1 * (1 - self._b + self._b * largo / (self._prom or 1))
                s += self._idf.get(t, 0.0) * num / den
                cubierto += self._idf.get(t, 0.0)
            # una sola palabra suelta que no es un concepto del dominio (por ejemplo "capital" en
            # "capital de Francia") no alcanza para considerar relevante a un documento
            if s > 0 and (len(coincidencias) >= 2 or any(t in CONCEPTOS for t in coincidencias)):
                res.append(Resultado(f, s, cubierto / total if total else 0.0))
        res.sort(key=lambda r: r.puntaje, reverse=True)
        if not res:
            return []
        mejor = res[0].puntaje
        return [r for r in res[:k] if r.puntaje >= self.min_puntaje and r.puntaje >= self.rel_top * mejor]


def cargar_indice(carpeta: Path | None = None, **kwargs: float) -> IndiceBM25:
    """Indexa todos los .md y .txt de una carpeta (por defecto, los 5 documentos de TiendaHogar)."""
    fragmentos: list[Fragmento] = []
    for ruta in sorted(Path(carpeta or DOCS_POR_DEFECTO).glob("*")):
        if ruta.suffix.lower() in {".md", ".txt"}:
            fragmentos += dividir(ruta.read_text(encoding="utf-8"), ruta.stem)
    return IndiceBM25(fragmentos, **kwargs)
