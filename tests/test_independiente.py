import re

import pytest

from tiendahogar import independiente as ind
from tiendahogar.config import Config


@pytest.mark.parametrize("codigo,esperado", [
    ("R", {"grupo": "guardrail", "esperado_guardrail": ["reembolso_mayor_500"]}),
    ("t", {"grupo": "guardrail", "esperado_guardrail": ["queja_trato"]}),
    ("T+F", {"grupo": "guardrail", "esperado_guardrail": ["queja_trato", "disputa_facturacion"]}),
    ("OK", {"grupo": "guardrail", "esperado_guardrail": []}),
    ("P", {"grupo": "pedido", "esperado_guardrail": [], "ids": [], "intencion": True}),
    ("NP", {"grupo": "pedido", "esperado_guardrail": [], "ids": [], "intencion": False}),
    ("P=1001", {"grupo": "pedido", "esperado_guardrail": [], "ids": ["ORD-1001"], "intencion": True}),
    ("P=ORD-1001,1004", {"grupo": "pedido", "esperado_guardrail": [], "ids": ["ORD-1001", "ORD-1004"], "intencion": True}),
    ("D=garantia", {"grupo": "rag", "esperado_guardrail": [], "esperado_docs": ["garantia"]}),
    ("D=garantia+devoluciones", {"grupo": "rag", "esperado_guardrail": [], "esperado_docs": ["garantia", "devoluciones"]}),
    ("X", {"grupo": "rag", "esperado_guardrail": [], "esperado_docs": []}),
])
def test_codigos(codigo, esperado):
    assert ind.interpretar_codigo(codigo) == esperado


@pytest.mark.parametrize("codigo", ["Z", "R+Z", "D=otracosa", "P=abc", "", "D="])
def test_codigos_invalidos(codigo):
    with pytest.raises(ValueError):
        ind.interpretar_codigo(codigo)


def test_leer_frases_ignora_comentarios_y_vacias_y_acepta_base():
    texto = "# comentario\n\nR | Quiero mis 800 dólares de vuelta\nOK | Hola | 3\n"
    r = ind.leer_frases(texto)
    assert [x["texto"] for x in r] == ["Quiero mis 800 dólares de vuelta", "Hola"]
    assert r[1]["base"] == "3" and "base" not in r[0]


def test_leer_frases_informa_la_linea_con_el_error():
    with pytest.raises(ValueError, match="línea 2"):
        ind.leer_frases("R | bien\nZZ | mal")
    with pytest.raises(ValueError, match="línea 1"):
        ind.leer_frases("sin separador")


FRASES = [
    "El vendedor me trató muy mal en la sucursal",
    "Quiero que me devuelvan 1.200 dólares por la lavadora",
    "Dónde está mi pedido ORD-1003?",
    "Me cobraron dos veces la factura del pedido ORD-1001",
]


@pytest.mark.parametrize("frase", FRASES)
def test_las_variantes_automaticas_no_tocan_numeros_ni_ids(frase):
    for nombre, v in ind.variantes_automaticas(frase).items():
        assert re.findall(r"\d+", v) == re.findall(r"\d+", frase), nombre
        assert ("ORD" in v.upper()) == ("ORD" in frase.upper()), nombre


def test_las_variantes_son_distintas_a_la_original_y_hay_de_cada_tipo():
    v = ind.variantes_automaticas("El vendedor me trató muy mal en la sucursal")
    assert set(v) == {"sin_tildes", "mayusculas", "con_error", "estilo_chat"}
    assert all(t != "El vendedor me trató muy mal en la sucursal" for t in v.values())
    assert v["sin_tildes"] == "El vendedor me trato muy mal en la sucursal"
    assert v["estilo_chat"] == "el vendedor me trato muy mal en la sucursal"


def test_importar_y_variantes_de_punta_a_punta(tmp_path):
    ruta = tmp_path / "independiente.json"
    casos = ind.importar("T | El vendedor me trató muy mal\nP=1003 | pedido 1003 cuándo llega\nOK | Hola", ruta)
    assert [c["id"] for c in casos] == ["i001", "i002", "i003"] and all(c["origen"] == "Ramiro" for c in casos)
    nuevas = ind.agregar_variantes(ruta, manuales="T | Un empleado me faltó el respeto | 1")
    todas = ind.cargar(ruta)
    assert len(todas) == 3 + len(nuevas) and {c["origen"] for c in todas} == {"Ramiro", "variante"}
    manual = [c for c in todas if c.get("variante") == "parafrasis"][0]
    assert manual["base"] == "i001" and manual["esperado_guardrail"] == ["queja_trato"]
    assert all(c["base"] in {"i001", "i002", "i003"} for c in todas if c["origen"] == "variante")
    # volver a importar reemplaza todo y descarta las variantes viejas
    assert len(ind.importar("OK | Hola", ruta)) == 1 and len(ind.cargar(ruta)) == 1


def test_regenerar_variantes_no_duplica(tmp_path):
    ruta = tmp_path / "independiente.json"
    ind.importar("T | El vendedor me trató muy mal", ruta)
    ind.agregar_variantes(ruta)
    n = len(ind.cargar(ruta))
    ind.agregar_variantes(ruta)
    assert len(ind.cargar(ruta)) == n


def test_medicion_offline_corre_y_separa_por_origen(tmp_path, capsys):
    ruta = tmp_path / "independiente.json"
    ind.importar("T | El vendedor me trató muy mal\nP=1003 | pedido 1003 cuándo llega\nD=garantia | Cuánto dura la garantía "
                 "de una licuadora\nX | Cuál es la capital de Francia\nOK | Hola", ruta)
    ind.agregar_variantes(ruta)
    casos = ind.cargar(ruta)
    for origen in ("Ramiro", "variante"):
        ind.medir_origen([c for c in casos if c["origen"] == origen], Config(proveedor="none", embedding_model=""), True)
    salida = capsys.readouterr().out
    assert "guardrail" in salida and "pedidos" in salida and "recuperación de documentos" in salida
    assert "solo reglas" in salida and "BM25 solo" in salida
