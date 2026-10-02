import pytest

from tiendahogar.pedidos import PEDIDOS, consultar_estado_pedido, extraer_order_ids


@pytest.mark.parametrize("order_id,producto,estado,entrega", [
    ("ORD-1001", "Refrigeradora", "En tránsito", "3 días hábiles"),
    ("ORD-1002", "Licuadora", "Entregado", "—"),
    ("ORD-1003", "Lavadora", "Procesando", "6 días hábiles"),
    ("ORD-1004", "Tostadora", "Cancelado", "—"),
])
def test_pedido_valido(order_id, producto, estado, entrega):
    r = consultar_estado_pedido(order_id)
    assert r["encontrado"] is True
    assert (r["order_id"], r["producto"], r["estado"], r["entrega_estimada"]) == (order_id, producto, estado, entrega)


@pytest.mark.parametrize("order_id", ["ORD-9999", "ORD-1005", "", "1001", "cualquier cosa", "ORD-1001; DROP TABLE"])
def test_pedido_invalido_no_inventa_datos(order_id):
    r = consultar_estado_pedido(order_id)
    assert r["encontrado"] is False
    assert r["estado"] == "No encontrado"
    assert "producto" not in r and "entrega_estimada" not in r


def test_tolera_minusculas_y_espacios():
    assert consultar_estado_pedido(" ord-1001 ")["producto"] == "Refrigeradora"


def test_entrada_que_no_es_texto_no_rompe():
    assert consultar_estado_pedido(None)["estado"] == "No encontrado"  # type: ignore[arg-type]


def test_la_tabla_tiene_los_cuatro_pedidos_del_enunciado():
    assert sorted(PEDIDOS) == ["ORD-1001", "ORD-1002", "ORD-1003", "ORD-1004"]


def test_extrae_ids_del_texto():
    assert extraer_order_ids("mi pedido ord-1001 y también ORD-1003, de nuevo ORD-1001") == ["ORD-1001", "ORD-1003"]
    assert extraer_order_ids("sin número") == []
