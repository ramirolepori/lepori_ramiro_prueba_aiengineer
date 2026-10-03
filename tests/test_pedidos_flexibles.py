import pytest

from tiendahogar import AgenteSoporte
from tiendahogar.evaluacion import cargar_casos_pedidos, medir_pedidos
from tiendahogar.pedidos import extraer_order_ids, extraer_referencias
from tiendahogar.semantica import ClasificadorSemantico, PuntajeNgramas

CASOS = cargar_casos_pedidos()


@pytest.mark.parametrize("caso", CASOS, ids=lambda c: c["id"])
def test_extraccion_de_numeros_del_set(caso):
    assert extraer_order_ids(caso["texto"]) == caso["ids"], caso["texto"]


@pytest.mark.parametrize("texto,esperado", [
    ("ORD-1001", [("ORD-1001", "ORD-1001")]),
    ("ord1001", [("ORD-1001", "ord1001")]),
    ("mi pedido es el 1003", [("ORD-1003", "1003")]),
    ("pedidos 1001, 1002 y 1004", [("ORD-1001", "1001"), ("ORD-1002", "1002"), ("ORD-1004", "1004")]),
    ("ORD-1001 y de nuevo ORD-1001", [("ORD-1001", "ORD-1001")]),
])
def test_referencias_guardan_lo_que_escribio_el_cliente(texto, esperado):
    assert extraer_referencias(texto) == esperado


@pytest.mark.parametrize("texto", [
    "Quiero un reembolso de $1000", "Compré hace 600 días", "pedido de $1000", "mi pedido llegó hace 1001 días",
    "orden del día", "Tengo 1001 dudas", "ORD", "pedido de 2 productos",
])
def test_un_numero_sin_contexto_de_pedido_no_cuenta(texto):
    assert extraer_order_ids(texto) == []


@pytest.fixture(scope="module")
def agente():
    return AgenteSoporte()


def test_pedido_escrito_como_numero_suelto_se_consulta_y_se_aclara_lo_entendido(agente):
    r = agente.responder("pedido 1003, cuándo llega?")
    assert "Entendí que te referís al pedido ORD-1003" in r.texto and "Procesando" in r.texto


def test_pedido_con_formato_estandar_no_agrega_aclaracion(agente):
    r = agente.responder("Dónde está mi pedido ORD-1003?")
    assert "Entendí" not in r.texto and "Procesando" in r.texto


def test_varios_pedidos_en_una_pregunta(agente):
    r = agente.responder("Estado de los pedidos 1001 y 1004")
    assert "En tránsito" in r.texto and "Cancelado" in r.texto and len(r.pedidos) == 2


def test_numero_inexistente_no_inventa_y_muestra_lo_que_entendio(agente):
    r = agente.responder("Orden 4321 cuándo llega?")
    assert "No encontré ningún pedido con el número ORD-4321" in r.texto and "Entendí" in r.texto


@pytest.mark.parametrize("pregunta,producto", [
    ("Mi lavadora no llega", "lavadora"),
    ("Hace una semana que espero mi pedido", None),
    ("Ya salió lo que compré?", None),
])
def test_consulta_sin_numero_lo_pide_y_no_busca_por_producto(agente, pregunta, producto):
    r = agente.responder(pregunta)
    assert "ORD-XXXX" in r.texto and not r.pedidos
    if producto:
        assert producto in r.texto
    assert not any(estado in r.texto for estado in ("En tránsito", "Procesando", "Entregado", "Cancelado"))


def test_la_pregunta_de_politica_de_envio_no_se_toma_por_consulta_de_pedido(agente):
    r = agente.responder("Cuánto tarda el envío a la capital?")
    assert "ORD-XXXX" not in r.texto and "envios" in r.fuentes


def test_conjunto_de_pedidos_sin_red():
    """Piso del modo offline (n-gramas): números exactos y al menos 3 de cada 4 consultas sin número."""
    r = medir_pedidos(CASOS, ClasificadorSemantico(None, PuntajeNgramas()))
    assert r["ids_ok"] == r["total"]
    assert r["intencion_ok"] / r["con_intencion"] >= 0.75
    assert r["falsos"] <= 1
