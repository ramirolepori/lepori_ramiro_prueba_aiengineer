"""Cliente de embeddings por HTTP (endpoint `/v1/embeddings`, el de OpenAI y el de Ollama) y similitud coseno."""

from __future__ import annotations

import math

from .config import Config
from .llm import ErrorLLM, _post


def coseno(a: list[float], b: list[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return num / den if den else 0.0


class ClienteEmbeddings:
    """Pide embeddings en lote y recuerda los que ya pidió (cada texto se pide una sola vez)."""

    def __init__(self, config: Config):
        if not config.embedding_model:
            raise ErrorLLM("falta EMBEDDING_MODEL")
        self._c = config
        self._memo: dict[str, list[float]] = {}

    def embeber(self, textos: list[str]) -> list[list[float]]:
        nuevos = [t for t in dict.fromkeys(textos) if t not in self._memo]
        if nuevos:
            cab = {"Authorization": f"Bearer {self._c.api_key}"} if self._c.api_key else {}
            r = _post(self._c.base_url.rstrip("/") + "/embeddings", cab,
                      {"model": self._c.embedding_model, "input": nuevos}, self._c.timeout_s)
            try:
                vectores = [d["embedding"] for d in sorted(r["data"], key=lambda d: d["index"])]
            except (KeyError, TypeError) as e:
                raise ErrorLLM("respuesta de embeddings con formato inesperado") from e
            if len(vectores) != len(nuevos):
                raise ErrorLLM("el proveedor devolvió una cantidad inesperada de embeddings")
            self._memo.update(zip(nuevos, vectores))
        return [self._memo[t] for t in textos]
