"""RAG mínimo sobre los 5 documentos de TiendaHogar, solo con librería estándar.

Cada documento mide menos de 400 caracteres, así que el chunking es un documento = un fragmento
(partirlos separaría frases que se necesitan juntas). `dividir` queda para cuando el corpus crezca.
La recuperación es BM25 con normalización de tildes, plural simple y una tabla corta de conceptos
(por ejemplo "devolver" y "devolución" apuntan al mismo término), porque BM25 puro no ve sinónimos.
"""

from __future__ import annotations

import difflib
import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .embeddings import ClienteEmbeddings, punto
from .llm import ErrorLLM
from .semantica import segmentar

DOCS_POR_DEFECTO = Path(__file__).resolve().parent / "data" / "docs"

STOPWORDS = {
    "a", "al", "ante", "con", "como", "cual", "cuales", "cuando", "de", "del", "el", "ella", "en", "es", "esta",
    "este", "esto", "la", "las", "lo", "los", "me", "mi", "mis", "no", "o", "para", "por", "que", "se", "si",
    "su", "sus", "un", "una", "unas", "uno", "unos", "y", "ya", "hay", "son", "ser", "debe", "puede", "pueden",
    "quiero", "quisiera", "necesito", "puedo", "tengo", "tienen", "hola", "buenas", "gracias", "favor", "saber",
    "cuanto", "cuantos", "cuanta", "cuantas", "donde", "quien", "hacer", "mas", "muy", "tiempo", "tarda", "tiene",
    "cualquier", "asistente", "tiendahogar", "ia", "sobre", "entre", "hacia", "hasta", "desde", "cada", "algo", "nada",
    "todo", "todos", "todas", "otro", "otra", "otros", "otras",
}

# palabra normalizada -> término canónico que se agrega a la consulta y a los fragmentos
CONCEPTOS = {
    "garantia": ["garantia", "defecto", "defectuoso", "defectuosa", "fabrica", "falla", "fallo", "roto",
                 "rota", "rompio", "rompe", "rompieron", "romper", "rompi", "descompuso", "descompuesto", "cubre", "quemo", "quemado", "quemada", "averia", "averio",
                 "desperfecto", "estropeo", "respalda", "respaldan", "respaldo", "cubierto", "cubierta"],
    "devolucion": ["arrepenti", "arrepiento", "arrepentimiento", "devolver", "devolucion", "devuelvo", "devuelve", "devuelto", "regresar", "retornar",
                   "cambiar", "cambio"],
    "envio": ["envio", "enviar", "envian", "envia", "entrega", "entregar", "llega", "llegar", "despacho", "despachar", "despachan",
              "demora", "demorar"],
    "reembolso": ["reembolso", "reembolsar", "reembolsan", "reintegro", "dinero", "plata", "reembolsa", "reintegran",
                  "reintegrar", "reintegren", "reintegrame", "guita"],
    "contacto": ["contacto", "contactar", "contactarme", "mail", "correo", "email", "soporte", "quejarme", "queja",
                 "reclamo", "quilombo"],
    "liquidacion": ["liquidacion", "oferta", "personalizado", "personalizada", "rebaja"],
}
# "mail", "correo" o "queja" aparecen en cualquier consulta: por sí solos no alcanzan para decir que el documento de contacto es relevante
CONCEPTOS_DEBILES = {"contacto"}
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


_PALABRAS_CONCEPTO = [p for p in _A_CONCEPTO if len(p) >= 6]


def _corregir(t: str) -> str:
    """Una falta de ortografía en una palabra del dominio ("reemoblso") vuelve a la palabra conocida."""
    if len(t) < 6 or not t.isalpha() or t in _A_CONCEPTO or _raiz(t) in _A_CONCEPTO:
        return t
    # una falta no cambia la primera letra: sin esa condición "aprender" se corregía a "prende" y "escribe" a "escribo"
    cerca = difflib.get_close_matches(t, [c for c in _PALABRAS_CONCEPTO if c[0] == t[0]], n=1, cutoff=0.85)
    return cerca[0] if cerca else t


_NO_ANDA = re.compile(r"\bno (?:funciona|anda|enciende|prende|arranca|sirve|calienta|enfria|lava|licua)\b")
# Frases que preguntan por el canal de contacto ("con quién hablo", "a qué mail escribo"): "hablo" o "escribo" por sí solas
# no dicen nada del dominio, pero la frase entera sí
_PIDE_CANAL = re.compile(
    r"\bcon (?:qu?ien|kien) (?:me )?(?:tengo que |debo |puedo |hay que )?(?:hablar|hablo|comunic\w+|contact\w+|contcat\w+|"
    r"reclam\w+|quej\w+)\b|"
    r"\ba (?:qu?ien|kien) (?:le )?(?:escribo|reclamo|consulto|me quejo|me dirijo|llamo|contacto)\b|"
    r"\b(?:a que|que) (?:mail|correo|email|canal)\b|"
    r"\bdonde (?:reclamo|me quejo|puedo quejarme)\b|\bcomo (?:me comunico|me contacto|contacto|hago un reclamo)\b|"
    # pide el dato de contacto: "cuál es el correo para reclamos", "tienen un mail de contacto", "mail de atención", "su email"
    r"\b(?:cual es|cuales son|dame|decime|dime|pasame|necesito|quiero|quisiera|tienen|tenes|tiene|hay)\b[^?.!]{0,20}"
    r"\b(?:correo|mail|e-?mail|canal|contacto)\b|"
    r"\b(?:correo|mail|e-?mail)\b (?:de|para) (?:contacto|atencion|soporte|ayuda|consultas?|reclamos?|quejas?)\b|"
    r"^\W*(?:el |un |su )?(?:correo|mail|e-?mail|contacto|canal de contacto)\W*$")
# Pide hablar con una persona o presentar un reclamo ("quiero hablar con un humano", "necesito un supervisor", "quiero presentar un
# reclamo formal"). Sin un tema de derivación en la frase se responde con el canal; con uno ("alguien del área legal") se deriva.
_PIDE_PERSONA = re.compile(
    r"\b(?:hablar|comunicarme|contactarme|chatear|pasame|comunicame|derivame|conectame|ponme) (?:con|a)(?: (?:una|un|el|la|algun[ao]?))? "
    r"(?:persona|humano|humana|agente|asesor\w*|supervisor\w*|operador\w*|alguien|representante|encargado|gerente)\b|"
    r"\b(?:necesito|quiero|quisiera) (?:un|el|una) (?:supervisor\w*|gerente|encargado|humano|asesor\w*|operador\w*)\b|"
    r"\batencion humana\b|"
    r"\b(?:presentar|hacer|iniciar|realizar|abrir|formular|efectuar) (?:un |el |mi )?(?:reclamo|queja)\b")
_PIDE_CANAL = re.compile(_PIDE_CANAL.pattern + "|" + _PIDE_PERSONA.pattern)


def tokenizar(texto: str) -> list[str]:
    tokens: list[str] = []
    # "no funciona", "no enciende"...: un defecto (por sí solas, "funciona" o "anda" no dicen nada del dominio)
    # "envío a La Plata" es la ciudad, no "plata" de dinero (que lleva al documento de reembolsos)
    t_norm = re.sub(r"\b(a|en|hasta|hacia|para|por|desde) la plata\b|\b(?:mar del|rio de la|del) plata\b", lambda m: (m.group(1) or "") + " laplata", normalizar(texto))
    t_norm = _PIDE_CANAL.sub("contacto canal", _NO_ANDA.sub("defecto", t_norm))
    for t in re.findall(r"[a-z0-9]+", t_norm):
        if t in STOPWORDS or len(t) < 2:
            continue
        t = _corregir(t)
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
                 min_puntaje: float = 1.4, rel_top: float = 0.5):
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

    def puntuar(self, consulta: str) -> list[Resultado]:
        """Todos los fragmentos con coincidencia léxica, del mejor al peor, sin aplicar el umbral."""
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
            if s > 0 and (len(coincidencias) >= 2 or any(t in CONCEPTOS and t not in CONCEPTOS_DEBILES for t in coincidencias)):
                res.append(Resultado(f, s, cubierto / total if total else 0.0))
        res.sort(key=lambda r: r.puntaje, reverse=True)
        return res

    def buscar(self, consulta: str, k: int = 3) -> list[Resultado]:
        res = self.puntuar(consulta)
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


# --- Recuperación híbrida: embeddings + BM25 -----------------------------------------------------------------

FUERA_DE_ALCANCE = DOCS_POR_DEFECTO.parent / "fuera_de_alcance.json"
_K_RRF = 60      # constante de la fusión por posición (reciprocal rank fusion)


class RecuperadorHibrido:
    """Recupera documentos por significado (embeddings) y por palabras (BM25), y los fusiona por posición.

    Relevancia: un documento cuenta si su similitud con la consulta supera por `margen` a la de las preguntas
    "fuera de alcance". Comparar contra lo que no se sabe responder, en lugar de usar un número absoluto, lo
    hace portable entre modelos de embeddings, que tienen escalas de similitud distintas. Con `usar_bm25` también
    cuenta lo que BM25 considera relevante. Después se descartan los que quedan más de `rel` por debajo del mejor.
    Si el servicio de embeddings falla, responde con BM25 solo (`ultimo_respaldo`).
    """

    def __init__(self, indice: IndiceBM25, cliente: ClienteEmbeddings, fuera_de_alcance: list[str] | None = None,
                 margen: float = 0.08, rel: float = 0.06, usar_bm25: bool = True, por_oracion: bool = True,
                 fraccion_del_mejor: float = 0.4):
        self.indice, self.cliente = indice, cliente
        self.por_oracion = por_oracion
        self.fuera = fuera_de_alcance or json.loads(FUERA_DE_ALCANCE.read_text(encoding="utf-8"))["preguntas"]
        self.margen, self.rel, self.usar_bm25 = margen, rel, usar_bm25
        self.fraccion_del_mejor = fraccion_del_mejor
        self.ultimo_respaldo = False
        self._vec_docs: dict[str, list[list[float]]] | None = None
        self._vec_fuera: list[list[float]] | None = None

    def _preparar(self) -> None:
        if self._vec_docs is None:
            partes = {f.id: self._partes(f.texto) for f in self.indice.fragmentos}
            planas = [t for ts in partes.values() for t in ts]
            todos = self.cliente.embeber_fijos(planas + self.fuera)     # textos fijos: una sola llamada y caché en disco
            vec = dict(zip(planas, todos[:len(planas)]))
            self._vec_docs = {i: [vec[t] for t in ts] for i, ts in partes.items()}
            self._vec_fuera = todos[len(planas):]

    def _partes(self, texto: str) -> list[str]:
        """El documento entero y, con `por_oracion`, cada una de sus oraciones (sin el título)."""
        if not self.por_oracion:
            return [texto]
        cuerpo = re.sub(r"^#.*\n+", "", texto).strip()
        oraciones = [o.strip() for o in re.split(r"(?<=[.!?])\s+", cuerpo) if len(o.strip()) > 20]
        return list(dict.fromkeys([texto] + oraciones))

    def similitudes(self, consulta: str) -> tuple[dict[str, float], float]:
        """Similitud de la consulta con cada documento y la mayor con una pregunta fuera de alcance."""
        self._preparar()
        q = self.cliente.embeber([consulta])[0]
        sims = {i: max(punto(q, v) for v in vs) for i, vs in self._vec_docs.items()}
        return sims, max(punto(q, v) for v in self._vec_fuera)

    def buscar(self, consulta: str, k: int = 3) -> list[Resultado]:
        self.ultimo_respaldo = False
        # Una consulta con dos temas ("cuánto tarda el envío y cuánto de garantía tiene") diluye su embedding y el
        # tema más fuerte tapa al otro: se recupera para la consulta entera y para cada cláusula, y se juntan.
        try:
            calculos = [(u, *self.similitudes(u)) for u in segmentar(consulta)]
        except ErrorLLM:
            self.ultimo_respaldo = True
            return self.indice.buscar(consulta, k)
        por_id = {f.id: f for f in self.indice.fragmentos}
        # Documentos que BM25 reconoce por una palabra explícita de la consulta ("reembolso", "garantía"): ancla léxica
        ancla = {r.fragmento.id for r in self.indice.buscar(consulta, k)} if self.usar_bm25 else set()
        elegidos: dict[str, tuple[float, float]] = {}        # id -> (fusión, margen sobre lo fuera de alcance)
        for unidad, sims, fuera in calculos:
            ancla_unidad = {r.fragmento.id for r in self.indice.buscar(unidad, 1)} if self.usar_bm25 else set()
            relevantes = {i for i, s in sims.items() if s - fuera >= self.margen} | ancla_unidad
            if not relevantes:
                continue
            pos_emb = {i: n for n, i in enumerate(sorted(sims, key=sims.get, reverse=True))}
            pos_bm = {r.fragmento.id: n for n, r in enumerate(self.indice.puntuar(unidad))}
            fusion = {i: 1 / (_K_RRF + pos_emb[i]) + (1 / (_K_RRF + pos_bm[i]) if i in pos_bm else 0.0)
                      for i in relevantes}
            mejor = max(sims[i] for i in relevantes)
            for i in relevantes:
                if (sims[i] >= mejor - self.rel or i in ancla_unidad) and fusion[i] > elegidos.get(i, (0.0, 0.0))[0]:
                    elegidos[i] = (fusion[i], sims[i] - fuera)
        if elegidos:
            # Un documento mucho más débil que el mejor (por ejemplo el que trae una cláusula suelta como "hace 5 días")
            # solo se queda si una palabra explícita de la consulta lo respalda.
            techo = max(m for _, m in elegidos.values())
            elegidos = {i: v for i, v in elegidos.items() if v[1] >= self.fraccion_del_mejor * techo or i in ancla}
        orden = sorted(elegidos, key=lambda i: elegidos[i][0], reverse=True)[:k]
        return [Resultado(por_id[i], *elegidos[i]) for i in orden]


def crear_recuperador(config: Config | None = None, cliente: ClienteEmbeddings | None = None
                      ) -> IndiceBM25 | RecuperadorHibrido:
    """Híbrido si hay EMBEDDING_MODEL (con proveedor openai); si no, BM25 solo."""
    config = config or Config()
    indice = cargar_indice()
    if config.embedding_model and config.proveedor == "openai":
        return RecuperadorHibrido(indice, cliente or ClienteEmbeddings(config))
    return indice
