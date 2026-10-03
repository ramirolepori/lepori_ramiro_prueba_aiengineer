"""Cronómetro por etapa, para separar lo que depende de los modelos de lo que depende de nuestro código.

Tres baldes en cada respuesta:
- `modelo_generativo_ms`: la llamada al modelo de lenguaje que redacta. Depende del modelo y del hardware.
- `modelo_embeddings_ms`: el tiempo esperando al servicio de embeddings. También depende del modelo y del hardware.
- `codigo_ms`: todo lo demás (reglas, parser, BM25, similitudes, tool de pedidos, validación). Es lo que se
  puede optimizar desde acá.
Las etapas (`guardrail_ms`, `recuperacion_ms`, ...) incluyen el tiempo de embeddings que pasó dentro de ellas.
"""

from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

ETAPAS = ("guardrail", "pedidos", "intencion", "recuperacion", "generacion", "validacion")


class Cronometro:
    def __init__(self) -> None:
        self.ms: dict[str, float] = defaultdict(float)

    def resumen(self, total_ms: float, embeddings_ms: float, embeddings_llamadas: int) -> dict[str, float]:
        out = {f"{e}_ms": round(self.ms.get(e, 0.0), 2) for e in ETAPAS}
        generativo = self.ms.get("generacion", 0.0)
        out.update({
            "total_ms": round(total_ms, 2),
            "embeddings_llamadas": embeddings_llamadas,
            "modelo_generativo_ms": round(generativo, 2),
            "modelo_embeddings_ms": round(embeddings_ms, 2),
            "codigo_ms": round(max(total_ms - generativo - embeddings_ms, 0.0), 2),
        })
        return out


_ACTUAL: ContextVar[Cronometro | None] = ContextVar("cronometro_actual", default=None)


@contextmanager
def activar(cron: Cronometro) -> Iterator[Cronometro]:
    token = _ACTUAL.set(cron)
    try:
        yield cron
    finally:
        _ACTUAL.reset(token)


@contextmanager
def etapa(nombre: str) -> Iterator[None]:
    """Suma al cronómetro activo el tiempo del bloque. Sin cronómetro activo no hace nada."""
    cron = _ACTUAL.get()
    t0 = time.perf_counter()
    try:
        yield
    finally:
        if cron is not None:
            cron.ms[nombre] += (time.perf_counter() - t0) * 1000
