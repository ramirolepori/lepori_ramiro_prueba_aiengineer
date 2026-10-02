"""Clientes de LLM con la librería estándar (urllib), sin dependencias.

- `OpenAICompatible`: sirve para OpenAI, Ollama, Gemini (endpoint compatible), Groq, vLLM, etc.
- `Anthropic`: API de mensajes de Anthropic.
Los dos reintentan con espera creciente ante errores de red o 429/5xx y cortan por tiempo máximo.
No se probaron contra una API real (ver SUBMISSION.md); los tests usan un cliente falso.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Protocol

from .config import Config


class ErrorLLM(Exception):
    pass


class LLM(Protocol):
    def generar(self, sistema: str, usuario: str) -> str: ...


def _post(url: str, cabeceras: dict[str, str], cuerpo: dict, timeout: float, reintentos: int = 2) -> dict:
    datos = json.dumps(cuerpo).encode("utf-8")
    ultimo: Exception | None = None
    for intento in range(reintentos + 1):
        req = urllib.request.Request(url, data=datos, method="POST",
                                     headers={"Content-Type": "application/json", **cabeceras})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            ultimo = e
            if e.code not in {408, 429, 500, 502, 503, 504}:
                raise ErrorLLM(f"el proveedor respondió HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            ultimo = e
        if intento < reintentos:
            time.sleep(2 ** intento)
    raise ErrorLLM(f"no se pudo llamar al proveedor tras {reintentos + 1} intentos: {ultimo}")


class OpenAICompatible:
    def __init__(self, config: Config):
        if not config.modelo:
            raise ErrorLLM("falta LLM_MODEL")
        self._c = config

    def generar(self, sistema: str, usuario: str) -> str:
        cab = {"Authorization": f"Bearer {self._c.api_key}"} if self._c.api_key else {}
        r = _post(self._c.base_url.rstrip("/") + "/chat/completions", cab, {
            "model": self._c.modelo, "max_tokens": self._c.max_tokens, "temperature": 0,
            "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
        }, self._c.timeout_s)
        try:
            return r["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError) as e:
            raise ErrorLLM("respuesta del proveedor con formato inesperado") from e


class Anthropic:
    def __init__(self, config: Config):
        if not (config.modelo and config.api_key):
            raise ErrorLLM("faltan LLM_MODEL o LLM_API_KEY")
        self._c = config

    def generar(self, sistema: str, usuario: str) -> str:
        r = _post("https://api.anthropic.com/v1/messages",
                  {"x-api-key": self._c.api_key, "anthropic-version": "2023-06-01"},
                  {"model": self._c.modelo, "max_tokens": self._c.max_tokens, "temperature": 0, "system": sistema,
                   "messages": [{"role": "user", "content": usuario}]}, self._c.timeout_s)
        try:
            return "".join(b["text"] for b in r["content"] if b.get("type") == "text").strip()
        except (KeyError, TypeError) as e:
            raise ErrorLLM("respuesta del proveedor con formato inesperado") from e


def crear_llm(config: Config | None = None) -> LLM | None:
    """Devuelve el cliente según LLM_PROVIDER, o None para el modo offline (sin LLM)."""
    config = config or Config()
    if config.proveedor in {"", "none", "offline"}:
        return None
    if config.proveedor == "openai":
        return OpenAICompatible(config)
    if config.proveedor == "anthropic":
        return Anthropic(config)
    raise ErrorLLM(f"LLM_PROVIDER desconocido: {config.proveedor} (usar none, openai o anthropic)")
