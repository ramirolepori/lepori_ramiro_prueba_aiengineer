import json
from pathlib import Path

import pytest

from tiendahogar.montos import extraer_montos

CASOS = Path(__file__).parent / "data" / "guardrail_evaluacion.json"


@pytest.mark.parametrize("texto,esperado", [
    ("$600", [600.0]), ("600 USD", [600.0]), ("USD600", [600.0]), ("600usd", [600.0]),
    ("1.200 dólares", [1200.0]), ("1,200.50 USD", [1200.5]), ("$1.000,50", [1000.5]), ("500,5 pesos", [500.5]),
    ("$ 1 200", [1200.0]), ("1 200 dólares", [1200.0]), ("$500.00", [500.0]), ("500,01", [500.01]),
    ("$2k", [2000.0]), ("1.5k dólares", [1500.0]), ("$0.5k", [500.0]), ("2 mil dólares", [2000.0]),
    ("mil dólares", [1000.0]), ("dos mil pesos", [2000.0]), ("mil quinientos dólares", [1500.0]),
    ("quinientos un dólares", [501.0]), ("seiscientos cincuenta pesos", [650.0]),
    ("treinta y cinco dólares", [35.0]), ("quinientas", [500.0]), ("seicientos dólares", [600.0]),
    ("un millón de pesos", [1_000_000.0]),
])
def test_formatos_de_monto(texto, esperado):
    assert extraer_montos(texto) == esperado


@pytest.mark.parametrize("texto", [
    "30 días", "hace 600 días", "dentro de 6 meses", "2 productos", "ORD-1001", "mi pedido ORD-1001 hace 3 días",
    "pedido 1001", "número de pedido 1003", "descuento del 20%", "una licuadora", "dos veces", "hola",
])
def test_lo_que_no_es_dinero(texto):
    assert extraer_montos(texto) == []


def test_varios_montos_en_la_misma_frase():
    assert extraer_montos("uno de $200 y otro de $150") == [200.0, 150.0]


def test_los_montos_del_set_de_evaluacion_se_clasifican_bien():
    """Para toda frase del set con intención de reembolso: supera $500 solo si se espera que escale."""
    casos = json.loads(CASOS.read_text(encoding="utf-8"))["casos"]
    for c in casos:
        if c["tipo"] != "monto":
            continue
        supera = max(extraer_montos(c["texto"]), default=0) > 500
        assert supera == bool(c["esperado"]), c["texto"]
