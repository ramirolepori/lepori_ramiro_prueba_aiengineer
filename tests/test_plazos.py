"""El plazo de devolución del Doc 2 aplicado por código a lo que el cliente dice que pasó desde la compra."""

import pytest

from tiendahogar import AgenteSoporte
from tiendahogar.plazos import dias_desde_la_compra, nota_de_devolucion


@pytest.mark.parametrize("texto,dias", [
    ("Quiero devolver mi heladera que compre hace 25 días", 25),
    ("Compré mi tostadora hace 45 días y la quiero devolver", 45),
    ("Compré hace dos meses y quiero cambiarlo", 60),
    ("Hace 3 semanas compré una tostadora, me la aceptan de vuelta?", 21),
    ("Ayer fui al local e hice una compra por $499,99 y quería devolverlo", 1),
    ("Compré una licuadora hace 40 días y no enciende, la devuelvo o hay garantía?", 40),
    ("Quiero devolver mi licuadora Antigüedad: hace 3 semanas.", 21),
    ("Hace 10 meses compré un refrigerador y quiero hacer la devolución", 300),
])
def test_dias_desde_la_compra(texto, dias):
    assert dias_desde_la_compra(texto) == dias


@pytest.mark.parametrize("texto", [
    "hace 6 días que envié el producto para que me devuelvan el dinero",         # días de espera de un reembolso
    "Cuánto dura la garantía de una licuadora comprada hace 3 meses?",           # no pide devolver
    "Devolví la heladera hace 8 días y todavía no me reintegran",
    "Quiero devolver mi heladera",                                               # sin duración
])
def test_no_cuenta_cuando_los_dias_son_de_otra_cosa(texto):
    assert dias_desde_la_compra(texto) is None


def test_la_nota_repite_el_documento():
    assert "defecto cubierto por la garantía" in nota_de_devolucion(31)
    assert "sin usar y en su empaque original" in nota_de_devolucion(30)


@pytest.mark.parametrize("pregunta,esperado", [
    ("Compré mi tostadora hace 45 días pero no la saqué del empaque, la quiero devolver", "pasaron más de 30 días"),
    ("Quiero devolver mi heladera que compré hace 25 días, solo la conecté para probarla", "dentro de los 30 días"),
])
def test_el_agente_agrega_la_cuenta_a_su_respuesta(pregunta, esperado):
    assert esperado in AgenteSoporte().responder(pregunta).texto


class LLMQueNoDebeUsarse:
    llamadas = 0

    def generar(self, sistema, prompt):
        LLMQueNoDebeUsarse.llamadas += 1
        return "No se aceptan devoluciones después de 30 días si el producto no fue usado. [devoluciones]"


def test_el_plazo_se_responde_por_codigo_y_no_con_el_modelo():
    r = AgenteSoporte(llm=LLMQueNoDebeUsarse()).responder("Compré mi tostadora hace 45 días pero no la saqué del empaque, la quiero devolver")
    assert LLMQueNoDebeUsarse.llamadas == 0
    assert "solo se acepta si el producto tiene un defecto cubierto por la garantía" in r.texto and "[devoluciones]" in r.texto


def test_con_mas_de_30_dias_y_una_falla_tambien_da_lo_que_dice_la_garantia():
    r = AgenteSoporte().responder("Compré una licuadora hace 40 días y no enciende, la devuelvo o hay garantía?")
    assert "pasaron más de 30 días" in r.texto and "6 meses" in r.texto and "[garantia]" in r.texto


@pytest.mark.parametrize("pregunta", [
    "Compré en liquidación hace 10 días y quiero devolver el producto",
    "Compré una heladera personalizada hace 20 días y la quiero devolver",
    "Compré una heladera que hicieron solo para mi hace 5 días y la quiero devolver",
])
def test_un_producto_que_no_se_devuelve_nunca_no_recibe_la_cuenta_de_los_dias(pregunta):
    texto = AgenteSoporte().responder(pregunta).texto
    assert "dentro de los 30 días" not in texto and "pasaron más de 30 días" not in texto
