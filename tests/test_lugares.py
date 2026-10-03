"""Plazo de envío según el lugar: lo decide el código, no el modelo (ver lugares.py)."""

import pytest

from tiendahogar import AgenteSoporte
from tiendahogar.lugares import resolver_lugares

CASOS = [
    # (consulta, tipo del primer lugar, ¿es capital provincial?)
    ("Soy de Córdoba capital, cuánto tarda el envío", "otra", True),
    ("Estoy en Mendoza capital, cuánto tarda?", "otra", True),
    ("y la capital de Salta?", "otra", True),
    ("Cuántos días tarda el envío a la capital del país?", "capital", False),
    ("Envíos a la capital, cuánto demoran?", "capital", False),
    ("Vivo en Capital Federal", "capital", False),
    ("Soy de CABA", "capital", False),
    ("vivo en Buenos Aires capital", "capital", False),
    ("Vivo en Palermo, cuánto tarda?", "capital", False),
    ("Mandan a Rosario? cuánto tarda", "otra", False),
    ("soy de cordova, cuanto tarda el envio", "otra", False),       # falta de ortografía
    ("Vivo en Bogotá, cuánto demora el envío?", "exterior", False),
    ("Hacen envíos a Chile?", "exterior", False),
    ("Soy de Córdoba, España. Envían?", "exterior", False),          # el país nombrado manda
    ("Vivo en Buenos Aires, cuánto tarda?", "ambiguo_ba", False),    # la Ciudad o la provincia
    ("Soy de Zapala, cuánto tarda el envío?", "desconocido", False), # no está en el gazetteer: no se adivina
]


@pytest.mark.parametrize("consulta,tipo,provincial", CASOS)
def test_resuelve_el_lugar(consulta, tipo, provincial):
    lugares = resolver_lugares(consulta)
    assert lugares and lugares[0].tipo == tipo
    assert lugares[0].capital_provincial is provincial


@pytest.mark.parametrize("consulta", [
    "Cuánto tarda el envío?",
    "Voy a hacer una compra de una heladera, cuánto tarda en llegar a mi casa?",
    "Cuál es la garantía de una licuadora?",
])
def test_sin_lugar_no_inventa_ninguno(consulta):
    assert resolver_lugares(consulta) == []


def test_dos_lugares():
    lugares = resolver_lugares("Mando a Rosario y a Córdoba capital, cuánto tardan?")
    assert [l.nombre for l in lugares] == ["Rosario", "Córdoba"]


@pytest.fixture(scope="module")
def agente():
    return AgenteSoporte()


def test_respuesta_capital_provincial_usa_el_plazo_de_otras_ciudades(agente):
    r = agente.responder("Soy de Córdoba capital, cuánto tarda el envío?")
    assert r.estado == "respondido" and r.fuentes == ["envios"]
    assert "5-7 días hábiles" in r.texto and "2-3" not in r.texto
    assert "no la del país" in r.texto and "[envios]" in r.texto


def test_respuesta_capital_del_pais(agente):
    r = agente.responder("Cuántos días tarda el envío a la capital del país?")
    assert "2-3 días hábiles" in r.texto and "5-7" not in r.texto and "Ciudad de Buenos Aires" in r.texto


def test_respuesta_exterior_no_hay_envio(agente):
    r = agente.responder("Hacen envíos a Chile?")
    assert "no están disponibles" in r.texto and "días hábiles" not in r.texto


def test_respuesta_buenos_aires_ambigua_da_los_dos_plazos(agente):
    r = agente.responder("Vivo en Buenos Aires, cuánto tarda el envío?")
    assert "2-3 días hábiles" in r.texto and "5-7 días hábiles" in r.texto and "Decime cuál es tu caso" in r.texto


def test_sin_lugar_da_todos_los_plazos_y_pide_la_ciudad(agente):
    r = agente.responder("Voy a hacer una compra de una heladera, cuánto tarda en llegar a mi casa?")
    assert "2-3 días hábiles" in r.texto and "5-7 días hábiles" in r.texto and "internacionales" in r.texto
    assert "Decime tu ciudad" in r.texto


def test_el_lugar_no_pide_numero_de_pedido(agente):
    r = agente.responder("Voy a hacer una compra desde Salta capital, cuánto tarda en llegar?")
    assert "número de pedido" not in r.texto and "5-7 días hábiles" in r.texto


class LLMQueInventa:
    """Un modelo que decide por su cuenta qué ciudad es la capital: el agente no tiene que usarlo para el envío."""
    llamadas = 0

    def generar(self, sistema, prompt):
        LLMQueInventa.llamadas += 1
        return "Córdoba capital es la capital, así que tarda 2-3 días hábiles. [envios]"


def test_el_modelo_no_decide_el_plazo_de_envio():
    a = AgenteSoporte(llm=LLMQueInventa())
    r = a.responder("Soy de Córdoba capital, cuánto tarda el envío?")
    assert LLMQueInventa.llamadas == 0 and "5-7 días hábiles" in r.texto and "2-3" not in r.texto


def test_envio_mas_garantia_el_modelo_solo_redacta_la_garantia():
    class LLM:
        prompts: list[str] = []

        def generar(self, sistema, prompt):
            LLM.prompts.append(prompt)
            return "La garantía cubre defectos de fabricación por 12 meses. [garantia]"

    r = AgenteSoporte(llm=LLM()).responder("Soy de Salta capital: cuánto tarda el envío y cuánto de garantía tiene la estufa?")
    assert LLM.prompts and "[envios]" not in LLM.prompts[0]
    assert "garantía cubre" in r.texto and "5-7 días hábiles" in r.texto


def test_una_pregunta_de_politica_no_pide_numero_de_pedido(agente):
    r = agente.responder("Cuánto tarda el envío y cuánto de garantía tiene la estufa? Soy de la capital")
    assert "número de pedido" not in r.texto and "2-3 días hábiles" in r.texto
