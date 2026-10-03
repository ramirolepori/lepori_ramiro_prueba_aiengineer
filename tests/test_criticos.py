"""Lo primero que hay que leer: los comportamientos que pide el enunciado, uno por uno y sin depender de ningún modelo.

1. RAG: responde con los documentos y cita la fuente; lo que no está en ellos, no lo inventa.
2. Tool: `consultar_estado_pedido(order_id)` devuelve el pedido, o "No encontrado" si no existe.
3. Guardrail: reembolsos mayores a $500, quejas por el trato, disputas de facturación y temas legales se derivan a una persona.

El resto de los tests (más de 800) cubren variantes, frases mal escritas, ataques y la memoria de la conversación.
"""

import pytest

from tiendahogar import AgenteSoporte, consultar_estado_pedido

CONTACTO = "soporte@tiendahogar.example"


@pytest.fixture(scope="module")
def agente():
    return AgenteSoporte()          # sin modelo: el comportamiento crítico no lo necesita


# 1. RAG sobre los documentos ------------------------------------------------------------------------------------------

def test_responde_con_el_documento_y_lo_cita(agente):
    r = agente.responder("Cuánto dura la garantía de una licuadora?")
    assert r.estado == "respondido" and r.fuentes == ["garantia"] and "6 meses" in r.texto and "[garantia]" in r.texto


def test_liquidacion_no_se_devuelve(agente):
    r = agente.responder("Puedo devolver un producto en liquidación?")
    assert "devoluciones" in r.fuentes and "liquidación" in r.texto and "no se aceptan" in r.texto.lower()


def test_una_pregunta_ajena_a_los_documentos_no_se_inventa(agente):
    r = agente.responder("Quién ganó el mundial de 2022?")
    assert r.estado == "sin_informacion" and not r.fuentes and "No tengo esa información" in r.texto


# 2. Tool de pedidos ---------------------------------------------------------------------------------------------------

def test_la_tool_devuelve_un_pedido_existente():
    assert consultar_estado_pedido("ORD-1001") == {"order_id": "ORD-1001", "encontrado": True, "producto": "Refrigeradora",
                                                   "estado": "En tránsito", "entrega_estimada": "3 días hábiles"}


def test_la_tool_dice_que_no_encontro_un_pedido_inexistente():
    r = consultar_estado_pedido("ORD-9999")
    assert r["encontrado"] is False and r["estado"] == "No encontrado"


def test_el_agente_usa_la_tool_y_no_inventa_un_pedido(agente):
    assert "Refrigeradora" in agente.responder("Cuál es el estado de ORD-1001?").texto
    assert "No encontré ningún pedido" in agente.responder("Cuál es el estado de ORD-9999?").texto


# 3. Guardrail de derivación -------------------------------------------------------------------------------------------

def test_500_no_se_deriva_y_501_si(agente):
    assert agente.responder("Quiero un reembolso de $500").estado == "respondido"
    r = agente.responder("Quiero un reembolso de $501")
    assert r.estado == "escalado" and r.escalamientos == ["reembolso_mayor_500"] and CONTACTO in r.texto


@pytest.mark.parametrize("pregunta, categoria", [
    ("Un empleado me trató muy mal en el local", "queja_trato"),
    ("Me cobraron dos veces en la factura", "disputa_facturacion"),
    ("Tengo un problema con mi factura", "disputa_facturacion"),
    ("Voy a iniciar acciones legales contra la tienda", "tema_legal"),
])
def test_los_casos_de_derivacion_van_a_una_persona(agente, pregunta, categoria):
    r = agente.responder(pregunta)
    assert r.estado == "escalado" and r.escalamientos == [categoria] and CONTACTO in r.texto


def test_una_pregunta_mixta_responde_lo_permitido_y_deriva_lo_otro(agente):
    r = agente.responder("Cuánto dura la garantía de una licuadora? Además un empleado me trató mal")
    assert r.estado == "escalado" and "6 meses" in r.texto and CONTACTO in r.texto


# Hallazgos de una evaluación externa -----------------------------------------------------------------------------------

@pytest.mark.parametrize("pregunta", ["Me van a reembolsar en 5-10 días?", "Cuánto tarda un reembolso, de 5 a 10 días hábiles?"])
def test_un_rango_de_dias_no_es_un_monto(agente, pregunta):
    assert "Con el monto que indicás" not in agente.responder(pregunta).texto


def test_si_se_deriva_no_se_dice_que_no_hace_falta_un_supervisor(agente):
    r = agente.responder("Reembolso de 500 pesos y 1000 pesos")
    assert r.estado == "escalado" and "no hace falta la aprobación" not in r.texto
