"""El agente no responde lo que está fuera de los documentos: ni trivia, ni cálculos, ni charla. Banco de preguntas en
tests/data/fuera_de_alcance_evaluacion.json (distinto de la referencia que usa el umbral del recuperador)."""

import json
from pathlib import Path

import pytest

from tiendahogar import AgenteSoporte

BANCO = json.loads((Path(__file__).parent / "data" / "fuera_de_alcance_evaluacion.json").read_text(encoding="utf-8"))

# Casos que el agente maneja a propósito de otra forma:
#  - un tema legal siempre se deriva a una persona, aunque no tenga que ver con la tienda (documento 5);
#  - "paquete a la luna" habla de un envío: se responde con la política de envíos.
EXCEPCIONES = {"Cómo pongo una demanda de alimentos?", "Cuánto tarda en llegar un paquete a la luna?"}


@pytest.fixture(scope="module")
def agente():
    return AgenteSoporte()


@pytest.mark.parametrize("pregunta", [p for p in BANCO["puras"] if p not in EXCEPCIONES])
def test_una_pregunta_fuera_de_alcance_no_se_responde(agente, pregunta):
    r = agente.responder(pregunta)
    assert r.estado == "sin_informacion" and r.fuentes == [], r.texto


@pytest.mark.parametrize("pregunta", [
    "Qué distancia hay del sol a la luna?",
    "Cuál es la capital de Francia? (caso 3-0)",          # un texto de más no la convierte en una pregunta de envíos
    "Cuál es la capital de Francia? Gracias!",
    "Hola, quería saber qué distancia hay del sol a la luna",
    "Escribime un script en Python que ordene una lista",  # "ordene" no es "ordené un pedido"
])
def test_variantes_de_preguntas_fuera_de_alcance(agente, pregunta):
    r = agente.responder(pregunta)
    assert r.estado == "sin_informacion" and "número de pedido" not in r.texto


@pytest.mark.parametrize("pregunta", BANCO["cercanas"])
def test_una_pregunta_cercana_al_negocio_no_inventa(agente, pregunta):
    """Sin modelo, la respuesta es el texto de un documento o 'no tengo esa información': nunca un dato nuevo."""
    r = agente.responder(pregunta)
    assert r.estado in {"sin_informacion", "respondido"}
    if r.estado == "respondido":
        assert r.fuentes and all(f"[{f}]" in r.texto for f in r.fuentes)
