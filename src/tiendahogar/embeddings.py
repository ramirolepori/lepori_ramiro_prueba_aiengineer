"""Cliente de embeddings por HTTP (endpoint `/v1/embeddings`, el de OpenAI y el de Ollama) y similitud coseno.

Para no pagar el arranque en frío en cada proceso, los embeddings de textos fijos (documentos, anclas del
guardrail) se guardan en disco (`.cache/`, ignorado por git). Las preguntas de los clientes no se guardan nunca:
solo se recuerdan en memoria durante el proceso.
"""

from __future__ import annotations

import hashlib
import json
import math
import operator
import threading
import time
from pathlib import Path

from .config import Config
from .llm import ErrorLLM, _post
from .tiempos import sumar_embeddings


MAX_PREGUNTAS_EN_MEMORIA = 2000


def unitario(v: list[float]) -> list[float]:
    norma = math.sqrt(sum(x * x for x in v))
    return [x / norma for x in v] if norma else list(v)


def coseno(a: list[float], b: list[float]) -> float:
    """Coseno de dos vectores cualesquiera."""
    return punto(unitario(a), unitario(b))


def punto(a: list[float], b: list[float]) -> float:
    """Producto punto. Entre vectores unitarios (los que devuelve `ClienteEmbeddings`) es el coseno."""
    return sum(map(operator.mul, a, b))


class ClienteEmbeddings:
    """Pide embeddings en lote y recuerda los que ya pidió (cada texto se pide una sola vez).

    Devuelve vectores unitarios. Lleva la cuenta de las llamadas HTTP y del tiempo que tardó el servicio de embeddings, para separar en las
    mediciones lo que depende del modelo de embeddings de lo que depende de nuestro código.
    """

    def __init__(self, config: Config, cache_dir: Path | None = None):
        if not config.embedding_model:
            raise ErrorLLM("falta EMBEDDING_MODEL")
        self._c = config
        self._memo: dict[str, list[float]] = {}
        self._cuenta = threading.Lock()
        self.llamadas = 0          # llamadas HTTP al servicio
        self.segundos = 0.0        # tiempo acumulado esperando al servicio
        self.desde_disco = 0       # vectores que se leyeron del disco en lugar de pedirse
        cache_dir = cache_dir if cache_dir is not None else config.cache_dir
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._disco: dict[str, list[float]] | None = None
        self._fijos: set[str] = set()      # documentos y anclas: nunca se descartan de la memoria

    # --- caché en disco, solo para textos fijos ---

    def _ruta_cache(self) -> Path:
        modelo = "".join(c if c.isalnum() or c in "-_." else "_" for c in self._c.embedding_model)
        return self._cache_dir / f"embeddings_v2_{modelo}.json"      # v2: vectores ya normalizados

    def _clave(self, texto: str) -> str:
        return hashlib.sha1(texto.encode("utf-8")).hexdigest()

    def _cargar_disco(self) -> dict[str, list[float]]:
        if self._disco is None:
            self._disco = {}
            if self._cache_dir and self._ruta_cache().exists():
                try:
                    self._disco = json.loads(self._ruta_cache().read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    self._disco = {}      # caché dañada: se ignora y se vuelve a pedir
        return self._disco

    def embeber_fijos(self, textos: list[str]) -> list[list[float]]:
        """Como `embeber`, pero para textos que no cambian (documentos, anclas): usa y llena la caché en disco."""
        self._fijos.update(textos)
        if self._cache_dir is None:
            return self.embeber(textos)
        disco = self._cargar_disco()
        for t in textos:
            v = disco.get(self._clave(t))
            if v is not None and t not in self._memo:
                self._memo[t] = v
                self.desde_disco += 1
        faltan = [t for t in dict.fromkeys(textos) if self._clave(t) not in disco]
        vectores = self.embeber(textos)
        if faltan:
            for t in faltan:
                disco[self._clave(t)] = self._memo[t]
            try:
                self._cache_dir.mkdir(parents=True, exist_ok=True)
                self._ruta_cache().write_text(json.dumps(disco), encoding="utf-8")
            except OSError:
                pass                       # sin permiso de escritura: no es grave, solo no se guarda
        return vectores

    # --- pedido al servicio ---

    def embeber(self, textos: list[str]) -> list[list[float]]:
        nuevos = [t for t in dict.fromkeys(textos) if t not in self._memo]
        if nuevos:
            cab = {"Authorization": f"Bearer {self._c.api_key}"} if self._c.api_key else {}
            t0 = time.perf_counter()
            try:
                r = _post(self._c.base_url.rstrip("/") + "/embeddings", cab,
                          {"model": self._c.embedding_model, "input": nuevos}, self._c.timeout_s)
            finally:
                dt = time.perf_counter() - t0
                with self._cuenta:
                    self.llamadas += 1
                    self.segundos += dt
                sumar_embeddings(dt)
            try:
                vectores = [d["embedding"] for d in sorted(r["data"], key=lambda d: d["index"])]
            except (KeyError, TypeError) as e:
                raise ErrorLLM("respuesta de embeddings con formato inesperado") from e
            if len(vectores) != len(nuevos):
                raise ErrorLLM("el proveedor devolvió una cantidad inesperada de embeddings")
            try:
                unitarios = [unitario(v) for v in vectores]         # unitarios: el coseno es un producto punto
            except (TypeError, ValueError) as e:
                raise ErrorLLM("respuesta de embeddings con vectores inválidos") from e
            if len({len(v) for v in unitarios}) > 1:
                raise ErrorLLM("el proveedor devolvió vectores de distinto largo")
            self._memo.update(zip(nuevos, unitarios))
            self._recortar_memoria()
        return [self._memo[t] for t in textos]

    def _recortar_memoria(self) -> None:
        """Las preguntas de los clientes se recuerdan en memoria, pero no sin límite: en un proceso que corre días la
        memoria crecería con cada pregunta distinta. Se descartan las más viejas que no son textos fijos."""
        exceso = len(self._memo) - len(self._fijos) - MAX_PREGUNTAS_EN_MEMORIA
        if exceso > 0:
            for t in [t for t in self._memo if t not in self._fijos][:exceso]:
                del self._memo[t]
