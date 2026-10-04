"""Clientes de LLM con la librería estándar (urllib), sin dependencias.

- `OpenAICompatible`: sirve para OpenAI, Ollama, Gemini (endpoint compatible), Groq, vLLM, etc.
- `Anthropic`: API de mensajes de Anthropic.
Los dos reintentan con espera creciente ante errores de red o 429/5xx y cortan por tiempo máximo.
No se probaron contra una API real (ver SUBMISSION.md); los tests usan un cliente falso.
"""

from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Protocol

from .config import Config


class ErrorLLM(Exception):
    pass


class LLM(Protocol):
    def generar(self, sistema: str, usuario: str) -> str: ...


def _preferir_ipv4(url: str) -> str:
    """En Windows, `localhost` se resuelve primero a IPv6 (::1) y los servidores locales como Ollama escuchan en
    IPv4: cada llamada pierde unos 2 segundos esperando a que falle el intento. Con 127.0.0.1 son milisegundos."""
    partes = urllib.parse.urlsplit(url)
    if partes.hostname != "localhost":
        return url
    puerto = f":{partes.port}" if partes.port else ""
    return urllib.parse.urlunsplit(partes._replace(netloc="127.0.0.1" + puerto))


# Servicios que acaban de fallar: durante unos segundos no se vuelve a intentar. Sin esto, con un servidor caído cada
# llamada (guardrail, recuperación y redacción) esperaba sus propios reintentos y una sola pregunta tardaba más de 30 s.
_CAIDOS: dict[str, float] = {}
ESPERA_TRAS_CAIDA_S = 30.0


def _rechazada(error: Exception) -> bool:
    """¿El servidor rechazó la conexión (no hay nadie escuchando)? No depende del idioma del sistema."""
    return isinstance(error, ConnectionRefusedError) or isinstance(getattr(error, "reason", None), ConnectionRefusedError)


def _post(url: str, cabeceras: dict[str, str], cuerpo: dict, timeout: float, reintentos: int = 2) -> dict:
    datos = json.dumps(cuerpo).encode("utf-8")
    ultimo: Exception | None = None
    original = url
    servicio = urllib.parse.urlsplit(original).netloc
    if _CAIDOS.get(servicio, 0.0) > time.monotonic():
        raise ErrorLLM(f"el servicio {servicio} no responde (se vuelve a intentar en unos segundos)")
    url = _preferir_ipv4(original)
    for intento in range(reintentos + 1):
        req = urllib.request.Request(url, data=datos, method="POST",
                                     headers={"Content-Type": "application/json", **cabeceras})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resultado = json.loads(r.read().decode("utf-8"))
            _CAIDOS.pop(servicio, None)
            return resultado
        except urllib.error.HTTPError as e:
            ultimo = e
            if e.code not in {408, 429, 500, 502, 503, 504}:
                try:
                    detalle = e.read().decode("utf-8", "replace")[:300]
                except OSError:
                    detalle = ""
                raise ErrorLLM(f"el proveedor respondió HTTP {e.code}: {detalle}") from e
        except (OSError, http.client.HTTPException, ValueError) as e:  # red, corte de conexión, timeout, JSON roto
            ultimo = e
            if _rechazada(e):
                if url != original:
                    url = original     # el servidor local no escucha en IPv4: se vuelve a la dirección escrita
                    original = url
                    continue
                break                  # nadie escucha en esa dirección: reintentar no sirve de nada
        if intento < reintentos:
            time.sleep(2 ** intento)
    _CAIDOS[servicio] = time.monotonic() + ESPERA_TRAS_CAIDA_S
    raise ErrorLLM(f"no se pudo llamar al proveedor: {ultimo}")


class OpenAICompatible:
    def __init__(self, config: Config):
        if not config.modelo:
            raise ErrorLLM("falta LLM_MODEL")
        self._c = config

    def generar(self, sistema: str, usuario: str) -> str:
        cab = {"Authorization": f"Bearer {self._c.api_key}"} if self._c.api_key else {}
        base = {"model": self._c.modelo,
                "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]}
        url = self._c.base_url.rstrip("/") + "/chat/completions"
        # Los modelos de razonamiento de OpenAI exigen `max_completion_tokens` y rechazan `temperature`;
        # Gemini, Ollama y los modelos clásicos usan `max_tokens`. Se prueba lo clásico y, si el proveedor
        # lo rechaza con un 400, se reintenta con la variante nueva: el mismo código sirve para todos.
        variantes = [{"max_tokens": self._c.max_tokens, "temperature": 0},
                     {"max_completion_tokens": self._c.max_tokens}]
        for i, extra in enumerate(variantes):
            try:
                r = _post(url, cab, {**base, **extra}, self._c.timeout_s)
                break
            except ErrorLLM as e:
                if i == len(variantes) - 1 or "HTTP 400" not in str(e):
                    raise
        try:
            return r["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError, TypeError) as e:     # TypeError: la respuesta no es un objeto JSON
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
